"""
postprocess/invoice/header_extractor.py
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.ocr_corrector import clean_text
from ..models import DocumentIdentity

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Mapping mois multilingue
# ─────────────────────────────────────────────────────────────────────────────
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "janv": 1, "févr": 2, "fév": 2, "avr": 4, "juil": 7,
    "aoû": 8, "sept": 9, "déc": 12,
}

# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 4 — Patterns numéro de facture resserrés
# ─────────────────────────────────────────────────────────────────────────────
_INVOICE_NUM_PATTERNS = [
    re.compile(
        r"(?:invoice|facture|fac|fact|bill)\s*(?:n[°o]|num(?:ber|éro)?|ref(?:erence)?|#)?\s*[:\-]?\s*([\w/\-]{3,30})",
        re.I,
    ),
    re.compile(
        r"(?:n[°o]|num(?:ber|éro)?)\s*(?:de\s+)?(?:facture|invoice)\s*[:\-]?\s*([\w/\-]{3,30})",
        re.I,
    ),
    re.compile(r"\b((?:FAC|INV|FACT|BL|BC|PO|SO)[/\-]?[\w\-]{2,20})\b"),
    re.compile(r"N°\s*([\w/\-]{3,20})", re.I),
]

# Blacklist pour rejeter montants / devises / mots financiers
_INVOICE_NUM_BLACKLIST = re.compile(
    r"^[\d.,\s]+$"
    r"|^(EUR|USD|GBP|TND|MAD|DZD|CHF)$"
    r"|^(TOTAL|NET|TVA|TAX|HT|TTC|VAT)$",
    re.I,
)

_DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b"),
    re.compile(r"\b(\w+)\s+(\d{4})\b"),
    re.compile(r"\b(\d{4})[/-](\d{2})[/-](\d{2})\b"),
    re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b"),
    re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{2})\b"),
]

_CURRENCY_SYMBOLS = [
    (re.compile(r'€'), "EUR"),
    (re.compile(r'\$'), "USD"),
    (re.compile(r'£'), "GBP"),
    (re.compile(r'¥'), "JPY"),
    (re.compile(r'CHF\b', re.I), "CHF"),
    (re.compile(r'CAD\b', re.I), "CAD"),
    (re.compile(r'AUD\b', re.I), "AUD"),
    (re.compile(r'MAD\b', re.I), "MAD"),
    (re.compile(r'DZD\b', re.I), "DZD"),
    (re.compile(r'TND\b', re.I), "TND"),
    (re.compile(r'\bEUR\b|\bEUROS?\b', re.I), "EUR"),
    (re.compile(r'\bUSD\b|\bU\.?S\.?\s*DOLLARS?\b', re.I), "USD"),
    (re.compile(r'\bGBP\b|\bPOUND\b|\bSTERLING\b', re.I), "GBP"),
    (re.compile(r'\bJPY\b|\bYEN\b', re.I), "JPY"),
    (re.compile(r'\bTND\b|\bDINAR\s+TUNISIEN\b', re.I), "TND"),
    (re.compile(r'\bDZD\b|\bDINAR\s+ALGERIEN\b', re.I), "DZD"),
    (re.compile(r'\bMAD\b|\bDIRHAM\b', re.I), "MAD"),
]

_SUPPLIER_LABELS = re.compile(
    r"(?:fournisseur|supplier|vendor|émis\s+par|issued\s+by|from|vendeur|"
    r"société|company|entreprise|prestataire|nom\s+de\s+la\s+société)\s*[:#]?",
    re.I,
)
_CLIENT_LABELS = re.compile(
    r"(?:client|customer|bill\s+to|sold\s+to|facturé\s+à|destinataire)\s*[:#]?",
    re.I,
)
_PERIOD_LABELS = re.compile(
    r"(?:period|période|month\s+ended|mois\s+de|date\s+de\s+facture|"
    r"invoice\s+date|date|du|au)\s*[:#]?",
    re.I,
)
_INVOICE_NUM_LABELS = re.compile(
    r"(?:invoice|facture|n°|ref|référence|numéro|number|no\.?)\s*[:#]?",
    re.I,
)


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation de la période  (inchangée)
# ─────────────────────────────────────────────────────────────────────────────
def normalize_period(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()

    m = re.search(r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b", text, re.I)
    if m:
        month_num = _MONTH_MAP.get(m.group(2).lower())
        if month_num:
            return f"{m.group(3)}-{month_num:02d}-{int(m.group(1)):02d}"

    m = re.search(r"\b(\w+)\s+(\d{4})\b", text, re.I)
    if m:
        month_num = _MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return f"{m.group(2)}-{month_num:02d}"

    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{2})$", text)
    if m:
        day, month, year = m.groups()
        year_full = 2000 + int(year) if int(year) < 50 else 1900 + int(year)
        return f"{year_full}-{month}-{day}"

    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return text

    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    m = re.match(r"(\d{4})-(\d{2})$", text)
    if m:
        return text

    return None


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 3 — _collect_all_text : headers/footers en tête
# ─────────────────────────────────────────────────────────────────────────────
def _collect_all_text(pages: List[Dict], tables: Optional[List[Dict]] = None) -> str:
    header_footer_parts: List[str] = []
    body_parts: List[str] = []

    for page in pages:
        # Headers et footers en premier — zone riche en métadonnées
        for zone in ("headers", "footers"):
            for h in page.get(zone, []):
                t = h.get("text", "").strip()
                if t:
                    header_footer_parts.append(t)

        # Texte brut de la page
        raw = page.get("raw_text", "").strip()
        if raw:
            body_parts.append(raw)

        # Cellules kv_regions
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                t = cell.get("text", "").strip()
                if t:
                    body_parts.append(t)

    # Tables brutes
    if tables:
        for table in tables:
            for row in table.get("matrix", []):
                for cell in row:
                    if cell:
                        body_parts.append(str(cell))

    # Headers/footers en tête → priorité dans les recherches séquentielles
    all_parts = header_footer_parts + body_parts
    return " \n ".join(p for p in all_parts if p)


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 5 — Texte header/footer seul pour recherche prioritaire
# ─────────────────────────────────────────────────────────────────────────────
def _collect_header_footer_text(pages: List[Dict]) -> str:
    parts = []
    for page in pages:
        for zone in ("headers", "footers"):
            for h in page.get(zone, []):
                t = h.get("text", "").strip()
                if t:
                    parts.append(t)
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 1 — _find_in_kv_by_label : tolérance ±30px, portée 10 cellules
# ─────────────────────────────────────────────────────────────────────────────
def _find_in_kv_by_label(pages: List[Dict], label_pattern: re.Pattern) -> Optional[str]:
    for page in pages:
        for kv in page.get("kv_regions", []):
            cells = kv.get("cells", [])
            for i, cell in enumerate(cells):
                text = cell.get("text", "")
                if not label_pattern.search(text):
                    continue

                label_bbox = cell.get("bbox") or {}
                label_t = label_bbox.get("t", 0)
                label_b = label_bbox.get("b", label_t + 20)
                label_r = label_bbox.get("r", 0)

                # Chercher jusqu'à 10 cellules suivantes (au lieu de 5)
                for j in range(i + 1, min(i + 10, len(cells))):
                    next_cell = cells[j]
                    next_bbox = next_cell.get("bbox") or {}
                    next_t = next_bbox.get("t", 0)
                    next_l = next_bbox.get("l", 0)
                    val_text = next_cell.get("text", "").strip()

                    if not val_text or label_pattern.search(val_text):
                        continue

                    # Même ligne : tolérance ±30px
                    if abs(next_t - label_t) < 30 and next_l >= label_r - 10:
                        return clean_text(val_text)

                    # Ligne juste en dessous : tolérance 0–50px
                    if 0 < next_t - label_b < 50:
                        return clean_text(val_text)

    return None


try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


def _find_date_in_text(text: str) -> Optional[str]:
    if not text:
        return None

    if HAS_DATEUTIL:
        words = text.split()
        for length in range(1, 7):
            for i in range(len(words) - length + 1):
                candidate = ' '.join(words[i:i + length])
                candidate_clean = re.sub(r'[^\w\s/-]', '', candidate).strip()
                if not candidate_clean:
                    continue
                try:
                    dt = dateutil_parser.parse(candidate_clean, fuzzy=False, dayfirst=True)
                    if 2000 <= dt.year <= 2099:
                        return candidate_clean
                except Exception:
                    continue

    patterns = [
        r'\b(\d{1,2})\s+(jan(?:uary|vier)?|feb(?:ruary|rier)?|mar(?:ch|s)?|apr(?:il)?|avr(?:il)?|may|mai|jun(?:e|i)?|jul(?:y|let)?|aug(?:ust)?|aoû(?:t)?|sep(?:tember|tembre)?|oct(?:ober|obre)?|nov(?:ember|embre)?|dec(?:ember|embre)?|déc(?:embre)?)\.?\s+(\d{4})\b',
        r'\b(jan(?:uary|vier)?|feb(?:ruary|rier)?|mar(?:ch|s)?|apr(?:il)?|avr(?:il)?|may|mai|jun(?:e|i)?|jul(?:y|let)?|aug(?:ust)?|aoû(?:t)?|sep(?:tember|tembre)?|oct(?:ober|obre)?|nov(?:ember|embre)?|dec(?:ember|embre)?|déc(?:embre)?)\.?\s+(\d{4})\b',
        r'\b(\d{4})[/-](\d{2})[/-](\d{2})\b',
        r'\b(\d{2})[/-](\d{2})[/-](\d{4})\b',
        r'\b(\d{2})[/-](\d{2})[/-](\d{2})\b',
        r'\b(\d{4})\.(\d{2})\.(\d{2})\b',
        r'\b(\d{2})\.(\d{2})\.(\d{4})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    ultime = re.search(r'\b(\d{2}[-/.]?\d{2}[-/.]?\d{4}|\d{4}[-/.]?\d{2}[-/.]?\d{2})\b', text)
    if ultime:
        return ultime.group(0)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 2 — _find_date_contextual : bug next() corrigé + mois FR
# ─────────────────────────────────────────────────────────────────────────────
_DATE_LABEL_KEYWORDS = [
    "date", "période", "period", "invoice date", "facturée le",
    "du ", "au ", "mois de", "month ended", "billing period",
    "date de facture", "date facture",
]

_DATE_FRAGMENT_RE = re.compile(
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})"
    r"|(\d{4}[/\-.]\d{2}[/\-.]\d{2})"
    r"|(\d{1,2}\s+(?:jan|fév|feb|mar|avr|apr|mai|may|jun|jul|aoû|aug|sep|oct|nov|déc|dec)[a-zé]*\.?\s+\d{2,4})"
    r"|((?:jan|fév|feb|mar|avr|apr|mai|may|jun|jul|aoû|aug|sep|oct|nov|déc|dec)[a-zé]*\.?\s+\d{4})",
    re.IGNORECASE,
)

def _find_date_contextual(text: str) -> Optional[str]:
    if not text:
        return None

    candidates: List[tuple] = []

    for line in text.split("\n"):
        line_clean = line.strip()
        if not line_clean:
            continue

        has_label = any(kw in line_clean.lower() for kw in _DATE_LABEL_KEYWORDS)
        priority = 10 if has_label else 0

        for m in _DATE_FRAGMENT_RE.finditer(line_clean):
            # CORRECTION : next() sur les groupes du match, pas sur un tuple
            fragment = next((g for g in m.groups() if g), None)
            if fragment:
                candidates.append((priority, len(fragment), fragment.strip()))

    if not candidates:
        return None

    # Priorité décroissante, puis longueur décroissante
    candidates.sort(key=lambda x: (-x[0], -x[1]))
    return candidates[0][2]


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 4 — _find_invoice_number_in_text : validation renforcée
# ─────────────────────────────────────────────────────────────────────────────
def _find_invoice_number_in_text(text: str) -> Optional[str]:
    for pat in _INVOICE_NUM_PATTERNS:
        for m in pat.finditer(text):
            num = m.group(1).strip()
            if len(num) < 3 or _INVOICE_NUM_BLACKLIST.match(num):
                continue
            # Doit contenir au moins un chiffre
            if not re.search(r"\d", num):
                continue
            return num
    return None


def _find_supplier_in_kv(pages: List[Dict]) -> Optional[str]:
    supplier_label_re = re.compile(
        r"(fournisseur|supplier|vendor|émis\s+par|issued\s+by|vendeur)\s*[:#]?", re.I
    )
    result = _find_in_kv_by_label(pages, supplier_label_re)
    if result:
        return result

    for page in pages:
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                if cell.get("semantic_class") == "company":
                    return clean_text(cell.get("text", ""))

    candidates = []
    for page in pages:
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                t = cell.get("text", "").strip()
                if not t:
                    continue
                if re.search(r"\b(TVA|TAX|TOTAL|INVOICE|FACTURE|DATE|PAGE|REF|N°)\b", t, re.I):
                    continue
                if t.isupper() and len(t) > 4 and not re.match(r"^[\d\s\-/]+$", t):
                    candidates.append(t)

    if candidates:
        return max(candidates, key=len)
    return None


def _find_concession_in_kv(pages: List[Dict]) -> Optional[str]:
    concession_label_re = re.compile(r"\bconcession\b", re.I)
    for page in pages:
        for kv in page.get("kv_regions", []):
            cells = kv.get("cells", [])
            for i, cell in enumerate(cells):
                if concession_label_re.search(cell.get("text", "")):
                    label_bbox = cell.get("bbox") or {}
                    label_x = label_bbox.get("l", 999)
                    candidates = []
                    for c2 in cells:
                        if c2.get("semantic_class") == "code_or_name":
                            c2_x = (c2.get("bbox") or {}).get("l", 0)
                            if abs(c2_x - label_x) <= 15:
                                candidates.append((c2_x, c2.get("text", "")))
                    if candidates:
                        candidates.sort(key=lambda x: abs(x[0] - label_x))
                        return candidates[0][1]
    return None


def _find_currency_in_pages(
    pages: List[Dict], all_text: str, tables: Optional[List[Dict]] = None
) -> str:
    for pattern, currency in _CURRENCY_SYMBOLS:
        if pattern.search(all_text):
            return currency
    if tables:
        for table in tables:
            for row in table.get("matrix", []):
                for cell in row:
                    if cell:
                        for pattern, currency in _CURRENCY_SYMBOLS:
                            if pattern.search(str(cell)):
                                return currency
    return "USD"


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION 5 — extract_identity : headers/footers prioritaires
# ─────────────────────────────────────────────────────────────────────────────
def extract_identity(
    doc_info: Dict[str, Any],
    pages: List[Dict],
    metadata: Dict[str, Any],
    known_suppliers: Optional[List[str]] = None,
    all_text: Optional[str] = None,
) -> DocumentIdentity:
    if all_text is None:
        all_text = _collect_all_text(pages, None)

    # Texte header/footer seul — prioritaire pour date et numéro de facture
    hf_text = _collect_header_footer_text(pages)

    # ── Période ────────────────────────────────────────────────────────────────
    period = (
        doc_info.get("period")
        or doc_info.get("date")
        or _find_in_kv_by_label(pages, _PERIOD_LABELS)
        or _find_date_contextual(hf_text)      # headers/footers en premier
        or _find_date_contextual(all_text)     # puis texte complet
        or _find_date_in_text(hf_text)         # fallback regex sur hf
        or _find_date_in_text(all_text)        # fallback regex global
    )
    period = clean_text(period) if period else None
    period_normalized = normalize_period(period) if period else None

    # ── Numéro de facture ──────────────────────────────────────────────────────
    invoice_number = (
        doc_info.get("invoice_number")
        or _find_in_kv_by_label(pages, _INVOICE_NUM_LABELS)
        or _find_invoice_number_in_text(hf_text)   # headers/footers prioritaires
        or _find_invoice_number_in_text(all_text)
    )
    invoice_number = clean_text(invoice_number) if invoice_number else None

    # ── Société ────────────────────────────────────────────────────────────────
    company = doc_info.get("company") or _find_supplier_in_kv(pages)
    if not company and known_suppliers:
        try:
            from rapidfuzz import fuzz, process as fuzz_process
            match = fuzz_process.extractOne(
                all_text, known_suppliers, scorer=fuzz.partial_ratio, score_cutoff=75
            )
            if match:
                company = match[0]
        except ImportError:
            pass
    company = clean_text(company) if company else None

    # ── Type de document ───────────────────────────────────────────────────────
    document_type = (
        doc_info.get("document_type")
        or _find_in_kv_by_label(pages, re.compile(r"(?:type|nature|objet)\s*[:#]?", re.I))
    )
    if not document_type:
        for kw, label in [
            ("joint interest billing", "Joint Interest Billing"),
            ("purchase order", "Purchase Order"),
            ("bon de commande", "Bon de commande"),
            ("devis", "Devis"),
            ("avoir", "Avoir"),
            ("credit note", "Credit Note"),
        ]:
            if kw.lower() in all_text.lower():
                document_type = label
                break
        if not document_type:
            m = re.search(
                r"\b(INVOICE|FACTURE|DEVIS|QUOTATION|CREDIT\s+NOTE|BON\s+DE\s+COMMANDE)\b",
                all_text, re.I,
            )
            if m:
                document_type = m.group(1).title()
    document_type = clean_text(document_type) if document_type else None

    # ── Concession ─────────────────────────────────────────────────────────────
    concession = doc_info.get("concession") or _find_concession_in_kv(pages)
    concession = clean_text(concession) if concession else None

    # ── DocuSign ID ────────────────────────────────────────────────────────────
    docusign_id = doc_info.get("docusign_id")
    if not docusign_id:
        m = re.search(r"docusign\s+envelope\s+id\s*:\s*([A-F0-9\-]{30,})", all_text, re.I)
        if m:
            docusign_id = m.group(1).strip()

    # ── Devise ─────────────────────────────────────────────────────────────────
    currency = _find_currency_in_pages(pages, all_text, tables=None)

    # ── Total pages ────────────────────────────────────────────────────────────
    total_pages = doc_info.get("total_pages_in_doc")
    if not total_pages:
        for page in pages:
            for zone in ("headers", "footers"):
                for h in page.get(zone, []):
                    txt = h.get("text", "")
                    m = re.search(r"\b(\d+)\s+of\s+(\d+)\b", txt, re.I)
                    if m:
                        total_pages = int(m.group(2))
                        break
                    m = re.search(r"page\s+\d+\s*/\s*(\d+)", txt, re.I)
                    if m:
                        total_pages = int(m.group(1))
                        break
                if total_pages:
                    break
            if total_pages:
                break

    _log.info(
        f"[HeaderExtractor] company={company} | period={period} | "
        f"invoice_number={invoice_number} | currency={currency}"
    )

    return DocumentIdentity(
        company=company,
        concession=concession,
        document_type=document_type,
        period=period,
        period_normalized=period_normalized,
        docusign_id=docusign_id,
        total_pages=total_pages,
        pages_processed=metadata.get("page_count", 0),
        source_file=str(Path(metadata.get("file", "")).name) if metadata.get("file") else None,
        document_hash=metadata.get("document_hash"),
        extraction_status=metadata.get("status", "unknown"),
        currency=currency,
        invoice_number=invoice_number,
    )