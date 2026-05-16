#!/usr/bin/env python3

from __future__ import annotations
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.extraction.engine.document_converter import DocumentConverter
from backend.extraction.engine.datamodel.base_models import InputFormat
from .utils.geometry import BBox, sort_cells_spatially

_log = logging.getLogger(__name__)

def _deduplicate_merged_headers(merged_headers: List[str]) -> List[str]:
    cleaned = []
    for h in merged_headers:
        parts = h.split()
        seen = []
        for p in parts:
            if not seen or p != seen[-1]:
                seen.append(p)
        cleaned.append(" ".join(seen))
    final = []
    seen_names = {}
    for h in cleaned:
        if h in seen_names:
            seen_names[h] += 1
            final.append(f"{h}_{seen_names[h]}")
        else:
            seen_names[h] = 0
            final.append(h)
    return final
# Patterns génériques pour la classification KV
_AMOUNT_RE = re.compile(r"([\(\-]?\s*[\d]{1,3}(?:[,\s]\d{3})*(?:\.\d+)?\s*[\)]?)")
_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b", re.I),
    re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", re.I),
]
_EMAIL_RE = re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")
_URL_RE = re.compile(r"\bhttps?://\S+\b")
_PHONE_RE = re.compile(r"\+?\d[\d\s.-]{6,}\d")
_VAT_RE = re.compile(r"\b[A-Z]{2}[\dA-Z]{2,20}\b")   # numéro TVA simplifié
_INVOICE_NUM_RE = re.compile(r"(?:invoice|facture|n°|ref)\s*[:#]?\s*([\w/-]+)", re.I)
_TOTAL_KEYWORDS = frozenset([
    "total", "grand total", "sous-total", "subtotal", "net", "balance",
    "montant", "amount due", "total ttc", "total ht", "total facture",
])

def _classify_kv_cell(text: str) -> str:
    t = text.strip()
    # Date
    for pat in _DATE_PATTERNS:
        if pat.search(t):
            return "date"
    # Montant
    if _AMOUNT_RE.match(t):
        return "amount"
    # Email, téléphone, URL
    if _EMAIL_RE.match(t):
        return "email"
    if _URL_RE.match(t):
        return "url"
    if _PHONE_RE.match(t):
        return "phone"
    # Numéro de TVA / SIREN
    if _VAT_RE.match(t):
        return "tax_id"
    # Mots-clés génériques de document
    if re.search(r"invoice|facture|purchase order|bon de commande", t, re.I):
        return "document_type"
    if re.search(r"date|période|period|échéance|due date", t, re.I):
        return "date_label"
    if re.search(r"fournisseur|supplier|vendor|émis par|issued by", t, re.I):
        return "supplier_label"
    if re.search(r"client|customer|bill to|sold to", t, re.I):
        return "client_label"
    if re.search(r"n°|ref|numéro|reference|code", t, re.I):
        return "reference_label"
    if re.search(r"total|montant|amount|balance|net à payer", t, re.I):
        return "total_label"
    if re.search(r"page", t, re.I):
        return "page_info"
    # Détection d'une entité nommée (tout en majuscules, longueur > 3)
    if t.isupper() and len(t) > 3 and not re.search(r"\d", t):
        return "company"
    return "unknown"

def _detect_column_semantics(header_texts: List[str]) -> List[str]:
    """
    Détection générique des rôles de colonnes basée sur des mots-clés multilingues.
    """
    patterns = [
        (re.compile(r"description|désignation|libellé|designation|item|article", re.I), "description"),
        (re.compile(r"quantity|quantité|qté|qty", re.I), "quantity"),
        (re.compile(r"unit.?price|prix.?unitaire|price", re.I), "unit_price"),
        (re.compile(r"total|montant|amount|net|brut|taxe|tva|remise|discount", re.I), "amount"),
        (re.compile(r"ref|n°|code|référence", re.I), "reference"),
        (re.compile(r"date|période|period", re.I), "date"),
        (re.compile(r"tva|tax|vat", re.I), "tax"),
        (re.compile(r"remise|discount|rabais", re.I), "discount"),
    ]
    col_names = []
    for h in header_texts:
        h_clean = h.strip()
        if not h_clean:
            col_names.append("unknown")
            continue
        matched = False
        for pat, sem in patterns:
            if pat.search(h_clean):
                col_names.append(sem)
                matched = True
                break
        if matched:
            continue
        # Si le header contient "expenditure", ne pas le classer comme "date"
        if re.search(r"\bexpenditure\b", h_clean, re.I):
            # fallback : nom normalisé unique
            norm = re.sub(r"\s+", "_", h_clean.lower())
            norm = re.sub(r"[^\w_]", "", norm)[:30]
            col_names.append(norm if norm else "unknown")
        else:
            # Fallback normal pour les autres
            norm = re.sub(r"\s+", "_", h_clean.lower())
            norm = re.sub(r"[^\w_]", "", norm)[:30]
            col_names.append(norm if norm else "unknown")
    seen_sem = {}
    final_col_names = []
    for sem in col_names:
        if sem in seen_sem:
            seen_sem[sem] += 1
            final_col_names.append(f"{sem}_{seen_sem[sem]}")
        else:
            seen_sem[sem] = 0
            final_col_names.append(sem)
    return final_col_names

