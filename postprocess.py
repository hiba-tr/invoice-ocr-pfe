"""
postprocess.py — Universal Invoice Post-Processor (100% gratuit, sans API)
Détecte intelligemment n'importe quelle structure de facture.
"""

import json
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Constantes universelles (multilingues)
# ─────────────────────────────────────────────────────────────────────────────

# Mots-clés pour colonnes de description (FR/EN/AR/ES/DE/IT)
DESC_KEYWORDS = [
    "description", "désignation", "designation", "libellé", "libelle",
    "intitulé", "intitule", "article", "produit", "service", "item",
    "wording", "nature", "objet", "detail", "détail", "bezeichnung",
    "omschrijving", "articolo", "descripcion", "البيان", "الوصف", "التسمية"
]

# Mots-clés pour colonnes de quantité
QTY_KEYWORDS = [
    "qté", "qty", "quantité", "quantite", "quantity", "qte", "nb",
    "nombre", "nbre", "units", "unité", "unite", "menge", "antal"
]

# Mots-clés pour prix unitaire
UNIT_PRICE_KEYWORDS = [
    "pu", "pu ht", "prix unitaire", "unit price", "price", "prix",
    "tarif", "rate", "preis", "coût unitaire", "cout unitaire"
]

# Mots-clés pour montant total HT
TOTAL_HT_KEYWORDS = [
    "total ht", "montant ht", "ht", "hors taxe", "hors tva",
    "subtotal", "sous-total", "amount", "montant", "total", "betrag"
]

# Mots-clés pour TVA/taxe
TAX_KEYWORDS = [
    "tva", "vat", "tax", "taxe", "taxes", "impôt", "impot",
    "مبلغ tva", "الضريبة", "ضريبة", "steuer", "iva"
]

# Mots-clés pour total TTC
TOTAL_TTC_KEYWORDS = [
    "ttc", "total ttc", "total tva", "total tax", "net à payer",
    "net a payer", "montant ttc", "total amount", "grand total",
    "مجموع", "الإجمالي", "gesamtbetrag"
]

# Lignes de résumé (à marquer is_summary=True)
SUMMARY_KEYWORDS = [
    "subtotal", "sous-total", "total", "ttc", "ht", "tva", "vat",
    "tax", "taxe", "net", "remise", "discount", "avoir", "balance",
    "solde", "acompte", "reste", "دفع", "مجموع", "إجمالي"
]

# Mots-clés pour numéro de ligne (colonnes à ignorer)
ROW_NUM_KEYWORDS = ["n°", "n", "no", "#", "num", "ref", "réf", "id", "ligne", "item"]

# Mots à ignorer pour détecter les en-têtes (logos, titres)
IGNORE_HEADER_TEXTS = [
    "invoice", "facture", "فاتورة", "rechnung", "fattura", "factura",
    "receipt", "reçu", "bill", "devis", "quotation", "proforma",
    "credit note", "avoir", "purchase order", "bon de commande"
]

# Séparateurs de sections
SECTION_PATTERNS = [
    r'^(wells?|facilities|capex|opex|general\s*&?\s*admin)',
    r'^(devis\s*n[°o]?\s*[\w/\-]+)',
    r'^(lot\s*\d+|phase\s*\d+|section\s*\d+)',
    r'^(chapitre|chapter|partie|part)\s*\d*',
    r'^\d+\.\s+[A-Z]',
]


# ─────────────────────────────────────────────────────────────────────────────
# Nettoyage de valeurs numériques
# ─────────────────────────────────────────────────────────────────────────────

