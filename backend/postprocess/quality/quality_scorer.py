"""postprocess/quality/quality_scorer.py – Score de qualité de l'extraction"""
import logging
from typing import Dict, List, Tuple
from ..models import ExtractionQuality, DocumentIdentity, FinancialSummary, Section, TableSchema

_log = logging.getLogger(__name__)

def _score_identity(identity: DocumentIdentity) -> Tuple[float, List[str], List[str]]:
    required = {"company": identity.company, "document_type": identity.document_type,
                "period": identity.period, "docusign_id": identity.docusign_id}
    optional = {"concession": identity.concession, "period_normalized": identity.period_normalized}
    issues = [f"Champ manquant : {k}" for k, v in required.items() if not v]
    warnings = [f"Champ optionnel absent : {k}" for k, v in optional.items() if not v]
    score = (len(required) - len(issues)) / len(required) if required else 1.0
    return score, issues, warnings

def _score_financial(summary: FinancialSummary, schema: TableSchema) -> Tuple[float, List[str], List[str]]:
    issues, warnings = [], []
    points, max_pts = 0, 4
    if summary.totals_by_column:
        points += 1
    elif summary.total_rows:
        points += 0.5
        warnings.append("Totaux calculés (aucune ligne total officielle dans le document)")
    else:
        issues.append("Aucun total disponible")
    numeric_totals = [v for v in summary.totals_by_column.values() if v.value is not None]
    if numeric_totals:
        points += 1
    else:
        issues.append("Tous les totaux sont vides")
    if summary.sharing_balanced is True:
        points += 1
    elif summary.sharing_balanced is False:
        issues.append("Déséquilibre des parts détecté")
    else:
        points += 0.5
        warnings.append("Colonnes de partage non détectées (facultatif)")
    unknown_cols = sum(1 for c in schema.columns if c.semantic.startswith("col_"))
    if unknown_cols == 0:
        points += 1
    else:
        warnings.append(f"{unknown_cols} colonne(s) non identifiée(s)")
        points += 0.5
    for a in summary.anomalies:
        if "artefact" in a.lower():
            warnings.append(a)
        else:
            issues.append(a)
    return min(points / max_pts, 1.0), issues, warnings

def _score_structure(sections: List[Section]) -> Tuple[float, List[str], List[str]]:
    issues, warnings = [], []
    if not sections:
        return 0.0, ["Aucune section détectée"], []
    real_secs = [s for s in sections if s.name != "_ungrouped_"]
    total_items = sum(s.item_count for s in sections)
    active_items = sum(s.active_count for s in sections)
    points = 0
    if real_secs:
        points += 1
    else:
        warnings.append("Aucune section nommée (lignes en section générique)")
    if active_items > 0:
        points += 1
    else:
        issues.append("Aucune ligne avec montants actifs")
    ratio = active_items / max(total_items, 1)
    if ratio >= 0.10:
        points += 1
    else:
        warnings.append(f"Faible ratio lignes actives : {active_items}/{total_items} ({ratio:.0%})")
    return points / 3, issues, warnings

def compute_quality(
    identity: DocumentIdentity,
    summary: FinancialSummary,
    sections: List[Section],
    schema: TableSchema,
    metadata: Dict,
) -> ExtractionQuality:
    id_s, id_i, id_w = _score_identity(identity)
    fin_s, fin_i, fin_w = _score_financial(summary, schema)
    str_s, str_i, str_w = _score_structure(sections)
    overall = round(id_s * 0.30 + fin_s * 0.50 + str_s * 0.20, 4)
    total_rows = sum(s.item_count for s in sections)
    active_rows = sum(s.active_count for s in sections)
    _log.info(f"[Quality] {overall:.0%} | Identité:{id_s:.0%} Financier:{fin_s:.0%} Structure:{str_s:.0%}")
    return ExtractionQuality(
        overall_score=overall,
        identity_complete=(id_s == 1.0),
        tables_found=metadata.get("tables_found", 0),
        total_rows=total_rows,
        active_rows=active_rows,
        issues=id_i + fin_i + str_i,
        warnings=id_w + fin_w + str_w,
    )