def _extract_page_headers(page) -> Dict[str, Any]:
    result = {"headers": [], "page_number_raw": None, "total_pages": None, "docusign_id": None}
    if not (hasattr(page, "assembled") and page.assembled):
        return result
    headers = getattr(page.assembled, "headers", []) or []
    for h in headers:
        text = ""
        if hasattr(h, "cluster") and h.cluster:
            for cell in (h.cluster.cells or []):
                if hasattr(cell, "text") and cell.text and cell.text.strip():
                    text = cell.text.strip()
                    break
        if not text and hasattr(h, "text") and h.text:
            text = h.text.strip()
        if not text:
            continue
        header_entry = {
            "text": text,
            "label": h.label.value if hasattr(h.label, "value") else str(h.label),
            "bbox": None,
        }
        if hasattr(h, "cluster") and h.cluster and hasattr(h.cluster, "bbox"):
            bb = h.cluster.bbox
            header_entry["bbox"] = {"l": bb.l, "t": bb.t, "r": bb.r, "b": bb.b}
        result["headers"].append(header_entry)
        m = re.match(r"(\d+)\s+of\s+(\d+)", text, re.IGNORECASE)
        if m:
            result["page_number_raw"] = int(m.group(1))
            result["total_pages"] = int(m.group(2))
        m = re.match(r"docusign\s+envelope\s+id\s*:\s*(.+)", text, re.IGNORECASE)
        if m:
            result["docusign_id"] = m.group(1).strip()
    return result

def _extract_kv_regions(page) -> List[Dict[str, Any]]:
    kv_regions = []
    if not (hasattr(page, "assembled") and page.assembled):
        return kv_regions
    body = getattr(page.assembled, "body", []) or []
    for element in body:
        label = ""
        if hasattr(element, "label"):
            label = element.label.value if hasattr(element.label, "value") else str(element.label)
        if label != "key_value_region":
            continue
        region = {"type": "key_value_region", "bbox": None, "cells": [], "extracted_fields": {}}
        if hasattr(element, "cluster") and element.cluster:
            cluster = element.cluster
            if hasattr(cluster, "bbox"):
                bb = cluster.bbox
                region["bbox"] = {"l": bb.l, "t": bb.t, "r": bb.r, "b": bb.b}
            raw_cells = getattr(cluster, "cells", []) or []
            sorted_cells = sort_cells_spatially(raw_cells)
            for cell in sorted_cells:
                text = ""
                if hasattr(cell, "text"):
                    text = (cell.text or "").strip()
                if not text:
                    continue
                bbox_obj = BBox.from_cell(cell)
                cell_entry = {
                    "text": text,
                    "semantic_class": _classify_kv_cell(text),
                    "from_ocr": getattr(cell, "from_ocr", False),
                    "confidence": getattr(cell, "confidence", 1.0),
                    "bbox": bbox_obj.to_dict() if bbox_obj else None,
                }
                region["cells"].append(cell_entry)
        kv_regions.append(region)
    return kv_regions

