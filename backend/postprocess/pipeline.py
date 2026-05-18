"""
postprocess/pipeline.py
========================
Pipeline principal de post-traitement DocCore.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .core.schema_detector import build_schema
from .core.ocr_corrector import clean_text, clean_description
from .invoice.header_extractor import extract_identity, _find_currency_in_pages
from .invoice.line_item_builder import build_items_from_rows, merge_tables
from .invoice.financial_analyzer import analyze_financials
from .quality.quality_scorer import compute_quality
from .models import (
    InvoiceDocument, Section, LineItem, MonetaryAmount,
    TableSchema, RawTable
)

_log = logging.getLogger(__name__)


def _matrix_to_rows(table: Dict) -> List[Dict[str, Any]]:
    """
    Convertit la matrice brute du bridge en une liste de rows structurées.
    """
    matrix = table.get("matrix", [])
    col_semantics = table.get("column_semantics", [])
    data_start = table.get("data_start_row", 0)
    num_cols = len(col_semantics)

    # Identifier l'indice de la colonne description
    desc_col = 0
    for i, sem in enumerate(col_semantics):
        if sem in ("description", "designation", "libelle", "article", "item"):
            desc_col = i
            break

    rows = []
    for r in range(data_start, len(matrix)):
        row_vals = matrix[r]
        if not any(cell for cell in row_vals):
            continue   # ligne vide

        description = ""
        values = {}
        for c in range(num_cols):
            text = (row_vals[c] or "").strip() if c < len(row_vals) else ""
            sem = col_semantics[c] if c < len(col_semantics) else f"col_{c}"

            if c == desc_col:
                description = text
            values[sem] = {"text": text, "amount": None}

        # Détection du type de ligne
        row_type = "data"
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in [
            "total", "grand total", "sous-total", "subtotal",
            "net", "balance", "montant", "total facture",
            "total expenditure", "total expenditures",
            "cash basis", "accrual basis"
        ]):
            row_type = "total"
        elif re.match(r"^[A-Z\s]{3,}$", description) and len(description.split()) <= 5:
            row_type = "section_header"

        rows.append({
            "row_index": r,
            "description": description,
            "row_type": row_type,
            "values": values,
            "quality_flags": [],
        })

    return rows


def process_from_dict(
    raw: Dict[str, Any],
    known_suppliers: Optional[List[str]] = None,
) -> InvoiceDocument:
    t0 = time.perf_counter()

    pages    = raw.get("pages", [])
    tables   = raw.get("tables", [])
    metadata = raw.get("metadata", {})
    doc_info = raw.get("document_info", {})

    # ── 1. Devise ──────────────────────────────────────────────────────────
    currency = _find_currency_in_pages(pages)

    # ── 2. Schéma de colonnes ──────────────────────────────────────────────
    schema_table = next((t for t in tables if t.get("column_headers_raw")), None)
    if schema_table:
        schema = build_schema(
            headers_raw=schema_table.get("column_headers_raw", []),
            semantics_from_extraction=schema_table.get("column_semantics", []),
            currency=currency,
        )
    else:
        schema = build_schema([], currency=currency)

    # ── 3. Conversion matrix → rows si nécessaire ──────────────────────────
    for t in tables:
        if "rows" not in t:
            t["rows"] = _matrix_to_rows(t)

    # 🔍 DIAGNOSTIC TEMPORAIRE
    _log.warning("=== DIAGNOSTIC FUSION ===")
    _log.warning(f"Nombre de tables brutes : {len(tables)}")
    for i, t in enumerate(tables):
        _log.warning(f"Table {i}: page={t.get('page_no')}, headers={t.get('column_headers_raw')}, nb_rows={len(t.get('rows', []))}, semantics={t.get('column_semantics')}")
    # 🔍 FIN DIAGNOSTIC

    # ── 4. Fusion multi-pages ──────────────────────────────────────────────
    merged_tables = merge_tables(tables)

    # 🔍 DIAGNOSTIC APRÈS FUSION
    _log.warning(f"Nombre de tables fusionnées : {len(merged_tables)}")
    for i, mt in enumerate(merged_tables):
        _log.warning(f"Fusionnée {i}: source_pages={mt.get('source_pages')}, nb_rows={len(mt.get('rows', []))}")
    # 🔍 FIN DIAGNOSTIC

    # ── 5. Construction des items depuis les rows ──────────────────────────
    sections: List[Section] = []
    global_totals: List[LineItem] = []

    for table in merged_tables:
        rows = table.get("rows", [])
        col_semantics = table.get("column_semantics", [])
        section_schema_dict = {
            "headers": table.get("column_headers_raw", []),
            "semantics": table.get("column_semantics", []),
        }
        items, totals = build_items_from_rows(rows, col_semantics, schema, currency)
        # ✅ Inclure les lignes de totaux dans la section pour l'affichage
        all_items = items + totals
        sections.append(Section(
            name="Items",
            row_index=0,
            items=all_items,
            columns_schema=section_schema_dict
        ))
        global_totals.extend(totals)   # conserver pour l'analyse financière

    # ── 6. Identité ────────────────────────────────────────────────────────
    identity = extract_identity(doc_info, pages, metadata, known_suppliers)
    identity.currency = currency

    # ── 7. Analyse financière ──────────────────────────────────────────────
    financial_summary = analyze_financials(
        sections, global_totals, raw.get("totals", {}), schema, currency
    )

    # ── 8. Qualité ─────────────────────────────────────────────────────────
    metadata["tables_found"] = len(merged_tables)
    quality = compute_quality(identity, financial_summary, sections, schema, metadata)

    # ── 9. Raw tables pour le frontend ─────────────────────────────────────
    raw_tables = []
    for table in merged_tables:
        raw_tables.append(RawTable(
            table_id=table.get("table_id", "unknown"),
            headers=table.get("column_headers_raw", []),
            rows=[[
                row["values"].get(sem, {}).get("text", "") if sem in row["values"] else ""
                for sem in table.get("column_semantics", [])
            ] for row in table.get("rows", [])]
        ))

    # ── 10. Assemblage final ───────────────────────────────────────────────
    invoice = InvoiceDocument(
        identity=identity,
        schema=schema,
        sections=sections,
        financial_summary=financial_summary,
        quality=quality,
        raw_tables=raw_tables,
    )

    elapsed = time.perf_counter() - t0
    _log.info(
        f"[Pipeline] ✓ {elapsed:.3f}s | Score: {quality.overall_score:.0%} | "
        f"Colonnes: {schema.semantics} | Items: {sum(s.item_count for s in sections)}"
    )
    return invoice


def process(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> InvoiceDocument:
    """Pipeline depuis un fichier JSON."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    invoice = process_from_dict(raw)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        invoice.to_json(str(output_path))
        _log.info(f"[Pipeline] Sauvegardé → {output_path}")

    return invoice