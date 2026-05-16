"""
postprocess/invoice/header_extractor.py
=========================================
Extraction générique des métadonnées de facture.

Stratégie multi-sources (par ordre de priorité) :
  1. document_info du bridge (déjà extrait)
  2. kv_regions (régions clé-valeur détectées par Docling)
  3. headers de page (en-têtes/pieds de page)
  4. raw_text (texte brut complet — fallback regex)

Entièrement générique : fonctionne pour JIB pétrolier, factures commerciales,
devis, bons de commande, etc.
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
    "janv": 1, "févr": 2, "avr": 4, "juil": 7, "sept": 9, "oct": 10, "déc": 12,
}

# ─────────────────────────────────────────────────────────────────────────────
# Patterns de détection
# ─────────────────────────────────────────────────────────────────────────────

# Numéro de facture — patterns courants multilingues
_INVOICE_NUM_PATTERNS = [
    re.compile(r"(?:invoice|facture|fac|fact|bill|n°facture|n°\s*fac)\s*[:#]?\s*([\w/\-]+)", re.I),
    re.compile(r"(?:ref|reference|réf|numéro)\s*[:#]?\s*([\w/\-]+)", re.I),
    re.compile(r"(?:FAC|INV|FACT|BL|BC|PO|SO)\s*[-#]?\s*([\w/\-]+)", re.I),
    re.compile(r"N°\s*([\w/\-]+)", re.I),
]

# Date / Période — formats multiples
_DATE_PATTERNS = [
    # "31 January 2025", "1 Janvier 2025"
    re.compile(r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b"),
    # "January 2025", "Janvier 2025"
    re.compile(r"\b(\w+)\s+(\d{4})\b"),
    # "2025-01-31", "31/01/2025", "01-31-2025"
    re.compile(r"\b(\d{4})[/-](\d{2})[/-](\d{2})\b"),
    re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b"),
    # "31/01/25"
    re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{2})\b"),
]

# Devise
_CURRENCY_PATTERNS = [
    (re.compile(r'\bUSD\b|\bU\.S\.\s*DOLLARS?\b', re.I), "USD"),
    (re.compile(r'\bEUR\b|\bEUROS?\b|\b€\b', re.I), "EUR"),
    (re.compile(r'\bTND\b|\bDINAR', re.I), "TND"),
    (re.compile(r'\bGBP\b|\bPOUND', re.I), "GBP"),
    (re.compile(r'\bCHF\b', re.I), "CHF"),
    (re.compile(r'\bJPY\b|\bYEN\b', re.I), "JPY"),
    (re.compile(r'\bMAD\b|\bDIRHAM', re.I), "MAD"),
    (re.compile(r'\bDZD\b|\bDINAR\s+ALGERIEN', re.I), "DZD"),
]

# Labels indiquant un fournisseur/société
_SUPPLIER_LABELS = re.compile(
    r"(?:fournisseur|supplier|vendor|émis\s+par|issued\s+by|from|vendeur|"
    r"société|company|entreprise|prestataire|nom\s+de\s+la\s+société)\s*[:#]?",
    re.I,
)

# Labels indiquant un client
_CLIENT_LABELS = re.compile(
    r"(?:client|customer|bill\s+to|sold\s+to|facturé\s+à|destinataire)\s*[:#]?",
    re.I,
)

# Labels de période
_PERIOD_LABELS = re.compile(
    r"(?:period|période|month\s+ended|mois\s+de|date\s+de\s+facture|"
    r"invoice\s+date|date|du|au)\s*[:#]?",
    re.I,
)

# Labels de numéro de facture
_INVOICE_NUM_LABELS = re.compile(
    r"(?:invoice|facture|n°|ref|référence|numéro|number|no\.?)\s*[:#]?",
    re.I,
)


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation de la période
# ─────────────────────────────────────────────────────────────────────────────

def normalize_period(text: str) -> Optional[str]:
    """
    Convertit une période en format ISO YYYY-MM ou YYYY-MM-DD.
    Gère les formats anglais, français et numériques.
    """
    if not text:
        return None

    text = text.strip()

    # Format "31 January 2025" ou "1 janvier 2025"
    m = re.search(r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b", text, re.I)
    if m:
        month_num = _MONTH_MAP.get(m.group(2).lower())
        if month_num:
            return f"{m.group(3)}-{month_num:02d}-{int(m.group(1)):02d}"

    # Format "January 2025" ou "Janvier 2025"
    m = re.search(r"\b(\w+)\s+(\d{4})\b", text, re.I)
    if m:
        month_num = _MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return f"{m.group(2)}-{month_num:02d}"

    # Format ISO "2025-01-31"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return text

    # Format "31/01/2025"
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # Format "2025-01"
    m = re.match(r"(\d{4})-(\d{2})$", text)
    if m:
        return text

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Extraction depuis les sources
# ─────────────────────────────────────────────────────────────────────────────

def _collect_all_text(pages: List[Dict]) -> str:
    """Collecte tout le texte disponible (raw_text + kv_regions + headers)."""
    parts = []
    for page in pages:
        parts.append(page.get("raw_text", ""))
        for h in page.get("headers", []):
            parts.append(h.get("text", ""))
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                parts.append(cell.get("text", ""))
    return " ".join(p for p in parts if p)


def _find_in_kv_by_label(pages: List[Dict], label_pattern: re.Pattern) -> Optional[str]:
    """
    Cherche une valeur dans les kv_regions en repérant une cellule "label"
    puis en prenant la cellule suivante (proximité spatiale).
    """
    for page in pages:
        for kv in page.get("kv_regions", []):
            cells = kv.get("cells", [])
            for i, cell in enumerate(cells):
                text = cell.get("text", "")
                if label_pattern.search(text):
                    # Chercher la valeur : cellule suivante sur la même ligne (Δt < 15px)
                    label_bbox = cell.get("bbox") or {}
                    label_t = label_bbox.get("t", 0)
                    label_r = label_bbox.get("r", 0)

                    for j in range(i + 1, min(i + 5, len(cells))):
                        next_cell = cells[j]
                        next_bbox = next_cell.get("bbox") or {}
                        next_t = next_bbox.get("t", 0)
                        next_l = next_bbox.get("l", 0)
                        val_text = next_cell.get("text", "").strip()

                        if not val_text:
                            continue
                        # Même ligne (tolérance ±15px) et à droite du label
                        if abs(next_t - label_t) < 15 and next_l >= label_r - 5:
                            return clean_text(val_text)
                        # Ou ligne juste en dessous (tolérance ±30px)
                        if 0 < next_t - label_t < 30:
                            return clean_text(val_text)
    return None


def _find_date_in_text(text: str) -> Optional[str]:
    """Cherche une date dans un texte brut."""
    # "31 January 2025"
    m = re.search(r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b", text)
    if m and _MONTH_MAP.get(m.group(2).lower()):
        return m.group(0)
    # "January 2025"
    m = re.search(r"\b(\w+)\s+(\d{4})\b", text)
    if m and _MONTH_MAP.get(m.group(1).lower()):
        return m.group(0)
    # "31/01/2025"
    m = re.search(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b", text)
    if m:
        return m.group(0)
    # "2025-01-31"
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        return m.group(0)
    return None


def _find_invoice_number_in_text(text: str) -> Optional[str]:
    """Cherche un numéro de facture dans un texte brut."""
    for pat in _INVOICE_NUM_PATTERNS:
        m = pat.search(text)
        if m:
            num = m.group(1).strip()
            # Valider : au moins 3 chars, pas juste des espaces
            if len(num) >= 2 and not num.isspace():
                return num
    return None


def _find_company_in_kv(pages: List[Dict]) -> Optional[str]:
    """
    Cherche le nom de la société/fournisseur dans les kv_regions.
    Accepte : labels explicites OU cellules "company" classifiées par le bridge.
    """
    # 1. Via label explicite
    result = _find_in_kv_by_label(pages, _SUPPLIER_LABELS)
    if result:
        return result

    # 2. Via semantic_class "company" du bridge
    for page in pages:
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                if cell.get("semantic_class") == "company":
                    return clean_text(cell.get("text", ""))

    # 3. Chercher une entité tout-majuscules dans les kv_regions (heuristique)
    candidates = []
    for page in pages:
        for kv in page.get("kv_regions", []):
            for cell in kv.get("cells", []):
                t = cell.get("text", "").strip()
                # Entité tout en majuscules, longueur > 4, pas que des chiffres
                if (t.isupper() and len(t) > 4
                        and not re.match(r"^[\d\s\-/]+$", t)
                        and not re.search(r"\b(TOTAL|INVOICE|FACTURE|DATE|PAGE|REF)\b", t, re.I)):
                    candidates.append(t)

    if candidates:
        # Prendre la plus longue (souvent le nom complet)
        return max(candidates, key=len)

    return None


def _find_concession_in_kv(pages: List[Dict]) -> Optional[str]:
    """
    Cherche le code de concession (spécifique aux factures pétrolières JIB).
    Générique : cherche par label "Concession" avec tolérance spatiale ±15px.
    """
    concession_label_re = re.compile(r"\bconcession\b", re.I)
    for page in pages:
        for kv in page.get("kv_regions", []):
            cells = kv.get("cells", [])
            for i, cell in enumerate(cells):
                if concession_label_re.search(cell.get("text", "")):
                    label_bbox = cell.get("bbox") or {}
                    label_x = label_bbox.get("l", 999)

                    # Chercher code_or_name à droite avec tolérance ±15px
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


def _find_currency_in_pages(pages: List[Dict]) -> str:
    """Détecte la devise depuis tout le texte disponible."""
    all_text = _collect_all_text(pages)
    for pattern, currency in _CURRENCY_PATTERNS:
        if pattern.search(all_text):
            return currency
    return "USD"


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ─────────────────────────────────────────────────────────────────────────────

def extract_identity(
    doc_info: Dict[str, Any],
    pages: List[Dict],
    metadata: Dict[str, Any],
    known_suppliers: Optional[List[str]] = None,
) -> DocumentIdentity:
    """
    Extrait l'identité complète du document depuis toutes les sources disponibles.
    """
    all_text = _collect_all_text(pages)

    # ── Période ────────────────────────────────────────────────────────────────
    period = (
        doc_info.get("period")
        or doc_info.get("date")
        or _find_in_kv_by_label(pages, _PERIOD_LABELS)
        or _find_date_in_text(all_text)
    )
    period = clean_text(period) if period else None
    period_normalized = normalize_period(period) if period else None

    # ── Numéro de facture ──────────────────────────────────────────────────────
    invoice_number = (
        doc_info.get("invoice_number")
        or _find_in_kv_by_label(pages, _INVOICE_NUM_LABELS)
        or _find_invoice_number_in_text(all_text)
    )
    invoice_number = clean_text(invoice_number) if invoice_number else None

    # ── Société ────────────────────────────────────────────────────────────────
    company = (
        doc_info.get("company")
        or _find_company_in_kv(pages)
    )
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
    # Heuristique : chercher des mots-clés de type de document dans le texte
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
            # Chercher "INVOICE", "FACTURE" en majuscules dans le texte
            m = re.search(r"\b(INVOICE|FACTURE|DEVIS|QUOTATION|CREDIT NOTE|BON DE COMMANDE)\b",
                          all_text, re.I)
            if m:
                document_type = m.group(1).title()
    document_type = clean_text(document_type) if document_type else None

    # ── Concession (spécifique JIB mais inoffensif sinon) ─────────────────────
    concession = doc_info.get("concession") or _find_concession_in_kv(pages)
    concession = clean_text(concession) if concession else None

    # ── DocuSign ID ────────────────────────────────────────────────────────────
    docusign_id = doc_info.get("docusign_id")
    if not docusign_id:
        m = re.search(r"docusign\s+envelope\s+id\s*:\s*([A-F0-9\-]{30,})", all_text, re.I)
        if m:
            docusign_id = m.group(1).strip()

    # ── Devise ─────────────────────────────────────────────────────────────────
    currency = _find_currency_in_pages(pages)

    # ── Total pages ────────────────────────────────────────────────────────────
    total_pages = doc_info.get("total_pages_in_doc")
    if not total_pages:
        # Chercher "X of Y" ou "Page X/Y" dans les headers
        for page in pages:
            for h in page.get("headers", []):
                m = re.search(r"\b(\d+)\s+of\s+(\d+)\b", h.get("text", ""), re.I)
                if m:
                    total_pages = int(m.group(2))
                    break
                m = re.search(r"page\s+\d+\s*/\s*(\d+)", h.get("text", ""), re.I)
                if m:
                    total_pages = int(m.group(1))
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