def _extract_table_from_page(page, page_no: int) -> List[Dict[str, Any]]:
    tables = []
    if not (hasattr(page, "predictions") and page.predictions):
        return tables
    pred = page.predictions
    if not (hasattr(pred, "tablestructure") and pred.tablestructure):
        return tables
    table_map = getattr(pred.tablestructure, "table_map", {}) or {}
    for table_id, tbl in table_map.items():
        num_rows = tbl.num_rows
        num_cols = tbl.num_cols
        raw_cells = getattr(tbl, "table_cells", []) or []
        if num_rows == 0 or num_cols == 0:
            continue
        actual_max_row = max((getattr(c, "start_row_offset_idx", 0) + (getattr(c, "row_span", 1) or 1) - 1) for c in raw_cells) + 1 if raw_cells else num_rows
        actual_max_col = max((getattr(c, "start_col_offset_idx", 0) + (getattr(c, "col_span", 1) or 1) - 1) for c in raw_cells) + 1 if raw_cells else num_cols
        num_rows = max(num_rows, actual_max_row)
        num_cols = max(num_cols, actual_max_col)
        matrix: List[List[Optional[str]]] = [[None] * num_cols for _ in range(num_rows)]
        cell_objects: List[Dict] = []
        for cell in raw_cells:
            row = getattr(cell, "start_row_offset_idx", 0)
            col = getattr(cell, "start_col_offset_idx", 0)
            row_span = getattr(cell, "row_span", 1) or 1
            col_span = getattr(cell, "col_span", 1) or 1
            text = (getattr(cell, "text", "") or "").strip()
            text = re.sub(r'\s+', ' ', text)   # supprimer les sauts de ligne et espaces multiples
            is_col_header = getattr(cell, "column_header", False)
            is_row_header = getattr(cell, "row_header", False)
            is_row_section = getattr(cell, "row_section", False)
            bbox_dict = None
            if hasattr(cell, "bbox") and cell.bbox:
                b = cell.bbox
                bbox_dict = {"l": b.l, "t": b.t, "r": b.r, "b": b.b}
            cell_obj = {
                "row": row, "col": col, "row_span": row_span, "col_span": col_span,
                "text": text, "column_header": is_col_header, "row_header": is_row_header,
                "row_section": is_row_section, "amount": None, "bbox": bbox_dict,
            }
            cell_objects.append(cell_obj)
            for dr in range(row_span):
                for dc in range(col_span):
                    r2, c2 = row + dr, col + dc
                    if r2 < num_rows and c2 < num_cols:
                        matrix[r2][c2] = text
        header_rows: Dict[int, Dict[int, str]] = defaultdict(dict)
        data_start_row = 0
        for c_obj in cell_objects:
            if c_obj["column_header"]:
                header_rows[c_obj["row"]][c_obj["col"]] = c_obj["text"]
                data_start_row = max(data_start_row, c_obj["row"] + 1)
        merged_headers: List[str] = [""] * num_cols
        for row_idx in sorted(header_rows.keys()):
            for col_idx, text in header_rows[row_idx].items():
                col_span = 1
                for c_obj in cell_objects:
                    if c_obj["column_header"] and c_obj["row"] == row_idx and c_obj["col"] == col_idx:
                        col_span = c_obj["col_span"]
                        break
                for span_offset in range(col_span):
                    target_col = col_idx + span_offset
                    if target_col < num_cols:
                        sep = " " if merged_headers[target_col] else ""
                        merged_headers[target_col] += sep + text
        # == AJOUT : déduplication des headers fusionnés ==
        merged_headers = _deduplicate_merged_headers(merged_headers)
        col_semantics = _detect_column_semantics(merged_headers)
        table_bbox = None
        if hasattr(tbl, "cluster") and tbl.cluster and hasattr(tbl.cluster, "bbox"):
            bb = tbl.cluster.bbox
            table_bbox = {"l": bb.l, "t": bb.t, "r": bb.r, "b": bb.b}
        tables.append({
            "table_id": str(table_id),
            "page_no": page_no,
            "num_rows": num_rows,
            "num_cols": num_cols,
            "data_start_row": data_start_row,
            "column_headers_raw": merged_headers,
            "column_semantics": col_semantics,
            "matrix": matrix,
            "cells": cell_objects,
            "bbox": table_bbox,
            "raw_cells": raw_cells,
        })
    return tables

def _collect_raw_text(page) -> str:
    text_parts = []
    if not (hasattr(page, "parsed_page") and page.parsed_page):
        return ""
    cells = getattr(page.parsed_page, "textline_cells", []) or []
    def sort_key(c):
        if hasattr(c, "rect") and c.rect:
            cy = (c.rect.r_y0 + c.rect.r_y2) / 2
            cx = (c.rect.r_x0 + c.rect.r_x1) / 2
        else:
            cy, cx = 0, 0
        return (round(cy / 3), cx)
    for cell in sorted(cells, key=sort_key):
        text = (getattr(cell, "text", "") or "").strip()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)

