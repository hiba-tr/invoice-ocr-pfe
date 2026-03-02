import json
import re
from pathlib import Path

# =========================
# GET USEFUL BLOCKS (REAL DOCLING STRUCTURE)
# =========================
def get_useful_blocks(doc):
    blocks = []

    # Text blocks
    for text in doc.get("texts", []):
        blocks.append({
            "type": "text",
            "text": text.get("text", "")
        })

    # Table blocks
    for table in doc.get("tables", []):
        blocks.append({
            "type": "table",
            "data": table.get("data", {})
        })

    return blocks

# =========================
# EXTRACT HEADER (including concession as an object)
# =========================
def extract_header(blocks):
    header = {
        "supplier": None,
        "document_title": None,
        "invoice_date": None,
        "currency": None,
        "concession": {
            "name": None,
            "phase": None
        }
    }

    for block in blocks:
        if block["type"] != "text":
            continue

        text = block["text"]
        lower = text.lower()

        # Supplier
        if "omv" in lower and header["supplier"] is None:
            header["supplier"] = text

        # Document title
        if "joint interest billing" in lower and header["document_title"] is None:
            header["document_title"] = text

        # Invoice date (first occurrence of pattern "DD Month YYYY")
        if header["invoice_date"] is None:
            match = re.search(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", text)
            if match:
                header["invoice_date"] = match.group(0)

        # Currency (look for USD or Dollars)
        if header["currency"] is None:
            if "usd" in lower or "dollars" in lower:
                header["currency"] = "USD"

        # Concession name and phase
        if text == "CHEROUQ":
            header["concession"]["name"] = text
        elif text == "Development":
            header["concession"]["phase"] = text

    return header

# =========================
# EXTRACT TABLE ITEMS (CORRECTED)
# =========================
def extract_items(blocks):
    items = []
    columns = []  # les noms des colonnes (en-têtes) du premier tableau (on les prend du premier tableau rencontré)

    for block in blocks:
        if block["type"] != "table":
            continue

        table_data = block["data"]
        cells = table_data.get("table_cells", [])
        num_rows = table_data.get("num_rows", 0)
        num_cols = table_data.get("num_cols", 0)

        if num_rows == 0 or num_cols == 0:
            continue

        # Construire une matrice vide rows x cols
        matrix = [["" for _ in range(num_cols)] for _ in range(num_rows)]

        # Remplir la matrice avec les textes des cellules
        for cell in cells:
            row = cell.get("start_row_offset_idx", 0)
            col = cell.get("start_col_offset_idx", 0)
            text = cell.get("text", "").strip()
            if row < num_rows and col < num_cols:
                matrix[row][col] = text

        # Extraire les en-têtes de colonnes (première ligne) si ce n'est pas déjà fait
        if not columns and num_rows > 0:
            columns = matrix[0]  # on garde les en-têtes du premier tableau

        # Parcourir les lignes à partir de la ligne 1 (index 1) jusqu'à la fin
        # On ignore la ligne d'en-tête (index 0) et on vérifie que la première cellule n'est pas un titre de section
        for row_idx in range(1, num_rows):
            description = matrix[row_idx][0] if len(matrix[row_idx]) > 0 else ""
            if not description or description == "Item Description":
                continue  # ignorer les lignes vides ou le titre de section
            values = matrix[row_idx][1:]  # valeurs des colonnes 1 à 6 (selon le nombre de colonnes)

            # Créer un item avec description et valeurs associées aux colonnes
            item = {
                "description": description,
                "values": {}
            }
            # Associer chaque valeur au nom de colonne correspondant
            for i, col_name in enumerate(columns[1:]):  # on saute la première colonne (description)
                if i < len(values):
                    item["values"][col_name] = values[i]
            items.append(item)

    return items, columns

# =========================
# BUILD FINAL JSON
# =========================
def build_structured_invoice(header, items, columns):
    return {
        "invoice": {
            "header": header,
            "columns": columns,          # les noms des colonnes (en-têtes)
            "line_items": items,         # liste d'items avec description et valeurs par colonne
            "line_count": len(items)
        }
    }

# =========================
# MAIN FILTER FUNCTION
# =========================
def filter_invoice(input_json_path, output_json_path=None):
    """
    Lit le JSON brut généré par Docling, extrait les informations structurées,
    et retourne le dictionnaire correspondant. Si output_json_path est fourni,
    sauvegarde également le résultat dans ce fichier.
    """
    # Chargement du JSON
    with open(input_json_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    # Récupération des blocs
    blocks = get_useful_blocks(doc)

    # Extraction de l'en-tête
    header = extract_header(blocks)

    # Extraction des lignes et colonnes
    items, columns = extract_items(blocks)

    # Construction du JSON final
    structured_invoice = build_structured_invoice(header, items, columns)

    # Sauvegarde optionnelle
    if output_json_path:
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(structured_invoice, f, indent=2, ensure_ascii=False)

    return structured_invoice

# =========================
# MAIN (pour exécution en ligne de commande)
# =========================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python filter_invoice.py <input_json> [output_json]")
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    result = filter_invoice(input_path, output_path)
    print("✅ Traitement terminé avec succès !")
    if output_path:
        print(f"📄 Fichier généré : {output_path}")
    else:
        print("Résultat (premières lignes) :", str(result)[:200])