#!/usr/bin/env python3
"""
Lit le dump JSON brut de Docling, affiche un résumé et exporte
un fichier JSON clair contenant les matrices de tous les tableaux.
Usage : python filter_dump.py <dump.json> [--output sortie.json]
"""
import json, sys
from pathlib import Path
from collections import defaultdict

def print_sep(title=""):
    print("\n" + "=" * 70)
    if title:
        print(f"  {title}")
        print("=" * 70)

def normalize_header(header: str) -> str:
    return " ".join(header.split())

def main(dump_path: str, output_path: str = None):
    dump_file = Path(dump_path)
    if not dump_file.exists():
        print(f"Fichier introuvable : {dump_file}")
        sys.exit(1)

    with open(dump_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    pages = data.get("pages", [])
    print_sep("RÉSUMÉ DU DUMP DOCLING")
    print(f"Nombre de pages : {len(pages)}")

    export_data = {"pages": []}   # structure pour l'export JSON

    all_tables = []
    for page_idx, page in enumerate(pages, start=1):
        page_no = page.get("page_no", page_idx)
        size = page.get("size", {})
        print_sep(f"Page {page_no} (taille : {size.get('width','?')} x {size.get('height','?')})")

        predictions = page.get("predictions")
        if not predictions:
            print("  Aucune prédiction (pas de tableaux)")
            continue

        tablestructure = predictions.get("tablestructure")
        if not tablestructure:
            print("  Pas de structure de tableau")
            continue

        table_map = tablestructure.get("table_map", {})
        if not table_map:
            print("  Aucun tableau dans table_map")
            continue

        print(f"  Nombre de tableaux : {len(table_map)}")
        page_export = {"page_no": page_no, "tables": []}

        for table_id, tbl in table_map.items():
            num_rows = tbl.get("num_rows", 0)
            num_cols = tbl.get("num_cols", 0)
            cells = tbl.get("table_cells", [])
            print(f"\n    Table ID={table_id} : {num_rows} lignes x {num_cols} colonnes, {len(cells)} cellules")

            # Reconstruction des en-têtes (identique au bridge)
            header_rows = defaultdict(dict)
            data_start_row = 0
            for cell in cells:
                if cell.get("column_header"):
                    r = cell.get("start_row_offset_idx", 0)
                    c = cell.get("start_col_offset_idx", 0)
                    text = cell.get("text", "").strip()
                    header_rows[r][c] = text
                    data_start_row = max(data_start_row, r + 1)

            merged_headers = [""] * num_cols
            for r_idx in sorted(header_rows.keys()):
                for c_idx, text in header_rows[r_idx].items():
                    span = 1
                    for cell in cells:
                        if (cell.get("column_header") and
                            cell.get("start_row_offset_idx") == r_idx and
                            cell.get("start_col_offset_idx") == c_idx):
                            span = cell.get("col_span", 1)
                            break
                    for offset in range(span):
                        if c_idx + offset < num_cols:
                            merged_headers[c_idx + offset] += (" " + text if merged_headers[c_idx + offset] else text)

            merged_headers = [normalize_header(h) for h in merged_headers]
            print(f"    En-têtes : {merged_headers}")

            # Construction de la matrice complète
            matrix = [["" for _ in range(num_cols)] for _ in range(num_rows)]
            for cell in cells:
                r = cell.get("start_row_offset_idx", 0)
                c = cell.get("start_col_offset_idx", 0)
                text = cell.get("text", "").strip()
                rs = cell.get("row_span", 1)
                cs = cell.get("col_span", 1)
                for dr in range(rs):
                    for dc in range(cs):
                        if r+dr < num_rows and c+dc < num_cols:
                            matrix[r+dr][c+dc] = text

            # Extraire seulement les lignes de données (après data_start_row)
            data_matrix = matrix[data_start_row:] if data_start_row < num_rows else []
            print(f"    Data start row : {data_start_row}")
            if data_matrix:
                print("    Aperçu des données :")
                for row in data_matrix[:5]:
                    print(f"      {row}")

            # Ajouter à l'export
            table_export = {
                "table_id": table_id,
                "num_rows": num_rows,
                "num_cols": num_cols,
                "headers": merged_headers,
                "data_start_row": data_start_row,
                "data": data_matrix
            }
            page_export["tables"].append(table_export)

            all_tables.append({
                "page": page_no,
                "table_id": table_id,
                "headers": merged_headers,
                "num_rows": num_rows,
                "num_cols": num_cols,
                "data_start_row": data_start_row
            })

        export_data["pages"].append(page_export)

    print_sep("RÉSUMÉ GLOBAL")
    print(f"Nombre total de tableaux extraits : {len(all_tables)}")
    groups = defaultdict(list)
    for t in all_tables:
        groups[tuple(t["headers"])].append(t)
    print("Groupes par en-têtes :")
    for h, tabs in groups.items():
        print(f"  {len(tabs)} tableau(x) avec en-têtes : {list(h)}")

    # Sauvegarde du JSON exporté
    if output_path is None:
        output_path = dump_file.stem + "_tables.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Export JSON enregistré : {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python filter_dump.py <dump.json> [--output sortie.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    out_file = None
    if len(sys.argv) > 2 and sys.argv[2] == "--output":
        if len(sys.argv) < 4:
            print("Erreur : --output nécessite un chemin")
            sys.exit(1)
        out_file = sys.argv[3]
    main(input_file, out_file)