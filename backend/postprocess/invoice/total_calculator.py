"""
postprocess/invoice/total_calculator.py
=========================================
Extraction et calcul des totaux globaux.

Stratégie (3 niveaux, ordre de priorité) :
  1. Lignes explicites de type "total" dans le tableau (ligne "Total net HT", etc.)
  2. raw_totals fournis par le bridge (extraction directe depuis le texte)
  3. Calcul automatique par sommation des items actifs (fallback)

Générique : fonctionne pour toute structure de facture.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..models import LineItem, MonetaryAmount, Section, TableSchema

_log = logging.getLogger(__name__)

# Mapping des clés raw_totals du bridge → sémantiques colonnes
_RAW_TOTALS_MAP = {
    "total_usd":   ["total", "amount", "cme_total", "grand_total"],
    "omv_share":   ["cme_omv", "omv_share", "omv"],
    "etap_share":  ["cme_etap", "etap_share", "etap"],
    "ytd_current": ["ytd_current", "ytd"],
    "ytd_previous":["ytd_previous"],
    "budget":      ["budget"],
}


def _sum_section_items(
    sections: List[Section],
    col_semantic: str,
    currency: str,
) -> Optional[MonetaryAmount]:
    """Somme les valeurs d'une colonne sur tous les items actifs de toutes les sections."""
    values = []
    for section in sections:
        for item in section.items:
            if item.row_type in ("total", "subtotal", "section_header"):
                continue
            amt = item.values.get(col_semantic)
            if amt and amt.value is not None:
                values.append(amt.value)

    if not values:
        return None

    total = sum(values)
    neg = total < 0
    raw = f"({abs(total):,.2f})" if neg else f"{total:,.2f}"
    return MonetaryAmount(raw=raw, value=total, currency=currency, is_negative=neg)


def extract_global_totals(
    sections: List[Section],
    global_totals: List[LineItem],
    raw_totals: Dict[str, Any],
    schema: TableSchema,
    currency: str = "USD",
) -> Dict[str, MonetaryAmount]:
    """
    Extrait les totaux par colonne selon les 3 niveaux de priorité.

    Retourne un dict {semantic_col: MonetaryAmount}.
    """
    totals_by_col: Dict[str, MonetaryAmount] = {}

    # ── Niveau 1 : lignes de totaux explicites ────────────────────────────────
    for item in global_totals:
        for sem, amt in item.values.items():
            if sem not in totals_by_col and amt.value is not None:
                totals_by_col[sem] = amt
                _log.debug(f"[TotalCalc] L1 {sem} = {amt.raw}")

    # ── Niveau 2 : raw_totals du bridge ──────────────────────────────────────
    for raw_key, candidate_sems in _RAW_TOTALS_MAP.items():
        raw_val = raw_totals.get(raw_key)
        if not raw_val:
            continue
        for sem in candidate_sems:
            if sem not in totals_by_col:
                amt = MonetaryAmount.from_text(str(raw_val), currency=currency)
                if amt.value is not None:
                    totals_by_col[sem] = amt
                    _log.debug(f"[TotalCalc] L2 {sem} = {amt.raw} (from raw_totals.{raw_key})")
                break

    # ── Niveau 3 : calcul automatique par sommation ───────────────────────────
    # Seulement si aucun total n'a été trouvé (document sans ligne total)
    if not totals_by_col:
        _log.info("[TotalCalc] Aucun total trouvé, calcul par sommation des items")
        for col in schema.numeric_cols:
            computed = _sum_section_items(sections, col.semantic, currency)
            if computed is not None:
                totals_by_col[col.semantic] = computed
                _log.debug(f"[TotalCalc] L3 {col.semantic} = {computed.raw}")

    # ── Complément : colonnes numériques manquantes calculées ─────────────────
    # Si on a des totaux L1/L2 mais il manque certaines colonnes → calcul partiel
    for col in schema.numeric_cols:
        if col.semantic not in totals_by_col:
            computed = _sum_section_items(sections, col.semantic, currency)
            if computed is not None:
                totals_by_col[col.semantic] = computed
                _log.debug(f"[TotalCalc] L3-complement {col.semantic} = {computed.raw}")

    if totals_by_col:
        _log.info(f"[TotalCalc] Totaux extraits: {list(totals_by_col.keys())}")
    else:
        _log.warning("[TotalCalc] Aucun total disponible")

    return totals_by_col