def clean_amount(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        s = re.sub(r'[\u0600-\u06FF]', '', s)
        s = re.sub(r'[$€£¥₹\u062f\u062a]', '', s)
        s = s.strip()
        if not s or s in ('-', '.', '—', '–', 'N/A', 'n/a', ''):
            return None
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        has_dot   = '.' in s
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
        try:
            f = float(s)
            return f if not (math.isnan(f) or math.isinf(f)) else None
        except ValueError:
            return None
    elif isinstance(val, (int, float)):
        f = float(val)
        return f if not (math.isnan(f) or math.isinf(f)) else None
    return None


def is_numeric_cell(text: str) -> bool:
    return clean_amount(text) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Détection de devise
# ─────────────────────────────────────────────────────────────────────────────

def detect_currency(full_text: str) -> str:
    text = full_text.upper()
    scores = {"TND": 0, "EUR": 0, "USD": 0, "GBP": 0}
    if re.search(r'\bTND\b|D\.T\b|\bDT\b|DINAR|\.ت\.د|دينار', full_text, re.IGNORECASE): scores["TND"] += 3
    if re.search(r'\bEUR\b|€|\bEURO\b', text): scores["EUR"] += 3
    if re.search(r'\bUSD\b|U\.S\.\s*DOLLAR|\$|\bDOLLAR\b', text): scores["USD"] += 3
    if re.search(r'\bGBP\b|£|\bPOUND\b', text): scores["GBP"] += 3
    if re.search(r'TUNIS|SFAX|SOUSSE|BIZERTE|NABEUL', text): scores["TND"] += 2
    if re.search(r'FRANCE|PARIS|LYON|MARSEILLE|BORDEAUX', text): scores["EUR"] += 2
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "TND"  # TND par défaut (contexte tunisien)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction de métadonnées
# ─────────────────────────────────────────────────────────────────────────────

def extract_metadata(pages: List[Dict]) -> Dict[str, Any]:
    # Collecter cellules dans l'ordre (important pour chercher "Bill To" puis cellule suivante)
    all_cells: List[str] = []
    full_text = ""
    for page in pages:
        for cell in page.get("text_cells", []):
            t = cell.get("text", "").strip()
            if t:
                all_cells.append(t)
                full_text += " " + t
        for table in page.get("tables", []):
            for cell in table.get("cells", []):
                t = cell.get("text", "").strip()
                if t:
                    all_cells.append(t)
                    full_text += " " + t

    meta: Dict[str, Any] = {
        "invoice_number": None,
        "date": None,
        "vendor": None,
        "client": None,
        "currency": detect_currency(full_text),
        "document_type": detect_document_type(full_text),
        "first_column_name": "Description",
    }

    # ── Numéro de facture (du plus précis au plus générique) ──────────────────
    BAD_VALS = {"date", "bill", "to", "from", "the", "de", "du", "le", "n", "no"}
    for pat in [
        r'(?:invoice|facture)\s*#\s*(\d+)',                                          # Invoice # 100
        r'(?:facture\s*n[°o]?|invoice\s*n[°o]?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-\.]{3,})',  # Facture N° F/05.2020/099
        r'N[°o]\s+([A-Z][A-Z0-9/\-\.]{3,})',                                        # N° F/05.2020/099
        r'(?:F|INV|FAC)[\/\-]([A-Z0-9][A-Z0-9/\-\.]{3,})',                          # F/05.2020/099
        r'#\s*(\d{2,})',                                                              # # 100
        r'(?:invoice|facture)\s+(?:n[°o]?\s*)?(\w{3,})',
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val.lower() not in BAD_VALS:
                meta["invoice_number"] = val
                break

    # ── Date ──────────────────────────────────────────────────────────────────
    for pat in [
        r'(?:Invoice\s*Date|date\s*(?:de\s*)?(?:facture|cr[eé]ation|emission|limite))[^\d]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        r'(?:dated?|le|du)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'
        r'|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t'
        r'|septembre|octobre|novembre|d[ée]cembre)\w*\s+\d{4})',
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            meta["date"] = m.group(1).strip()
            break

    # ── Fournisseur ───────────────────────────────────────────────────────────
    for pat in [
        r'(?:vendeur|vendor|seller|fournisseur|[eé]metteur)[^\n:]*[:\n]\s*([^\n:]{3,50}?)(?=\s+(?:ACHETEUR|CLIENT|N[°o]|DATE|\d{5})|$)',
        r'(?:company|soci[eé]t[eé]|entreprise)[^\n:]*[:\n]\s*([^\n,]{3,50})',
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            meta["vendor"] = m.group(1).strip()
            break

    # ── Client : chercher le mot-clé puis prendre la PROCHAINE cellule ────────
    CLIENT_TRIGGER = re.compile(
        r'^(?:bill\s*to|acheteur|client|customer|destinataire|[àa]\s+l\'?attention)$',
        re.IGNORECASE
    )
    for i, cell_text in enumerate(all_cells):
        if CLIENT_TRIGGER.match(cell_text.strip()):
            for j in range(i + 1, min(i + 4, len(all_cells))):
                candidate = all_cells[j].strip()
                # Nettoyer les trailing metadata comme "Date de création: ..."
                candidate = re.split(r'\s+(?:date|invoice|facture|n[°o]|email|t[eé]l|adresse)\b',
                                     candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                if candidate and len(candidate) > 1 and not re.match(r'^\d+$', candidate) \
                        and not CLIENT_TRIGGER.match(candidate):
                    meta["client"] = candidate
                    break
            if meta["client"]:
                break

    # Fallback client dans le texte continu
    if not meta["client"]:
        m = re.search(
            r'(?:bill\s*to|acheteur)\s*[:\-]?\s*([A-Za-z\u00C0-\u024F][^\n,\d]{2,40}?)(?=\s+\d|\s+Invoice|\s+Facture|\s*$)',
            full_text, re.IGNORECASE
        )
        if m:
            val = re.split(r'\s+(?:date|invoice|facture)\b', m.group(1), flags=re.IGNORECASE)[0].strip()
            if len(val) > 1:
                meta["client"] = val

    return meta


def detect_document_type(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["credit note", "avoir", "note de crédit"]): return "credit_note"
    if any(x in t for x in ["purchase order", "bon de commande", "p.o."]): return "purchase_order"
    if any(x in t for x in ["devis", "quotation", "quote", "pro forma", "proforma"]): return "quotation"
    if any(x in t for x in ["joint interest", "billing detail", "joint venture"]): return "billing_report"
    if any(x in t for x in ["payslip", "fiche de paie", "bulletin de salaire"]): return "payslip"
    if any(x in t for x in ["receipt", "reçu"]): return "receipt"
    return "invoice"


# ─────────────────────────────────────────────────────────────────────────────
# Analyse de structure de tableau
# ─────────────────────────────────────────────────────────────────────────────

def score_keyword(text: str, keywords: List[str]) -> int:
    t = text.lower().strip()
    return sum(1 for kw in keywords if kw in t)


def find_header_row(cell_map: Dict, num_rows: int, num_cols: int) -> int:
    """Détecte la ligne d'en-tête — fonctionne pour OMV ET les factures classiques."""
    best_row = 0
    best_score = -1

    # Mots-clés d'en-tête universels (FR + EN)
    HEADER_SIGNALS = [
        "description", "désignation", "designation", "item", "libellé",
        "budget", "expenditure", "omv", "etap",          # OMV
        "qté", "qty", "quantité", "quantity",             # factures classiques
        "pu", "pu ht", "prix unitaire", "unit price",
        "total ht", "total ttc", "montant", "tva", "vat",
        "n°", "réf", "ref",
    ]

    for r in range(min(num_rows, 12)):
        row_text = " ".join(
            cell_map.get((r, c), {}).get("text", "").lower()
            for c in range(num_cols)
        )
        score = sum(1 for sig in HEADER_SIGNALS if sig in row_text)
        # Bonus si plusieurs colonnes de la ligne sont non-vides (ligne dense = header)
        filled = sum(1 for c in range(num_cols) if cell_map.get((r, c), {}).get("text", "").strip())
        score += filled * 0.5

        if score > best_score:
            best_score = score
            best_row = r

    return best_row


def classify_column(header: str, col_idx: int, num_cols: int, cell_map: Dict,
                    num_rows: int, header_row: int) -> str:
    """Classifie une colonne selon son en-tête ET le contenu de ses cellules."""
    h = header.lower().strip()

    # Par en-tête
    if score_keyword(h, ROW_NUM_KEYWORDS) and col_idx == 0: return "row_num"
    if score_keyword(h, DESC_KEYWORDS): return "description"
    if score_keyword(h, QTY_KEYWORDS): return "qty"
    if score_keyword(h, UNIT_PRICE_KEYWORDS): return "unit_price"
    if score_keyword(h, TOTAL_TTC_KEYWORDS): return "total_ttc"
    if score_keyword(h, TAX_KEYWORDS): return "tax"
    if score_keyword(h, TOTAL_HT_KEYWORDS): return "total_ht"

    # Par contenu : si la majorité des cellules sont numériques → colonne valeur
    if not h:  # Pas d'en-tête ? Analyser le contenu
        numeric_count = sum(
            1 for r in range(header_row + 1, num_rows)
            if is_numeric_cell(cell_map.get((r, col_idx), {}).get("text", ""))
        )
        data_rows = num_rows - header_row - 1
        if data_rows > 0 and numeric_count / data_rows > 0.5:
            return "value"

    return "value"


def find_desc_col(headers: List[str], cell_map: Dict, num_rows: int,
                  header_row: int, num_cols: int) -> int:
    """Trouve la colonne de description la plus probable."""
    # 1. Chercher par mots-clés d'en-tête
    for ci, h in enumerate(headers):
        if score_keyword(h.lower(), DESC_KEYWORDS) > 0:
            return ci

    # 2. Chercher la colonne avec le plus de texte non-numérique
    text_scores = []
    for ci in range(num_cols):
        col_type = classify_column(headers[ci] if ci < len(headers) else "",
                                   ci, num_cols, cell_map, num_rows, header_row)
        if col_type == "row_num":
            text_scores.append(-1)
            continue
        text_count = sum(
            1 for r in range(header_row + 1, num_rows)
            if cell_map.get((r, ci), {}).get("text", "").strip()
            and not is_numeric_cell(cell_map.get((r, ci), {}).get("text", ""))
        )
        text_scores.append(text_count)

    return text_scores.index(max(text_scores)) if text_scores else 0


def is_section_row(text: str) -> bool:
    """Détermine si une ligne est un séparateur de section."""
    t = text.strip()
    if not t or len(t) < 2:
        return False
    for pat in SECTION_PATTERNS:
        if re.match(pat, t, re.IGNORECASE):
            return True
    # Une ligne avec uniquement du texte en gras/majuscule sans montant
    if t.isupper() and len(t.split()) <= 6 and not is_numeric_cell(t):
        return True
    return False


def split_merged_cell(text: str) -> Tuple[str, Optional[float]]:
    """
    Sépare une cellule fusionnée 'description + montant'.
    Ex: 'jouet 500.25' -> ('jouet', 500.25)
        'tva 0.18% 0.94' -> ('tva 0.18%', 0.94)
        'TOTAL د.ت 525.19' -> ('TOTAL', 525.19)
    """
    t = re.sub(r'[\u0600-\u06FF\s\.]+', ' ', text.strip()).strip()
    t = re.sub(r'\s*(USD|EUR|TND|DT)\s*', ' ', t, flags=re.IGNORECASE).strip()

    # Montant en fin : "description 500.25"
    m = re.match(r'^(.*?)\s+(-?\d[\d\s,\.]*)\s*$', t)
    if m:
        desc = m.group(1).strip()
        amt  = clean_amount(m.group(2))
        if desc and amt is not None:
            return desc, amt

    # Montant en début : "500.25 description"
    m2 = re.match(r'^(-?\d[\d\s,\.]*)\s+(.+)$', t)
    if m2:
        amt  = clean_amount(m2.group(1))
        desc = m2.group(2).strip()
        if desc and amt is not None:
            return desc, amt

    return text.strip(), None

# ─────────────────────────────────────────────────────────────────────────────
# NOUVELLE FONCTION : Détection intelligente des noms de colonnes
# ─────────────────────────────────────────────────────────────────────────────
# Noms de colonnes OMV connus (pour reconstruction si headers sur 2 lignes)
OMV_COLUMNS = [
    "Item Description",
    "Budget 2025",
    "YTD Expenditure As of Current Month",
    "YTD Expenditure As of Previous Month",
    "Current Month Expenditure 100%",
    "OMV (Tunesien) Production Share @ 50%",
    "ETAP Share @ 50%",
]

def _is_omv_table(cell_map: Dict, num_rows: int, num_cols: int) -> bool:
    """Détecte si le tableau est de type OMV/billing report."""
    full_text = " ".join(
        cell_map.get((r, c), {}).get("text", "").lower()
        for r in range(min(num_rows, 5))
        for c in range(num_cols)
    )
    omv_signals = ["omv", "etap", "expenditure", "budget 2025", "waha", "cherouq"]
    return sum(1 for s in omv_signals if s in full_text) >= 2


def detect_real_column_names(headers: List[str], cell_map: Dict, num_rows: int,
                             header_row: int, num_cols: int) -> List[str]:
    """
    Détecte dynamiquement les noms de colonnes depuis les headers réels du tableau.
    - Si c'est un tableau OMV avec headers sur 2 lignes : utilise OMV_COLUMNS
    - Sinon : lit les vraies cellules d'en-tête du tableau
    """
    # Cas OMV : headers étalés sur 2 lignes, utiliser les noms connus
    if _is_omv_table(cell_map, num_rows, num_cols):
        return OMV_COLUMNS[:num_cols]

    # Cas général : lire les cellules d'en-tête réelles
    real_headers = []
    for c in range(num_cols):
        # Chercher le header sur les 3 premières lignes (certains tableaux ont 2 lignes de header)
        parts = []
        for r in range(min(3, header_row + 1)):
            cell_text = cell_map.get((r, c), {}).get("text", "").strip()
            if cell_text and cell_text not in parts:
                parts.append(cell_text)
        combined = " ".join(parts).strip()
        real_headers.append(combined if combined else f"Col{c+1}")

    return real_headers
# ─────────────────────────────────────────────────────────────────────────────
# Détection de type de tableau
# ─────────────────────────────────────────────────────────────────────────────

def detect_table_layout(cell_map, num_rows, num_cols, header_row) -> str:
    """
    Détecte le layout du tableau :
    - 'merged'  : cellules fusionnées (description+montant dans une cellule)
    - 'normal'  : colonnes séparées classiques
    - 'two_col' : 2 colonnes seulement (description | montant)
    - 'info'    : tableau d'informations (pas de lignes d'articles)
    """
    if num_cols <= 1:
        return "merged"

    # Tableau info : contient des paires clé/valeur comme "Invoice # | 100"
    info_kw = ["bill to", "invoice #", "invoice date", "client", "adresse",
               "date", "numéro", "numero", "téléphone", "telephone", "email",
               "fournisseur", "vendeur", "acheteur"]
    info_score = sum(
        1 for r in range(num_rows) for c in range(num_cols)
        if any(kw in cell_map.get((r, c), {}).get("text", "").lower() for kw in info_kw)
    )
    if info_score >= 3:
        return "info"

    # Tableau 2 colonnes : description | montant
    if num_cols == 2:
        numeric_in_col1 = sum(
            1 for r in range(header_row + 1, num_rows)
            if is_numeric_cell(cell_map.get((r, 1), {}).get("text", ""))
        )
        if numeric_in_col1 > 0:
            return "two_col"

    # Tableau fusionné : cellules qui s'étendent sur toute la largeur
    merged_votes = sum(
        1 for r in range(header_row + 1, num_rows)
        if cell_map.get((r, 0), {}).get("col_span", 1) >= max(2, num_cols - 1)
        and split_merged_cell(cell_map.get((r, 0), {}).get("text", ""))[1] is not None
    )
    data_rows = max(1, num_rows - header_row - 1)
    if merged_votes / data_rows > 0.4:
        return "merged"

    return "normal"


# ─────────────────────────────────────────────────────────────────────────────
# Extraction des lignes
# ─────────────────────────────────────────────────────────────────────────────

def extract_table_items(table: Dict) -> Tuple[List[Dict], str]:
    cells = table.get("cells", [])
    num_rows = table.get("num_rows", 0)
    num_cols = table.get("num_cols", 0)
    if num_rows == 0 or num_cols == 0:
        return [], "Item Description"

    cell_map = {(c.get("row", 0), c.get("col", 0)): c for c in cells}
    header_row = find_header_row(cell_map, num_rows, num_cols)

    # Lire les headers bruts depuis la ligne d'en-tête détectée
    raw_headers = [
        cell_map.get((header_row, c), {}).get("text", "").strip()
        for c in range(num_cols)
    ]
    headers = detect_real_column_names(raw_headers, cell_map, num_rows, header_row, num_cols)

    # Trouver la colonne description dynamiquement
    desc_col = find_desc_col(headers, cell_map, num_rows, header_row, num_cols)

    items = []
    current_section = None

    for r in range(header_row + 1, num_rows):
        row_vals = [cell_map.get((r, c), {}).get("text", "").strip() for c in range(num_cols)]
        if not any(row_vals):
            continue

        desc = row_vals[desc_col].strip()
        if not desc and len(row_vals) > 1:
            desc = row_vals[1].strip()

        if not desc or desc.lower() in ["item description", "description", "wells"]:
            continue

        # Détection des sections
        if desc.isupper() or len(desc.split()) <= 6:
            section_keywords = ["WELLS", "FACILITIES", "OTHER CAPEX", "GENERAL", "PARENT", "TOTAL"]
            if any(kw in desc.upper() for kw in section_keywords):
                current_section = desc
                continue

        # Nettoyage léger du texte (optionnel)
        desc = desc.replace("Faeilities", "Facilities").replace("Fanh2", "Farah 2")

        is_sum = any(kw in desc.lower() for kw in SUMMARY_KEYWORDS)

        valeurs = {}
        for ci in range(1, len(row_vals)):
            num = clean_amount(row_vals[ci])
            if num is not None:
                col_name = headers[ci] if ci < len(headers) else f"Col{ci}"
                valeurs[col_name] = num

        items.append({
            "description": desc,
            "is_summary": is_sum,
            "section": current_section,
            "valeurs": valeurs,
        })

    return items, "Item Description"

def extract_text_cell_items(pages: List[Dict]) -> List[Dict]:
    """Fallback : extraire depuis les cellules de texte libres."""
    items = []
    skip_kw = ["description", "amount", "invoice", "facture", "fatura",
               "bill to", "ship to", "terms", "payment"]
    for page in pages:
        for cell in page.get("text_cells", []):
            line = cell.get("text", "").strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in skip_kw):
                continue
            desc, amt = split_merged_cell(line)
            is_sum = any(kw in desc.lower() for kw in SUMMARY_KEYWORDS)
            items.append({
                "description": desc,
                "is_summary": is_sum,
                "section": None,
                "valeurs": {"Montant": amt} if amt is not None else {}
            })
    return items


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────

def postprocess_invoice(
    raw_input: Union[str, Path, dict],
    output_path=None,
) -> Dict[str, Any]:
    if isinstance(raw_input, (str, Path)):
        with open(raw_input, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    else:
        raw_data = raw_input

    pages: List[Dict] = raw_data.get("pages", [])
    metadata = extract_metadata(pages)

    # Extraire depuis tous les tableaux
    all_items = []
    first_col_name = "Description"
    for page in pages:
        for table in page.get("tables", []):
            items, col_name = extract_table_items(table)
            if items:
                all_items.extend(items)
                first_col_name = col_name

    # Fallback sur texte libre si aucun tableau utile
    if not all_items:
        all_items = extract_text_cell_items(pages)

    metadata["first_column_name"] = first_col_name

    # Collecter toutes les colonnes détectées
    columns: List[str] = []
    for item in all_items:
        for col in item["valeurs"].keys():
            if col not in columns:
                columns.append(col)

    result = {
        "metadata": metadata,
        "columns":  columns,
        "items":    all_items,
    }

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ Résultat sauvegardé dans: {output_path}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Universal Invoice Post-Processor (gratuit, sans API)"
    )
    parser.add_argument('input',  help="Chemin vers le JSON d'extraction")
    parser.add_argument('-o', '--output', help="Chemin de sortie JSON")
    args = parser.parse_args()

    output_path = args.output or (Path(args.input).stem + "_structure.json")
    result = postprocess_invoice(args.input, output_path)

    print("\n📋 RÉSULTAT:")
    meta = result['metadata']
    print(f"  Type       : {meta.get('document_type', 'N/A')}")
    print(f"  Fournisseur: {meta.get('vendor') or 'N/A'}")
    print(f"  Client     : {meta.get('client') or 'N/A'}")
    print(f"  Facture #  : {meta.get('invoice_number') or 'N/A'}")
    print(f"  Date       : {meta.get('date') or 'N/A'}")
    print(f"  Devise     : {meta.get('currency', 'N/A')}")
    print(f"\n  {len(result['items'])} ligne(s) extraite(s):")

    seen_cols: list = []
    for item in result['items']:
        for col in item['valeurs'].keys():
            if col not in seen_cols:
                seen_cols.append(col)

    first_col = meta.get('first_column_name', 'Description')
    header = f"  {'':2}  {first_col:<35}"
    for col in seen_cols:
        header += f"  {col:>14}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for item in result['items']:
        prefix  = "  Σ " if item.get("is_summary") else "  • "
        section = f"[{item['section']}] " if item.get("section") else ""
        line    = f"{prefix} {section}{item['description']:<35}"
        for col in seen_cols:
            val = item['valeurs'].get(col)
            if isinstance(val, float):
                val_str = f"{val:.2f}"
            elif val is None:
                val_str = "—"
            else:
                val_str = str(val)
            line += f"  {val_str:>14}"
        print(line)


if __name__ == "__main__":
    main()