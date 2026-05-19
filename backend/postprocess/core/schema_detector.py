"""postprocess/core/schema_detector.py – Découverte dynamique du schéma de colonnes"""
from __future__ import annotations
import re
import logging
from typing import List, Optional, Tuple
from ..models import ColumnDef, TableSchema

_log = logging.getLogger(__name__)

# Patterns multilingues génériques, sans aucune marque de domaine
_SEMANTIC_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bdescription\b|\bdesignation\b|\blibellé\b|\barticle\b|\bitem\b", re.I), "description"),
    (re.compile(r"\bquantity\b|\bquantité\b|\bqté\b|\bqty\b|\bqte\b", re.I), "quantity"),
    (re.compile(r"\bunit.?price\b|\bprix.?unitaire\b|\bprice\b|\btarif\b", re.I), "unit_price"),
    (re.compile(r"\btotal\b|\bmontant\b|\bamount\b|\bnet\b|\bbrut\b", re.I), "amount"),
    (re.compile(r"\bref\b|\bréférence\b|\bcode\b|\bn°\b|\bnuméro\b", re.I), "reference"),
    (re.compile(r"\bdate\b|\bpériode\b|\bperiod\b", re.I), "date"),
    (re.compile(r"\btva\b|\btax\b|\bvat\b", re.I), "tax"),
    (re.compile(r"\bremise\b|\bdiscount\b|\brabais\b", re.I), "discount"),
    (re.compile(r"\bcurrency\b|\bdevise\b", re.I), "currency"),
]

def _infer_semantic(header_text: str, col_index: int) -> str:
    if not header_text:
        return f"col_{col_index}"
    for pattern, semantic in _SEMANTIC_RULES:
        if pattern.search(header_text):
            return semantic
    # Fallback: normalise le texte
    norm = re.sub(r"\s+", "_", header_text.lower().strip())
    norm = re.sub(r"[^\w_]", "", norm)[:25]
    return norm or f"col_{col_index}"

def _infer_data_type(semantic: str, header_raw: str = "", col_index: int = 0) -> str:
    KNOWN_TYPES = {
        "amount": "amount", "unit_price": "amount", "tax": "amount",
        "discount": "amount", "total": "amount",
        "quantity": "quantity", "description": "text", "reference": "identifier",
        "date": "date", "currency": "text",
    }
    if semantic in KNOWN_TYPES:
        return KNOWN_TYPES[semantic]
    if header_raw:
        h = header_raw.lower()
        if re.search(r"\b(?:total|montant|prix|amount|price|budget|expenditure|€|\$)\b", h):
            return "amount"
        if re.search(r"\b(?:qte|quantit|quantity|qty|unit)\b", h):
            return "quantity"
        if re.search(r"\b(?:n°|réf|ref|code|numéro|num)\b", h):
            return "identifier"
    return "text"

def build_schema(
    headers_raw: List[str],
    semantics_from_extraction: Optional[List[str]] = None,
    currency: str = "USD",
) -> TableSchema:
    columns = []
    for i, raw in enumerate(headers_raw):
        if semantics_from_extraction and i < len(semantics_from_extraction):
            sem_from_ext = semantics_from_extraction[i]
            if sem_from_ext and not re.match(r"^col_\d+$", sem_from_ext) and sem_from_ext != "unknown":
                semantic = sem_from_ext
            else:
                semantic = _infer_semantic(raw, i)
        else:
            semantic = _infer_semantic(raw, i)
        data_type = _infer_data_type(semantic, raw, i)
        columns.append(ColumnDef(index=i, header_raw=raw.strip(), semantic=semantic,
                                data_type=data_type, currency=currency))
    _log.info(f"[SchemaDetector] Schéma découvert: {[c.semantic for c in columns]}")
        # Si la première colonne a un header vide, elle devient la colonne description
    if columns and (not columns[0].header_raw.strip()):
        columns[0].header_raw = "Description"
        columns[0].semantic = "description"
        columns[0].data_type = "text"    
        
        # Si aucune colonne n'a la sémantique "description", forcer la première colonne non-numérique à être "description"
    if not any(c.semantic == "description" for c in columns):
        for col in columns:
            if not col.is_numeric:
                col.semantic = "description"
                if not col.header_raw.strip():
                    col.header_raw = "Description"
                break
        else:
            # fallback : première colonne (ne devrait pas arriver)
            if columns:
                columns[0].semantic = "description"
    return TableSchema(columns=columns)