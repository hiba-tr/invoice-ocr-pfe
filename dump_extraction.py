#!/usr/bin/env python3
"""
dump_extraction.py
------------------
Exécute la conversion docling sur un PDF et dump TOUTE la structure
du ConversionResult en JSON brut, pour analyse de la couche postprocess.

Usage:
    python dump_extraction.py <fichier.pdf> [-o output.json]
"""

import json
import sys
import logging
from pathlib import Path

# ── Désactiver les logs docling pour garder la sortie propre ──────────────
logging.basicConfig(level=logging.WARNING)

from backend.extraction.engine.document_converter import DocumentConverter
from backend.extraction.engine.datamodel.base_models import InputFormat


def safe_serialize(obj, depth=0, max_depth=12):
    """
    Sérialise récursivement n'importe quel objet Python en structure
    JSON-compatible, en révélant tous les champs disponibles.
    """
    if depth > max_depth:
        return f"<max_depth_reached: {type(obj).__name__}>"

    # Types natifs JSON
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # Listes / tuples
    if isinstance(obj, (list, tuple)):
        return [safe_serialize(item, depth + 1, max_depth) for item in obj]

    # Dicts
    if isinstance(obj, dict):
        return {k: safe_serialize(v, depth + 1, max_depth) for k, v in obj.items()}

    # Pydantic v1 / v2
    if hasattr(obj, "model_dump"):
        try:
            return safe_serialize(obj.model_dump(), depth + 1, max_depth)
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return safe_serialize(obj.dict(), depth + 1, max_depth)
        except Exception:
            pass

    # Objets avec __dict__
    if hasattr(obj, "__dict__"):
        result = {"__type__": type(obj).__name__}
        for k, v in obj.__dict__.items():
            if k.startswith("__"):
                continue
            try:
                result[k] = safe_serialize(v, depth + 1, max_depth)
            except Exception as e:
                result[k] = f"<serialize_error: {e}>"
        return result

    # Enums
    if hasattr(obj, "value"):
        return obj.value

    # Fallback
    try:
        return str(obj)
    except Exception:
        return f"<unserializable: {type(obj).__name__}>"


def dump_result_structure(result) -> dict:
    """
    Construit un dump structuré et lisible du ConversionResult,
    en ciblant les zones utiles pour le postprocess.
    """
    dump = {
        "status": safe_serialize(result.status),
        "input": {
            "file": str(result.input.file) if result.input else None,
            "document_hash": result.input.document_hash if result.input else None,
            "format": safe_serialize(result.input.format) if result.input else None,
        },
        "errors": safe_serialize(getattr(result, "errors", [])),
        "timings": safe_serialize(getattr(result, "timings", {})),
        "num_pages": len(result.pages) if hasattr(result, "pages") else 0,
        "pages": [],
        # ── Dump du document Docling (si disponible) ──────────────────────
        "document_keys": [],
        "document_export": None,
    }

    # ── Document-level (export_to_dict si disponible) ─────────────────────
    if hasattr(result, "document") and result.document is not None:
        dump["document_keys"] = list(result.document.__dict__.keys()) \
            if hasattr(result.document, "__dict__") else []
        # Tentative d'export natif docling
        for export_method in ["export_to_dict", "model_dump", "dict"]:
            if hasattr(result.document, export_method):
                try:
                    dump["document_export"] = safe_serialize(
                        getattr(result.document, export_method)()
                    )
                    dump["document_export_method"] = export_method
                    break
                except Exception as e:
                    dump["document_export_error"] = str(e)

    # ── Pages ─────────────────────────────────────────────────────────────
    for page in result.pages:
        page_dump = {
            "page_no": page.page_no,
            "page_keys": list(page.__dict__.keys()) if hasattr(page, "__dict__") else [],
            "size": safe_serialize(page.size) if hasattr(page, "size") else None,
        }

        # assembled
        if hasattr(page, "assembled") and page.assembled:
            asm = page.assembled
            page_dump["assembled"] = {
                "__keys__": list(asm.__dict__.keys()) if hasattr(asm, "__dict__") else [],
                "headers": safe_serialize(getattr(asm, "headers", [])),
                "body_count": len(getattr(asm, "body", []) or []),
                "body_sample": safe_serialize((getattr(asm, "body", []) or [])[:5]),
                "elements_count": len(getattr(asm, "elements", []) or []),
                "elements_sample": safe_serialize((getattr(asm, "elements", []) or [])[:5]),
            }

        # parsed_page
        if hasattr(page, "parsed_page") and page.parsed_page:
            pp = page.parsed_page
            page_dump["parsed_page"] = {
                "__keys__": list(pp.__dict__.keys()) if hasattr(pp, "__dict__") else [],
                "textline_cells_count": len(getattr(pp, "textline_cells", []) or []),
                "textline_cells_sample": safe_serialize(
                    (getattr(pp, "textline_cells", []) or [])[:10]
                ),
            }

        # predictions → tablestructure
        if hasattr(page, "predictions") and page.predictions:
            pred = page.predictions
            page_dump["predictions"] = {
                "__keys__": list(pred.__dict__.keys()) if hasattr(pred, "__dict__") else [],
            }
            if hasattr(pred, "tablestructure") and pred.tablestructure:
                ts = pred.tablestructure
                table_map = getattr(ts, "table_map", {}) or {}
                page_dump["predictions"]["tablestructure"] = {
                    "table_count": len(table_map),
                    "tables": {}
                }
                for tid, tbl in table_map.items():
                    page_dump["predictions"]["tablestructure"]["tables"][str(tid)] = {
                        "num_rows": tbl.num_rows,
                        "num_cols": tbl.num_cols,
                        "cell_count": len(getattr(tbl, "table_cells", []) or []),
                        "cells_sample": safe_serialize(
                            (getattr(tbl, "table_cells", []) or [])[:20]
                        ),
                        "table_object_keys": list(tbl.__dict__.keys())
                            if hasattr(tbl, "__dict__") else []
                    }

        # layout / clusters (si présents)
        for attr in ["layout", "clusters", "cells", "image"]:
            if hasattr(page, attr):
                val = getattr(page, attr)
                if val is not None:
                    page_dump[f"_{attr}_type"] = type(val).__name__
                    if hasattr(val, "__dict__"):
                        page_dump[f"_{attr}_keys"] = list(val.__dict__.keys())

        dump["pages"].append(page_dump)

    return dump


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Dump brut du ConversionResult docling")
    parser.add_argument("input", help="Chemin vers le fichier PDF ou image")
    parser.add_argument("-o", "--output", help="Fichier JSON de sortie (défaut: <input>_dump.json)")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERREUR] Fichier introuvable: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or (input_path.stem + "_dump.json")

    print(f"[INFO] Conversion de: {input_path.name} ...", flush=True)

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
    )

    result = converter.convert(
        source=input_path,
        raises_on_error=False,
        max_num_pages=args.max_pages,
    )

    print(f"[INFO] Statut: {result.status.value}")
    print(f"[INFO] Pages: {len(result.pages)}")
    print(f"[INFO] Sérialisation en cours ...")

    dump = dump_result_structure(result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2)

    print(f"[OK] Dump sauvegardé → {output_path}")
    print(f"     Pages dumpées     : {dump['num_pages']}")
    print(f"     Document export   : {'OUI' if dump.get('document_export') else 'NON'}")
    print(f"     Clés document     : {dump.get('document_keys', [])}")


if __name__ == "__main__":
    main()