def extract_invoice(
    input_path: str,
    output_path: Optional[str] = None,
    max_pages: int = 100,
    page_range: tuple = (1, 999999),
) -> Dict[str, Any]:
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Fichier introuvable: {input_path}")
    suffix = input_file.suffix.lower()
    if suffix in (".pdf",):
        input_format = InputFormat.PDF
    elif suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"):
        input_format = InputFormat.IMAGE
    else:
        raise ValueError(f"Format non supporté: {suffix}")
    _log.info(f"[Extraction] Démarrage → {input_file.name}")
    converter = DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.IMAGE])
    try:
        result = converter.convert(source=input_file, raises_on_error=False,
                                   max_num_pages=max_pages, page_range=page_range)
    except Exception as e:
        _log.error(f"Erreur conversion : {e}")
        raise
    _log.info(f"[Extraction] Statut: {result.status.value} | Pages: {len(result.pages)}")
    timings_clean: Dict[str, Any] = {}
    if hasattr(result, "timings") and result.timings:
        for k, v in result.timings.items():
            if hasattr(v, "times"):
                timings_clean[k] = {
                    "total_sec": round(sum(v.times), 3),
                    "count": v.count,
                    "avg_sec": round(sum(v.times) / max(v.count, 1), 3),
                }
    output: Dict[str, Any] = {
        "metadata": {
            "file": str(input_file),
            "format": input_format.value,
            "status": result.status.value,
            "page_count": len(result.pages),
            "document_hash": result.input.document_hash if result.input else None,
            "timings": timings_clean,
        },
        "document_info": {},
        "pages": [],
        "tables": [],
        "raw_text": "",
    }
    all_raw_text_parts: List[str] = []
    all_page_kv: List[List[Dict]] = []
    all_tables_flat: List[Dict] = []
    for page in result.pages:
        page_no = page.page_no
        headers_info = _extract_page_headers(page)
        kv_regions = _extract_kv_regions(page)
        all_page_kv.append(kv_regions)
        tables = _extract_table_from_page(page, page_no)
        all_tables_flat.extend(tables)
        raw_text = _collect_raw_text(page)
        all_raw_text_parts.append(f"=== Page {page_no} ===\n{raw_text}")
        page_size = None
        if hasattr(page, "size") and page.size:
            page_size = {"width": page.size.width, "height": page.size.height}
        output["pages"].append({
            "page_no": page_no,
            "size": page_size,
            "page_number_in_doc": headers_info.get("page_number_raw"),
            "total_pages_in_doc": headers_info.get("total_pages"),
            "docusign_id": headers_info.get("docusign_id"),
            "headers": headers_info["headers"],
            "kv_regions": kv_regions,
            "tables": [{k: v for k, v in t.items() if k not in ("cells", "raw_cells", "matrix")}
                       for t in tables],
            "table_count": len(tables),
            "raw_text": raw_text,
        })
    output["tables"] = all_tables_flat
    # Agrégation intelligente des champs KV pour document_info
    kv_aggregated: Dict[str, Any] = {}
    # On parcourt toutes les régions KV pour extraire paires clé-valeur
    for page_kv_list in all_page_kv:
        for region in page_kv_list:
            cells = region["cells"]
            # Stratégie : on groupe les cellules proches spatialement pour former des paires
            # Ici on utilise une heuristique simple : une cellule "label" suivie d'une "valeur" sur la même ligne ou légèrement à droite
            for i in range(len(cells)-1):
                lbl = cells[i]
                val = cells[i+1]
                if lbl["semantic_class"].endswith("_label") or lbl["semantic_class"] in ("document_type",):
                    key = lbl["semantic_class"].replace("_label", "")
                    if key not in kv_aggregated:
                        kv_aggregated[key] = val["text"]
                elif lbl["semantic_class"] == "date":
                    if "date" not in kv_aggregated:
                        kv_aggregated["date"] = lbl["text"]
                elif lbl["semantic_class"] == "amount" and val["semantic_class"] == "amount":
                    pass  # éviter d'écraser
            # Détection simple de période via regex dans tout le texte KV
            for cell in cells:
                t = cell["text"]
                m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})", t)
                if m and "period" not in kv_aggregated:
                    kv_aggregated["period"] = m.group(1)
                m = re.search(r"(?:invoice|facture|n°)\s*[:#]?\s*([\w/-]+)", t, re.I)
                if m and "invoice_number" not in kv_aggregated:
                    kv_aggregated["invoice_number"] = m.group(1)
    for page_data in output["pages"]:
        if page_data.get("docusign_id") and "docusign_id" not in kv_aggregated:
            kv_aggregated["docusign_id"] = page_data["docusign_id"]
        if page_data.get("total_pages_in_doc") and "total_pages_in_doc" not in kv_aggregated:
            kv_aggregated["total_pages_in_doc"] = page_data["total_pages_in_doc"]
    output["document_info"] = kv_aggregated
    output["raw_text"] = "\n\n".join(all_raw_text_parts)
    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        _log.info(f"[Extraction] Résultat → {out_file}")
    return output

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="DocCore – Extraction Bridge")
    parser.add_argument("input", help="Fichier PDF ou image")
    parser.add_argument("-o", "--output", help="JSON de sortie")
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    output_path = args.output or (Path(args.input).stem + "_extraction.json")
    t_start = time.perf_counter()
    try:
        result = extract_invoice(input_path=args.input, output_path=output_path, max_pages=args.max_pages)
    except Exception as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    t_total = time.perf_counter() - t_start
    print(f"Extraction terminée en {t_total:.3f}s → {output_path}")

if __name__ == "__main__":
    main()