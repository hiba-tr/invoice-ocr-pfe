"""
postprocess/invoice/financial_analyzer.py
==========================================
Analyse financière générique.

Responsabilités :
  - Détection automatique des colonnes de partage (TVA, remise, OMV/ETAP, etc.)
  - Validation de la cohérence des parts (somme = total)
  - Calcul de la consommation budget vs réel
  - Détection d'anomalies financières
  - Variance YTD courant vs précédent
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..models import FinancialSummary, LineItem, MonetaryAmount, Section, TableSchema

_log = logging.getLogger(__name__)

_FLOAT_TOL = 0.02

# Sémantiques représentant un "total" global (pas des parts)
_TOTAL_SEMANTICS = frozenset([
    "total", "amount", "cme_total", "grand_total",
    "total_ht", "total_ttc", "net", "montant",
])


def _detect_sharing(
    totals_by_col: Dict[str, MonetaryAmount],
) -> Tuple[Dict[str, float], Optional[bool]]:
    """
    Détecte les colonnes de partage et vérifie leur cohérence.
    Générique : fonctionne pour TVA+HT=TTC, OMV+ETAP=Total, etc.
    """
    sharing: Dict[str, float] = {}
    balanced: Optional[bool] = None

    if not totals_by_col:
        return sharing, balanced

    # 1. Trouver la colonne total principale (valeur absolue maximale)
    total_amount: Optional[MonetaryAmount] = None
    for sem in _TOTAL_SEMANTICS:
        if sem in totals_by_col and totals_by_col[sem].value is not None:
            total_amount = totals_by_col[sem]
            break

    if total_amount is None:
        # Prendre la colonne avec la valeur absolue la plus grande
        valid = {k: v for k, v in totals_by_col.items() if v.value is not None}
        if valid:
            total_amount = max(valid.values(), key=lambda v: abs(v.value or 0))

    if total_amount is None or total_amount.value is None or total_amount.value == 0:
        return sharing, balanced

    total_val = total_amount.value

    # 2. Candidats de partage : colonnes numériques non-total avec valeur < abs(total)
    share_candidates = {
        k: v for k, v in totals_by_col.items()
        if v.value is not None
        and k not in _TOTAL_SEMANTICS
        and abs(v.value) < abs(total_val) * 1.01  # tolérance 1%
    }

    if len(share_candidates) < 2:
        return sharing, balanced

    # 3. Vérifier si la somme des parts ≈ total
    sum_shares = sum(v.value for v in share_candidates.values())

    # Utiliser la valeur absolue pour la comparaison (négatifs inclus)
    if abs(abs(sum_shares) - abs(total_val)) <= max(_FLOAT_TOL, abs(total_val) * 0.001):
        balanced = True
    else:
        balanced = False

    # 4. Calculer les pourcentages (en valeur absolue)
    abs_total = abs(total_val)
    if abs_total > 0:
        for k, v in share_candidates.items():
            sharing[k] = round((abs(v.value) / abs_total) * 100, 2)

    return sharing, balanced


def _compute_budget_consumption(
    totals_by_col: Dict[str, MonetaryAmount],
) -> Optional[float]:
    """Calcule le % budget consommé (YTD / Budget × 100)."""
    budget = totals_by_col.get("budget")
    ytd = totals_by_col.get("ytd_current") or totals_by_col.get("ytd")
    if (budget and ytd
            and budget.value and budget.value != 0
            and ytd.value is not None):
        return round((ytd.value / budget.value) * 100, 2)
    return None


def _detect_anomalies(
    sections: List[Section],
    global_totals: List[LineItem],
    totals_by_col: Dict[str, MonetaryAmount],
    sharing_balanced: Optional[bool],
) -> List[str]:
    """Détecte les anomalies financières dans le document."""
    anomalies = []

    # Déséquilibre des parts
    if sharing_balanced is False:
        anomalies.append("Déséquilibre dans les parts (la somme ne correspond pas au total)")

    # Artefacts OCR dans les items
    ocr_count = sum(
        len([f for f in item.quality_flags if "artifact" in f.lower()])
        for s in sections
        for item in s.items
    )
    if ocr_count:
        anomalies.append(f"{ocr_count} cellule(s) avec artefacts de fusion (corrigées)")

    # Variance YTD courant vs précédent (seuil : <50%)
    ytd_curr = totals_by_col.get("ytd_current")
    ytd_prev = totals_by_col.get("ytd_previous")
    if (ytd_curr and ytd_prev
            and ytd_curr.value and ytd_prev.value
            and ytd_prev.value != 0
            and abs(ytd_curr.value) < abs(ytd_prev.value) * 0.5):
        anomalies.append(
            f"YTD courant ({ytd_curr.raw}) < 50% du YTD précédent ({ytd_prev.raw})"
        )

    # Montants tous nuls (extraction probablement vide)
    if totals_by_col and all(v.value == 0 or v.value is None for v in totals_by_col.values()):
        anomalies.append("Tous les totaux sont à zéro — vérifier l'extraction")

    return anomalies


def analyze_financials(
    sections: List[Section],
    global_totals: List[LineItem],
    raw_totals: Dict[str, Any],
    schema: TableSchema,
    currency: str = "USD",
) -> FinancialSummary:
    """
    Analyse financière complète.
    Générique : fonctionne quelle que soit la structure de la facture.
    """
    from .total_calculator import extract_global_totals

    totals_by_col = extract_global_totals(
        sections, global_totals, raw_totals, schema, currency
    )

    sharing, sharing_balanced = _detect_sharing(totals_by_col)
    budget_pct = _compute_budget_consumption(totals_by_col)

    # Variance YTD vs Budget
    ytd_vs_budget = None
    budget_amt = totals_by_col.get("budget")
    ytd_amt = totals_by_col.get("ytd_current") or totals_by_col.get("ytd")
    if (budget_amt and ytd_amt
            and budget_amt.value and budget_amt.value != 0
            and ytd_amt.value is not None):
        ytd_vs_budget = round(
            ((ytd_amt.value - budget_amt.value) / abs(budget_amt.value)) * 100, 2
        )

    anomalies = _detect_anomalies(
        sections, global_totals, totals_by_col, sharing_balanced
    )

    _log.info(
        f"[FinancialAnalyzer] Totaux: {list(totals_by_col.keys())} | "
        f"Sharing: {sharing} | Balanced: {sharing_balanced} | "
        f"Budget%: {budget_pct} | Anomalies: {len(anomalies)}"
    )

    return FinancialSummary(
        total_rows=global_totals,
        totals_by_column=totals_by_col,
        sharing=sharing,
        sharing_balanced=sharing_balanced,
        budget_consumed_pct=budget_pct,
        ytd_vs_budget_variance=ytd_vs_budget,
        anomalies=anomalies,
    )