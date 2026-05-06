"""
postprocess.py — Universal Invoice Post-Processor (v3)
Handles:
- Standard invoices (Description / Qty / Unit Price / Total)
- OMV/JIB billing reports (multi-column, multi-page)
- Tables with col_span (merged header cells)
- Summary rows (Sub Total, Total, Credit)
- Multi-page continuation tables
- Multi-invoice PDFs (section splitting)
"""

import json
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def clean_amount(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        s = re.sub(r'[$€£¥₹\u062f\u062a]', '', s)
        s = re.sub(r'[\u0600-\u06FF]', '', s)
        s = re.sub(r'\b(USD|EUR|TND|GBP)\b\s*\$?\s*', '', s, flags=re.IGNORECASE)
        s = s.strip()
        if not s or s in ('-', '.', '—', '–', 'N/A', 'n/a', ''):
            return None
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        has_dot = '.' in s
        has_comma = ',' in s
        if has_comma and has_dot:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif has_comma and not has_dot:
            parts = s.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                s = s.replace(',', '.')
            else:
                s = s.replace(',', '')
        else:
            s = re.sub(r'[\s\u00a0]', '', s)
        s = s.replace(' ', '')
        try:
            f = float(s)
            return f if not (math.isnan(f) or math.isinf(f)) else None
        except ValueError:
            return None
    elif isinstance(val, (int, float)):
        f = float(val)
        return f if not (math.isnan(f) or math.isinf(f)) else None
    return None


def is_numeric(text: str) -> bool:
    if not text:
        return False
    return clean_amount(str(text)) is not None


def is_empty_cell(text: str) -> bool:
    t = str(text).strip() if text else ''
    return not t or t in ('-', '—', '–', 'N/A', 'n/a')


def has_real_value(text: str) -> bool:
    if is_empty_cell(text):
        return False
    t = str(text).strip()
    if t in ('0', '0.0', '0.00', '(0)', '(0.0)', '(0.00)', '(0.000)'):
        return False
    return True


# ---------------------------------------------------------------------------
# Currency & document type detection
# ---------------------------------------------------------------------------

def detect_currency(text: str) -> str:
    scores = {"TND": 0, "EUR": 0, "USD": 0, "GBP": 0}
    if re.search(r'\bTND\b|D\.T\b|\bDT\b|DINAR|Tunisian Dinar', text, re.IGNORECASE):
        scores["TND"] += 3
    if re.search(r'\bEUR\b|€|\bEURO\b', text, re.IGNORECASE):
        scores["EUR"] += 3
    if re.search(r'\bUSD\b|U\.S\.\s*DOLLAR|\$|\bDOLLAR\b|U\.S\. Dollars', text, re.IGNORECASE):
        scores["USD"] += 3
    if re.search(r'\bGBP\b|£|\bPOUND\b', text, re.IGNORECASE):
        scores["GBP"] += 3
    if re.search(r'TUNIS|SFAX|SOUSSE|BIZERTE|NABEUL', text, re.IGNORECASE):
        scores["TND"] += 2
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "USD"


def detect_document_type(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["joint interest", "billing detail", "joint venture"]):
        return "billing_report"
    if "working capital" in t:
        return "working_capital_report"
    if any(x in t for x in ["credit note", "avoir", "note de crédit"]):
        return "credit_note"
    if any(x in t for x in ["devis", "quotation", "quote", "pro forma", "proforma"]):
        return "quotation"
    if any(x in t for x in ["payslip", "fiche de paie", "bulletin de salaire"]):
        return "payslip"
    return "invoice"


# ---------------------------------------------------------------------------
# Rebuild matrix from cells (handles col_span properly)
# ---------------------------------------------------------------------------

def resolve_matrix(table: Dict) -> Tuple[List[List[str]], int, int]:
    """
    Build a (num_rows x num_cols) matrix from the cells list.
    col_span > 1: the text goes to the first column only; others stay empty.
    Returns (matrix, num_rows, num_cols).
    """
    cells = table.get("cells", [])
    num_rows = table.get("num_rows", 0)
    num_cols = table.get("num_cols", 0)

    if num_rows == 0 or num_cols == 0:
        return [], 0, 0

    matrix = [["" for _ in range(num_cols)] for _ in range(num_rows)]

    for cell in cells:
        r = cell.get("row", 0)
        c = cell.get("col", 0)
        text = str(cell.get("text", "") or "").strip()
        if 0 <= r < num_rows and 0 <= c < num_cols:
            matrix[r][c] = text

    return matrix, num_rows, num_cols


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------

HEADER_SIGNALS = [
    "description", "désignation", "designation", "libellé", "libelle",
    "item", "article", "service", "produit", "wording", "objet", "nature",
    "item description",
    "qty", "qté", "quantité", "quantite", "quantity", "nb", "nombre",
    "unit price", "prix unitaire", "pu", "tarif", "rate", "price",
    "total", "montant", "amount", "subtotal",
    "tva", "vat", "tax",
    "budget", "year to date", "current month", "omv", "etap",
    "working capital",
    "transaction date", "transaction id",
]

def find_header_end(matrix: List[List[str]], num_rows: int) -> int:
    """Return the first data row index (exclusive end of header)."""
    for r in range(min(num_rows, 5)):
        row_text = " ".join(str(c or "").lower() for c in matrix[r])
        score = sum(1 for sig in HEADER_SIGNALS if sig in row_text)
        non_empty = [str(c or "").strip() for c in matrix[r] if str(c or "").strip()]
        if not non_empty:
            continue
        numeric_count = sum(1 for v in non_empty if is_numeric(v))
        # If more than half the non-empty cells are numbers → data row
        if non_empty and numeric_count / len(non_empty) > 0.5:
            return r  # this row is already data
        if score > 0 or r == 0:
            continue  # still header
    return min(1, num_rows)


def extract_col_names(matrix: List[List[str]], header_end: int,
                      num_cols: int) -> List[str]:
    col_names = []
    for ci in range(num_cols):
        parts = []
        for ri in range(header_end):
            cell = str(matrix[ri][ci] if ci < len(matrix[ri]) else "").strip()
            if cell and cell not in parts:
                parts.append(cell)
        combined = " ".join(parts).strip()
        col_names.append(combined if combined else f"Col{ci+1}")
    return col_names


# ---------------------------------------------------------------------------
# Description column detection
# ---------------------------------------------------------------------------

DESC_SIGNALS = [
    "description", "désignation", "designation", "libellé", "libelle",
    "item", "article", "service", "produit", "wording", "objet",
    "nature", "item description"
]

def find_desc_col(col_names: List[str], matrix: List[List[str]],
                  header_end: int, num_cols: int) -> int:
    for ci, name in enumerate(col_names):
        if any(sig in name.lower() for sig in DESC_SIGNALS):
            return ci
    # Count text-heavy columns
    scores = []
    for ci in range(num_cols):
        count = sum(
            1 for ri in range(header_end, min(header_end + 20, len(matrix)))
            if (lambda v: v and not is_numeric(v) and not is_empty_cell(v))(
                str(matrix[ri][ci] if ci < len(matrix[ri]) else "").strip()
            )
        )
        scores.append(count)
    return scores.index(max(scores)) if scores else 0


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------

SECTION_KW = {
    "wells", "facilities", "other capex", "general & administration",
    "general and administration", "parent charges", "opex", "capex", "overhead",
}

TOTAL_KW = [
    "total", "subtotal", "sub total", "sous-total", "net", "grand total",
    "total expenditure", "total working capital", "balance", "credit",
    "amount due", "montant dû",
]

def is_section_header(desc: str, row_vals: List[str]) -> bool:
    d = desc.strip()
    if not d:
        return False
    other = [v for v in row_vals if v != d]
    all_empty = all(is_empty_cell(v) for v in other)
    if d.isupper() and len(d.split()) <= 4 and all_empty:
        return True
    if d.lower() in SECTION_KW and all_empty:
        return True
    return False


def is_total_row(desc: str) -> bool:
    d = desc.lower().strip()
    return any(kw in d for kw in TOTAL_KW)


# ---------------------------------------------------------------------------
# Extract items from one table
# ---------------------------------------------------------------------------

def extract_items_from_table(table: Dict) -> Tuple[List[Dict], List[str], str]:
    """
    Returns (items, value_col_names, desc_display_name).
    """
    matrix, num_rows, num_cols = resolve_matrix(table)
    if num_rows < 2 or num_cols < 1:
        return [], [], "Description"

    header_end = find_header_end(matrix, num_rows)
    if header_end >= num_rows:
        header_end = max(1, num_rows - 1)

    col_names = extract_col_names(matrix, header_end, num_cols)
    desc_col = find_desc_col(col_names, matrix, header_end, num_cols)

    # Description display name
    raw_desc = col_names[desc_col]
    DESC_ALIASES = {
        "description": "Description",
        "item description": "Item Description",
        "désignation": "Désignation",
        "designation": "Désignation",
        "libellé": "Libellé",
        "libelle": "Libellé",
        "article": "Article",
        "service": "Service",
    }
    desc_display = "Description"
    for key, val in DESC_ALIASES.items():
        if key in raw_desc.lower():
            desc_display = val
            break

    value_cols = [col_names[ci] for ci in range(num_cols) if ci != desc_col]

    items = []
    current_section = None

    for ri in range(header_end, num_rows):
        row = matrix[ri]
        row_vals = [str(row[ci] if ci < len(row) else "").strip()
                    for ci in range(num_cols)]

        if not any(v for v in row_vals):
            continue

        desc = row_vals[desc_col] if desc_col < len(row_vals) else ""

        # Skip header repetitions
        if desc.lower() in ("item description", "description", "désignation"):
            continue

        # Section header detection
        if desc and is_section_header(desc, row_vals):
            current_section = desc
            continue

        # Build valeurs
        valeurs = {}
        for ci in range(num_cols):
            if ci == desc_col:
                continue
            val = row_vals[ci] if ci < len(row_vals) else ""
            if val and not is_empty_cell(val):
                valeurs[col_names[ci]] = val

        # Handle rows with no description in desc_col
        # (e.g. Sub Total / Balance in a different column)
        if not desc:
            for ci in range(num_cols):
                if ci == desc_col:
                    continue
                val = row_vals[ci]
                if val and not is_numeric(val) and not is_empty_cell(val):
                    desc = val
                    if col_names[ci] in valeurs:
                        del valeurs[col_names[ci]]
                    break

        if not desc:
            continue

        items.append({
            "description": desc,
            "is_summary": is_total_row(desc),
            "section": current_section,
            "valeurs": valeurs,
        })

    return items, value_cols, desc_display


# ---------------------------------------------------------------------------
# Table type classification
# ---------------------------------------------------------------------------

_TYPE_SIGS = {
    "billing_detail": ["budget", "year to date", "current month expenditure", "omv", "etap"],
    "working_capital": ["working capital", "as of current month", "as of previous month"],
    "simple_invoice": ["description", "total", "amount"],
    "transaction": ["transaction date", "transaction id"],
    "summary": ["sub total", "credit", "balance"],
}

def classify_table(table: Dict) -> str:
    matrix, num_rows, num_cols = resolve_matrix(table)
    if not matrix:
        return "unknown"
    header_text = " ".join(
        str(c or "").lower()
        for row in matrix[:2]
        for c in row
    )
    scores = {
        t: sum(1 for sig in sigs if sig in header_text)
        for t, sigs in _TYPE_SIGS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(pages: List[Dict]) -> Dict[str, Any]:
    full_text_parts = []
    kv_cells = []

    for page in pages:
        for h in page.get("headers", []):
            t = h.get("text", "").strip()
            if t:
                full_text_parts.append(t)
        for kv in page.get("key_values", []):
            for cell in kv.get("cells", []):
                t = cell.get("text", "").strip()
                if t:
                    kv_cells.append(t)
                    full_text_parts.append(t)
        for cell in page.get("text_cells", []):
            t = cell.get("text", "").strip()
            if t:
                full_text_parts.append(t)
        for table in page.get("tables", []):
            for cell in table.get("cells", []):
                t = cell.get("text", "").strip()
                if t:
                    full_text_parts.append(t)

    full_text = " ".join(full_text_parts)

    meta: Dict[str, Any] = {
        "invoice_number": None,
        "date": None,
        "vendor": None,
        "client": None,
        "currency": detect_currency(full_text),
        "document_type": detect_document_type(full_text),
        "first_column_name": "Description",
        "concession": None,
        "concession_norm": None,
        "company": None,
    }

    # --- Invoice number ---
    inv_patterns = [
        r'Invoice\s*#\s*([\d\s]+)',
        r'(?:invoice|facture)\s*n[°o]?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-\.]{2,})',
        r'N[°o]\s+([A-Z][A-Z0-9/\-\.]{3,})',
        r'(?:F|INV|FAC)[\/\-]([A-Z0-9][A-Z0-9/\-\.]{3,})',
    ]
    BAD_VALS = {"date", "bill", "to", "from", "the", "de", "du", "le", "n", "no"}
    for pat in inv_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = re.sub(r'\s+', '', m.group(1).strip())
            if val.lower() not in BAD_VALS and len(val) >= 2:
                meta["invoice_number"] = val
                break

    # --- Date ---
    date_patterns = [
        r'MONTH\s+ENDED[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
        r'(?:Invoice\s*Date|Date\s*(?:de\s*)?(?:facture|émission))[^\d]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        r'(?:Date)[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
    ]
    for pat in date_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            raw_date = m.group(1).strip()
            try:
                from dateutil import parser as date_parser
                parsed = date_parser.parse(raw_date, fuzzy=True)
                meta["date"] = parsed.strftime("%Y-%m-%d")
            except Exception:
                meta["date"] = raw_date
            break

    # --- Vendor / Company ---
    # Specific known companies
    company_patterns = [
        r'(OMV[^\n,]{0,60})',
        r'((?:SONATRACH|TOTAL\s+E&P|BP|SHELL|ENI|REPSOL|CHEVRON)[^\n,]{0,40})',
    ]
    for pat in company_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            bad_words = ["sub total", "credit", "usd $", "eur $", "tnd", "$ 0", "$ 3"]
            if not any(bad in candidate.lower() for bad in bad_words):
                meta["company"] = candidate
                meta["vendor"] = candidate
                break

    # Fallback: look for business name in section_header text cells
    if not meta["vendor"]:
        skip_labels = {"invoice", "facture", "transactions", "pdf", "powered",
                       "invoiced to", "bill to", "your business"}
        for page in pages[:1]:
            for cell in page.get("text_cells", []):
                label = cell.get("label", "")
                text = cell.get("text", "").strip()
                if label == "section_header" and text and len(text) > 3:
                    if not any(s in text.lower() for s in skip_labels):
                        meta["vendor"] = text
                        meta["company"] = text
                        break
            if meta["vendor"]:
                break

    # --- Client ---
    client_re = re.compile(
        r'^(?:bill\s*to|invoiced?\s*to|acheteur|client|customer|destinataire)$',
        re.IGNORECASE
    )
    for i, txt in enumerate(kv_cells):
        if client_re.match(txt.strip()):
            parts = []
            for j in range(i+1, min(i+4, len(kv_cells))):
                c = kv_cells[j].strip()
                if client_re.match(c):
                    break
                if c and not re.match(r'^\d{5}', c) and not is_numeric(c):
                    parts.append(c)
                    if parts and not re.match(r'^\d', parts[0]):
                        break
            if parts:
                meta["client"] = " ".join(parts)
                break

    if not meta["client"]:
        for page in pages[:1]:
            for cell in page.get("text_cells", []):
                text = cell.get("text", "").strip()
                m = re.search(r'(?:Invoiced?\s+To|Bill\s+To)\s*[:\-]?\s*([^\n]+)', text, re.IGNORECASE)
                if m:
                    name = m.group(1).strip()
                    if name:
                        meta["client"] = name
                    break

    # --- Concession (OMV-specific) ---
    concession_val = None
    for i, txt in enumerate(kv_cells):
        if "concession" in txt.lower():
            after = re.split(r'[:\-]', txt, maxsplit=1)
            if len(after) > 1 and after[1].strip():
                concession_val = after[1].strip()
                break
            for j in range(i+1, min(i+4, len(kv_cells))):
                c = kv_cells[j].strip()
                if c and "concession" not in c.lower():
                    concession_val = c
                    break
            if concession_val:
                break

    if not concession_val:
        m = re.search(r'Concession\s+([A-Z][A-Za-z]+)', full_text)
        if m:
            concession_val = m.group(1).strip()

    meta["concession"] = concession_val or ""

    def _norm(text: str) -> str:
        if not text:
            return ""
        text = text.lower().strip()
        for src, dst in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),
                         ("î","i"),("ô","o"),("ù","u"),("û","u"),("ç","c")]:
            text = text.replace(src, dst)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    meta["concession_norm"] = _norm(meta["concession"]).upper()
    return meta


# ---------------------------------------------------------------------------
# Document segmentation
# ---------------------------------------------------------------------------

SECTION_START_KW = [
    "JOINT INTEREST BILLING DETAIL",
    "JOINT INTEREST ACCOUNT",
    "BILLING DETAIL",
]

def split_into_sections(pages: List[Dict]) -> List[List[Dict]]:
    sections = []
    current = []

    def _is_new_section(page: Dict) -> bool:
        for kv in page.get("key_values", []):
            for cell in kv.get("cells", []):
                text = cell.get("text", "")
                if any(kw in text for kw in SECTION_START_KW):
                    return True
        for table in page.get("tables", []):
            matrix = table.get("matrix", [])
            if matrix and matrix[0]:
                first = str(matrix[0][0] or "")
                if any(kw in first for kw in ["OMV", "PARTNER", "JOINT INTEREST"]):
                    return True
        return False

    for page in pages:
        if _is_new_section(page) and current:
            sections.append(current)
            current = []
        current.append(page)

    if current:
        sections.append(current)

    return sections if sections else [pages]


# ---------------------------------------------------------------------------
# TableGroup: merge multi-page tables
# ---------------------------------------------------------------------------

class TableGroup:
    def __init__(self, ttype: str, col_names: List[str], desc_col: int,
                 desc_display: str):
        self.ttype = ttype
        self.col_names = col_names
        self.desc_col = desc_col
        self.desc_display = desc_display
        self.items: List[Dict] = []
        self._fps: set = set()

    def _sig(self, cols: List[str]) -> List[str]:
        return [re.sub(r'\s+', ' ', c.lower().strip()) for c in cols]

    def matches(self, ttype: str, cols: List[str]) -> bool:
        if self.ttype != ttype:
            return False
        if len(self.col_names) != len(cols):
            return False
        return self._sig(self.col_names) == self._sig(cols)

    def add(self, new_items: List[Dict]):
        for item in new_items:
            fp = f"{item.get('description','')}|{sorted(item.get('valeurs',{}).items())}"
            if fp not in self._fps:
                self._fps.add(fp)
                self.items.append(item)

    @property
    def richness(self) -> float:
        if not self.items:
            return 0.0
        data = sum(
            1 for it in self.items
            for v in it.get("valeurs", {}).values()
            if has_real_value(str(v))
        )
        return len(self.items) + data * 0.5


# ---------------------------------------------------------------------------
# Process one section
# ---------------------------------------------------------------------------

def process_section(section_pages: List[Dict]) -> Dict[str, Any]:
    metadata = extract_metadata(section_pages)
    groups: List[TableGroup] = []

    for page in section_pages:
        for table in page.get("tables", []):
            matrix, num_rows, num_cols = resolve_matrix(table)
            if num_rows < 2 or num_cols < 1:
                continue

            ttype = classify_table(table)
            header_end = find_header_end(matrix, num_rows)
            if header_end >= num_rows:
                header_end = max(1, num_rows - 1)
            col_names = extract_col_names(matrix, header_end, num_cols)
            desc_col = find_desc_col(col_names, matrix, header_end, num_cols)

            items, _, desc_display = extract_items_from_table(table)
            if not items:
                continue

            matched = None
            for g in groups:
                if g.matches(ttype, col_names):
                    matched = g
                    break
            if matched is None:
                matched = TableGroup(ttype, col_names, desc_col, desc_display)
                groups.append(matched)
            matched.add(items)

    # No tables found → fallback to text
    if not groups:
        items = _text_fallback(section_pages)
        metadata["first_column_name"] = "Description"
        return {"metadata": metadata, "columns": [], "items": items}

    # Select best group
    PRIORITY = ["billing_detail", "simple_invoice", "working_capital",
                "transaction", "summary", "unknown"]
    selected = None
    for ptype in PRIORITY:
        candidates = [g for g in groups if g.ttype == ptype and g.richness > 0]
        if candidates:
            selected = max(candidates, key=lambda g: g.richness)
            break
    if selected is None:
        selected = max(groups, key=lambda g: g.richness)

    # Columns
    columns: List[str] = []
    for item in selected.items:
        for col in item.get("valeurs", {}).keys():
            if col not in columns:
                columns.append(col)

    metadata["first_column_name"] = selected.desc_display
    return {
        "metadata": metadata,
        "columns": columns,
        "items": selected.items,
    }


def _text_fallback(pages: List[Dict]) -> List[Dict]:
    items = []
    skip = {"invoice", "facture", "bill to", "ship to", "terms", "payment",
            "total in", "pdf generated", "powered by", "transactions"}
    for page in pages:
        for cell in page.get("text_cells", []):
            line = cell.get("text", "").strip()
            if not line or len(line) < 2:
                continue
            if any(s in line.lower() for s in skip):
                continue
            items.append({
                "description": line,
                "is_summary": is_total_row(line),
                "section": None,
                "valeurs": {},
            })
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def postprocess_invoice(
    raw_input: Union[str, Path, dict],
    output_path=None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Main entry point.
    Returns a single dict (one invoice) or a list of dicts (multi-invoice PDF).
    Always compatible with streamlit_app.py's expected format.
    """
    if isinstance(raw_input, (str, Path)):
        with open(raw_input, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    else:
        raw_data = raw_input

    pages: List[Dict] = raw_data.get("pages", [])
    sections = split_into_sections(pages)

    results = [process_section(s) for s in sections]

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = results[0] if len(results) == 1 else results
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved: {output_path}")

    return results[0] if len(results) == 1 else results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Universal Invoice Post-Processor v3")
    parser.add_argument('input', help="Path to extraction JSON")
    parser.add_argument('-o', '--output', help="Output JSON path")
    args = parser.parse_args()

    output_path = args.output or (Path(args.input).stem + "_postprocessed.json")
    result = postprocess_invoice(args.input, output_path)
    results = result if isinstance(result, list) else [result]

    print(f"\n📋 {len(results)} section(s) found")
    for i, res in enumerate(results):
        meta = res['metadata']
        print(f"\n--- Section {i+1} ---")
        print(f"  Type      : {meta.get('document_type')}")
        print(f"  Company   : {meta.get('company') or meta.get('vendor') or 'N/A'}")
        print(f"  Client    : {meta.get('client') or 'N/A'}")
        print(f"  Invoice # : {meta.get('invoice_number') or 'N/A'}")
        print(f"  Date      : {meta.get('date') or 'N/A'}")
        print(f"  Currency  : {meta.get('currency')}")
        print(f"  Items     : {len(res['items'])}")
        print(f"  Columns   : {res['columns']}")
        for item in res['items'][:10]:
            prefix = "  Σ " if item.get("is_summary") else "  • "
            sec = f"[{item['section']}] " if item.get("section") else ""
            vals = " | ".join(f"{k}={v}" for k, v in list(item['valeurs'].items())[:3])
            print(f"{prefix}{sec}{item['description'][:55]:<55} {vals}")


if __name__ == "__main__":
    main()
