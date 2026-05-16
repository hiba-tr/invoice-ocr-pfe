"""
postprocess/invoice/line_item_builder.py
=========================================
Construction des LineItem depuis les rows déjà structurées par le bridge.

Philosophie :
  Le bridge (invoice_extraction_bridge) a déjà fait la reconstruction bas-niveau
  des tableaux (cells → rows avec description + values).
  Ce module prend ces rows et :
    1. Nettoie les descriptions (artefacts OCR)
    2. Convertit les valeurs texte en MonetaryAmount typés
    3. Détecte les lignes de totaux vs lignes de données
    4. Fusionne les tableaux multi-pages
    5. Gère la colonne description dynamiquement (pas toujours col 0)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..core.ocr_corrector import clean_description, clean_text
from ..models import ColumnDef, LineItem, MonetaryAmount, TableSchema

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Mots-clés de totaux — multilingues, sans domaine spécifique
# ─────────────────────────────────────────────────────────────────────────────
_TOTAL_KEYWORDS = frozenset([
    "total", "grand total", "sous-total", "subtotal", "net", "balance",
    "montant", "amount due", "total ttc", "total ht", "net à payer",
    "solde", "total facture", "total général", "sum", "totale",
    "total expenditure", "total expenditures", "cash basis", "accrual basis",
    "net a payer", "neta payer",
])


def _is_total_row(description: str) -> bool:
    if not description:
        return False
    d = description.strip().lower()
    return any(kw in d for kw in _TOTAL_KEYWORDS)


def _find_description_col(col_semantics: List[str], schema: TableSchema) -> int:
    """
    Détermine l'indice de la colonne description.
    Cherche d'abord par sémantique, puis par heuristique (première colonne non-numérique).
    """
    # 1. Par sémantique exacte
    for i, sem in enumerate(col_semantics):
        if sem in ("description", "designation", "libelle", "article", "item"):
            return i

    # 2. Par schema (colonne non-numérique)
    for col in schema.columns:
        if not col.is_numeric:
            return col.index

    # 3. Fallback col 0
    return 0


def _build_monetary_value(
    text: str,
    col: Optional[ColumnDef],
    currency: str,
) -> MonetaryAmount:
    """
    Construit un MonetaryAmount en tenant compte du type de colonne.
    Les colonnes texte ne sont pas parsées comme montants.
    """
    if col and not col.is_numeric:
        # Colonne texte : on garde le texte brut sans conversion numérique
        return MonetaryAmount(raw=clean_text(text), value=None, currency=currency, is_empty=False)
    return MonetaryAmount.from_text(text, currency=currency)


def build_items_from_rows(
    rows: List[Dict[str, Any]],
    col_semantics: List[str],
    schema: TableSchema,
    currency: str = "USD",
) -> Tuple[List[LineItem], List[LineItem]]:
    """
    Construit les LineItem depuis les rows du bridge.

    Le bridge fournit pour chaque row :
      - description : texte de la colonne principale
      - row_type    : data | total | section_header
      - values      : dict {col_semantic: {text, amount}}

    Retourne (items_normaux, items_totaux).
    """
    items: List[LineItem] = []
    totals: List[LineItem] = []

    desc_col_idx = _find_description_col(col_semantics, schema)
    _log.debug(f"[LineItemBuilder] Colonne description = idx {desc_col_idx} ({col_semantics[desc_col_idx] if desc_col_idx < len(col_semantics) else '?'})")

    for row in sorted(rows, key=lambda r: r.get("row_index", 0)):
        raw_desc = row.get("description", "")
        row_type = row.get("row_type", "data")
        row_idx  = row.get("row_index", 0)
        raw_vals = row.get("values", {})

        # ── Nettoyage de la description ───────────────────────────────────────
        desc_clean = clean_description(raw_desc)
        if not desc_clean:
            desc_clean = raw_desc  # garder brut si clean vide

        # ── Surcharge du row_type depuis la description nettoyée ──────────────
        if _is_total_row(desc_clean):
            row_type = "total"

        # ── Construction des valeurs typées ───────────────────────────────────
        values: Dict[str, MonetaryAmount] = {}
        # ── Construction des valeurs typées ───────────────────────────────────
        values: Dict[str, MonetaryAmount] = {}
        desc_semantic = col_semantics[desc_col_idx] if desc_col_idx < len(col_semantics) else None
        for col_sem, val_info in raw_vals.items():
            # ⛔️ Ne pas inclure la colonne qui sert de description principale
            if col_sem == desc_semantic:
                continue
            text = val_info.get("text", "") if isinstance(val_info, dict) else str(val_info)
            text = clean_text(text)
            col_def = schema.get_col_by_semantic(col_sem)
            amt = _build_monetary_value(text, col_def, currency)
            values[col_sem] = amt

        # ── Détecter si la description vient d'une autre colonne (N°) ─────────
        # Si col 0 est un numéro de ligne (ex: "1.1", "1.1.1") et col 1 existe → prendre col 1
        if re.match(r"^\d+(\.\d+)*$", desc_clean.strip()) and desc_col_idx == 0:
            # Chercher la colonne suivante non-numérique
            for sem, val_info in raw_vals.items():
                col_def = schema.get_col_by_semantic(sem)
                if col_def and not col_def.is_numeric and col_def.index > 0:
                    alt_text = (val_info.get("text", "") if isinstance(val_info, dict) else str(val_info)).strip()
                    if alt_text and not re.match(r"^\d+(\.\d+)*$", alt_text):
                        desc_clean = clean_description(alt_text)
                        break

        item = LineItem(
            description=desc_clean,
            row_index=row_idx,
            row_type=row_type,
            values=values,
            quality_flags=row.get("quality_flags", []),
        )

        if row_type == "total":
            totals.append(item)
        else:
            items.append(item)

    _log.info(f"[LineItemBuilder] {len(items)} items | {len(totals)} totaux")
    return items, totals


# ─────────────────────────────────────────────────────────────────────────────
# Fusion multi-pages
# ─────────────────────────────────────────────────────────────────────────────

def _tables_are_continuations(t1: Dict, t2: Dict) -> bool:
    """Vérifie si t2 est la continuation de t1 (même structure de colonnes)."""
    if t1.get("num_cols") != t2.get("num_cols"):
        return False
    s1 = t1.get("column_semantics", [])
    s2 = t2.get("column_semantics", [])
    if not s1 or not s2:
        return False
    matches = sum(1 for a, b in zip(s1, s2) if a == b)
    return (matches / max(len(s1), 1)) >= 0.6


def merge_tables(tables: List[Dict]) -> List[Dict]:
    """
    Fusionne les tableaux de continuation multi-pages.
    Conserve les rows déjà structurées par le bridge.
    """
    if not tables:
        return []

    merged = []
    used: set = set()

    for i, t1 in enumerate(tables):
        if i in used:
            continue

        current = dict(t1)
        current["rows"] = list(t1.get("rows", []))
        current["total_rows"] = list(t1.get("total_rows", []))
        current["source_pages"] = [t1.get("page_no", 1)]

        for j, t2 in enumerate(tables[i + 1:], start=i + 1):
            if j in used:
                continue
            if t2.get("page_no") == t1.get("page_no"):
                continue
            if _tables_are_continuations(t1, t2):
                offset = max((r.get("row_index", 0) for r in current["rows"]), default=-1) + 1
                for row in t2.get("rows", []):
                    r2 = dict(row)
                    r2["row_index"] = r2.get("row_index", 0) + offset
                    current["rows"].append(r2)
                for row in t2.get("total_rows", []):
                    r2 = dict(row)
                    r2["row_index"] = r2.get("row_index", 0) + offset
                    current["total_rows"].append(r2)
                current["source_pages"].append(t2.get("page_no", 1))
                used.add(j)

        used.add(i)
        merged.append(current)

    _log.info(f"[LineItemBuilder] {len(tables)} tableaux → {len(merged)} après fusion")
    return merged