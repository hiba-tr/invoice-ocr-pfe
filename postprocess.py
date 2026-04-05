import json
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Union


def clean_amount(val) -> Optional[float]:
    """
    Convertit une valeur brute (str, int, float) en float propre.
    Retourne None si la valeur est invalide, NaN ou infinie.
    """
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().replace(' ', '').replace(',', '')
        if not s or s in ('-', '.'):
            return None
        # Notation comptable : (123.45) → -123.45
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        try:
            f = float(s)
        except ValueError:
            return None
    elif isinstance(val, (int, float)):
        f = float(val)
    else:
        return None

    if math.isnan(f) or math.isinf(f):
        return None
    return f


def extract_metadata(pages: List[Dict]) -> Dict[str, Any]:
    full_text = " ".join(
        cell.get("text", "")
        for page in pages
        for cell in page.get("text_cells", [])
    )
    metadata: Dict[str, Any] = {
        "company": None,
        "concession": None,
        "date": None,
        "currency": "USD",
    }

    # Société
    if "OMV" in full_text:
        metadata["company"] = "OMV (Tunesien) Production GmbH"

    # Concession
    match = re.search(r'Concession\s*:?\s*([A-Z0-9\s\-]+)', full_text, re.IGNORECASE)
    if match:
        metadata["concession"] = match.group(1).strip()

    # Date — plusieurs formats courants
    for pattern in [
        r'MONTH ENDED:\s*(\d{1,2}\s+\w+\s+\d{4})',
        r'Date\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        r'(\d{1,2}\s+\w+\s+\d{4})',
    ]:
        date_match = re.search(pattern, full_text, re.IGNORECASE)
        if date_match:
            metadata["date"] = date_match.group(1).strip()
            break

    # Devise
    if "EUR" in full_text or "€" in full_text:
        metadata["currency"] = "EUR"
    elif "USD" in full_text or "U.S.Dollars" in full_text or "$" in full_text:
        metadata["currency"] = "USD"
    elif "TND" in full_text or "Dinar" in full_text:
        metadata["currency"] = "TND"

    return metadata


def postprocess_invoice(
    raw_input: Union[str, Path, dict],
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Accepte :
      - un chemin vers un fichier JSON  (str | Path)
      - un dict brut directement        (dict)

    Retourne {"metadata": {...}, "items": [...]}
    """
    if isinstance(raw_input, (str, Path)):
        with open(raw_input, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    else:
        raw_data = raw_input

    pages: List[Dict] = raw_data.get("pages", [])
    metadata = extract_metadata(pages)

    # Récupérer tous les tableaux de toutes les pages
    tables: List[Dict] = []
    for page in pages:
        tables.extend(page.get("tables", []))

    if not tables:
        result = {"metadata": metadata, "items": []}
        _maybe_write(result, output_path)
        return result

    table = tables[0]
    cells = table.get("cells", [])
    num_rows = table.get("num_rows", 0)
    num_cols = table.get("num_cols", 0)

    if num_rows == 0 or num_cols == 0:
        result = {"metadata": metadata, "items": []}
        _maybe_write(result, output_path)
        return result

    # Construire la matrice
    matrix: List[List[str]] = [[""] * num_cols for _ in range(num_rows)]
    for cell in cells:
        r, c = cell.get("row", 0), cell.get("col", 0)
        if r < num_rows and c < num_cols:
            matrix[r][c] = str(cell.get("text", "")).strip()

    # Détecter la ligne d'en-tête
    header_idx = 0
    for i, row in enumerate(matrix):
        row_lower = " ".join(row).lower()
        if "description" in row_lower or "item" in row_lower or "libellé" in row_lower:
            header_idx = i
            break

    headers = [h.strip() for h in matrix[header_idx]]
    data_rows = matrix[header_idx + 1:]

    items: List[Dict[str, Any]] = []
    for row in data_rows:
        # Ignorer les lignes entièrement vides
        if not any(cell.strip() for cell in row):
            continue

        description = row[0].strip() if row else ""
        if not description:
            continue

        valeurs: Dict[str, Optional[float]] = {}
        for col_idx, col_name in enumerate(headers):
            if col_idx == 0 or not col_name:
                continue
            raw_val = row[col_idx] if col_idx < len(row) else None
            val = clean_amount(raw_val)
            if val is not None:
                valeurs[col_name] = val

        items.append({"description": description, "valeurs": valeurs})

    result = {"metadata": metadata, "items": items}
    _maybe_write(result, output_path)
    return result


def _maybe_write(data: dict, output_path: Optional[Union[str, Path]]) -> None:
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)