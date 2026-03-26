#!/usr/bin/env python3
"""
Post-traitement générique des factures extraites par DocCore
Nettoie et structure les données sans présupposés sur le contenu
"""

import json, sys
import re
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Tuple
from collections import Counter


def detect_common_prefixes(table_data: List[List[str]]) -> Set[str]:
    """
    Détecte automatiquement les préfixes communs dans la première colonne
    sans préfixes prédéfinis
    """
    if not table_data:
        return set()
    
    # Extraire la première colonne
    first_col = [row[0] for row in table_data if row and row[0] and isinstance(row[0], str)]
    
    if len(first_col) < 2:
        return set()
    
    prefixes = set()
    
    # Analyser les patterns de répétition
    for text in first_col:
        # Chercher des motifs comme "WORD WORD ... WORD" (au moins 2 mots)
        words = text.split()
        if len(words) >= 2:
            # Le préfixe potentiel est le premier mot ou les premiers mots
            for prefix_len in range(1, min(3, len(words))):  # Max 2 mots comme préfixe
                prefix = " ".join(words[:prefix_len])
                
                # Vérifier si ce préfixe apparaît dans plusieurs cellules
                count = sum(1 for cell in first_col if cell.startswith(prefix + " "))
                if count >= 2:  # Au moins 2 occurrences
                    prefixes.add(prefix)
    
    return prefixes


def clean_table_label(text: str, prefixes: Set[str]) -> str:
    """Nettoie un libellé en supprimant le préfixe s'il existe"""
    if not text or not isinstance(text, str):
        return text
    
    # Trier les préfixes du plus long au plus court
    for prefix in sorted(prefixes, key=len, reverse=True):
        if text.startswith(prefix + " "):
            cleaned = text[len(prefix) + 1:]
            if cleaned:
                return cleaned
        elif text.startswith(prefix) and text != prefix:
            cleaned = text[len(prefix):].strip()
            if cleaned:
                return cleaned
    
    return text


def parse_info_block(cells: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Parse générique le bloc d'informations
    Détecte automatiquement les paires clé-valeur
    """
    info = {}
    
    for i, cell_data in enumerate(cells):
        text = cell_data.get("text", "")
        if not text:
            continue
        
        # Détecter les paires clé-valeur avec ":"
        if ':' in text:
            parts = text.split(':', 1)
            key = parts[0].strip().lower().replace(' ', '_')
            value = parts[1].strip()
            if key and value:
                info[key] = value
                continue
        
        # Détecter les champs communs par pattern
        text_lower = text.lower()
        
        # Dates
        date_match = re.search(r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', text)
        if date_match and not info.get('date'):
            info['date'] = date_match.group()
        
        # Montants avec devise
        amount_match = re.search(r'([\d,\.]+)\s+(USD|EUR|GBP|TND|DZD)', text, re.IGNORECASE)
        if amount_match and not info.get('amount'):
            info['amount'] = amount_match.group(1)
            info['currency'] = amount_match.group(2).upper()
        
        # Noms de société (mots en majuscules avec GmbH, SA, SARL, etc.)
        if re.search(r'\b(GmbH|SA|SARL|S\.A\.|Ltd|LLC)\b', text):
            if not info.get('company'):
                info['company'] = text
        
        # Identifiants
        if re.search(r'ID[: ]+[A-Z0-9\-]+', text, re.IGNORECASE):
            id_match = re.search(r'ID[: ]+([A-Z0-9\-]+)', text, re.IGNORECASE)
            if id_match and not info.get('document_id'):
                info['document_id'] = id_match.group(1)
        
        # Détecter automatiquement les paires adjacentes
        if i + 1 < len(cells):
            next_text = cells[i + 1].get("text", "")
            if next_text and not any(c.isdigit() for c in next_text) and len(next_text) < 30:
                # Si le texte actuel est court et le suivant aussi, c'est peut-être une paire
                if len(text) < 30 and not info.get(text.lower().replace(' ', '_')):
                    info[text.lower().replace(' ', '_')] = next_text
    
    return info


def extract_matrix_from_table(table: Dict[str, Any]) -> List[List[str]]:
    """Extrait la matrice d'un tableau à partir des cellules"""
    num_rows = table.get("num_rows", 0)
    num_cols = table.get("num_cols", 0)
    cells = table.get("cells", [])
    
    if num_rows == 0 or num_cols == 0:
        return []
    
    # Créer une matrice vide
    matrix = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    
    # Remplir la matrice
    for cell in cells:
        row = cell.get("row", 0)
        col = cell.get("col", 0)
        text = cell.get("text", "")
        if row < num_rows and col < num_cols:
            matrix[row][col] = text
    
    return matrix


def detect_header_row(matrix: List[List[str]]) -> Tuple[int, List[str]]:
    """
    Détecte automatiquement la ligne d'en-tête d'un tableau
    Retourne (index_ligne, en_tetes)
    """
    if not matrix:
        return -1, []
    
    best_score = 0
    best_idx = -1
    best_headers = []
    
    for i, row in enumerate(matrix):
        # Critères pour une ligne d'en-tête:
        # - Contient des mots-clés de colonnes
        # - Peu de cellules vides
        # - Contient des mots en majuscule
        # - Pas de valeurs numériques pures
        
        row_text = " ".join(str(cell) for cell in row).lower()
        non_empty = sum(1 for cell in row if cell and str(cell).strip())
        non_empty_ratio = non_empty / len(row) if row else 0
        
        # Mots-clés d'en-tête
        header_keywords = ['description', 'item', 'well', 'facility', 'amount', 
                        'total', 'date', 'reference', 'quantity', 'price',
                        'unit', 'cost', 'value', 'name', 'id']
        keyword_score = sum(2 for kw in header_keywords if kw in row_text)
        
        # Score pour les cellules en majuscule
        uppercase_score = 0
        numeric_count = 0
        for cell in row:
            if cell and isinstance(cell, str):
                if cell.isupper() and len(cell) > 1:
                    uppercase_score += 1
                if re.match(r'^[\d,\.\-\(\)]+$', cell):
                    numeric_count += 1
        
        # Score total
        score = non_empty_ratio * 3 + keyword_score + uppercase_score * 0.5 - numeric_count
        
        if score > best_score:
            best_score = score
            best_idx = i
            best_headers = row
    
    return best_idx, best_headers


def clean_table(matrix: List[List[str]]) -> Dict[str, Any]:
    """Nettoie et structure un tableau de façon générique"""
    if not matrix:
        return {"headers": [], "data": [], "rows": 0, "columns": 0}
    
    # Détecter automatiquement les préfixes communs
    prefixes = detect_common_prefixes(matrix)
    
    # Nettoyer la première colonne
    cleaned_matrix = []
    for row in matrix:
        cleaned_row = row.copy()
        if row and prefixes and row[0]:
            cleaned_row[0] = clean_table_label(row[0], prefixes)
        cleaned_matrix.append(cleaned_row)
    
    # Détecter automatiquement la ligne d'en-tête
    header_idx, headers = detect_header_row(cleaned_matrix)
    
    if header_idx >= 0:
        # Extraire les données (tout après la ligne d'en-tête)
        data = [row for i, row in enumerate(cleaned_matrix) if i != header_idx]
        # Nettoyer les lignes vides
        data = [row for row in data if any(cell and str(cell).strip() for cell in row)]
        
        # S'assurer que toutes les lignes ont le même nombre de colonnes que les en-têtes
        if headers:
            target_len = len(headers)
            data = [row[:target_len] if len(row) > target_len else row + [""] * (target_len - len(row)) 
                    for row in data]
    else:
        # Pas d'en-tête détecté
        headers = []
        data = cleaned_matrix
    
    # Nettoyer les colonnes vides à la fin
    if data:
        max_cols = max(len(row) for row in data) if data else 0
        # Trouver la dernière colonne avec des données non vides
        while max_cols > 1:
            has_data = any(len(row) > max_cols - 1 and row[max_cols - 1] for row in data)
            if has_data:
                break
            max_cols -= 1
        
        if max_cols < len(data[0]) if data else 0:
            data = [row[:max_cols] for row in data]
            if headers and len(headers) > max_cols:
                headers = headers[:max_cols]
    
    return {
        "headers": headers,
        "data": data,
        "rows": len(data),
        "columns": len(headers) if headers else (max_cols if data else 0)
    }


def extract_totals_from_data(data: List[List[str]]) -> Dict[str, str]:
    """Extrait les totaux des données du tableau de façon générique"""
    totals = {}
    
    for row in data:
        row_str = " ".join(str(cell) for cell in row).lower()
        
        # Détecter les lignes de total
        if any(keyword in row_str for keyword in ['total', 'grand total', 'sum', 'subtotal']):
            # Chercher les valeurs numériques dans la ligne
            amounts = []
            for cell in row:
                if cell and isinstance(cell, str):
                    # Nettoyer le montant (enlever les parenthèses pour les négatifs)
                    clean_amount = cell.strip().replace('(', '-').replace(')', '').replace(',', '')
                    if re.match(r'^[\d\.\-]+$', clean_amount):
                        amounts.append(cell)
            
            if amounts:
                # Identifier le type de total par le texte de la ligne
                if 'usd' in row_str or 'dollar' in row_str:
                    totals['total_usd'] = amounts[-1]
                elif 'omv' in row_str:
                    totals['total_omv_share'] = amounts[-1]
                elif 'etap' in row_str:
                    totals['total_etap_share'] = amounts[-1]
                else:
                    # Total générique
                    totals['total'] = amounts[-1]
    
    return totals


def postprocess_invoice(raw_json_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Post-traite le JSON brut pour produire une version structurée
    """
    
    # Charger le JSON brut
    with open(raw_json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    # Structure finale
    structured = {
        "file": raw_data.get("file"),
        "format": raw_data.get("format"),
        "status": raw_data.get("status"),
        "metadata": raw_data.get("metadata", {}),
        "document": {
            "headers": [],
            "company_info": {},
            "tables": [],
            "totals": {}
        }
    }
    
    # =========================================================
    # 1. EXTRAIRE LES EN-TÊTES ET INFOS SOCIÉTÉ
    # =========================================================
    all_headers = []
    all_key_values = []
    
    for page in raw_data.get("pages", []):
        # Extraire les en-têtes
        for header in page.get("headers", []):
            header_text = header.get("text", "")
            if header_text and header_text not in all_headers:
                all_headers.append(header_text)
        
        # Extraire les key_values
        for kv in page.get("key_values", []):
            for cell in kv.get("cells", []):
                all_key_values.append(cell)
    
    structured["document"]["headers"] = all_headers
    
    # Parser les informations société
    if all_key_values:
        structured["document"]["company_info"] = parse_info_block(all_key_values)
    
    # =========================================================
    # 2. EXTRAIRE ET NETTOYER LES TABLEAUX
    # =========================================================
    all_tables = []
    
    for page in raw_data.get("pages", []):
        for table in page.get("tables", []):
            # Extraire la matrice
            matrix = extract_matrix_from_table(table)
            
            if matrix:
                # Nettoyer le tableau
                cleaned = clean_table(matrix)
                if cleaned["data"] or cleaned["headers"]:
                    all_tables.append(cleaned)
    
    structured["document"]["tables"] = all_tables
    
    # =========================================================
    # 3. EXTRAIRE LES TOTAUX
    # =========================================================
    totals = {}
    
    # Chercher les totaux dans les tableaux
    for table in all_tables:
        table_totals = extract_totals_from_data(table["data"])
        for key, value in table_totals.items():
            if value and not totals.get(key):
                totals[key] = value
    
    # Chercher les totaux dans les totaux déjà extraits par main.py
    if raw_data.get("totals"):
        for key, value in raw_data["totals"].items():
            if value and not totals.get(key):
                totals[key] = value
    
    structured["document"]["totals"] = totals
    
    # =========================================================
    # 4. SAUVEGARDE
    # =========================================================
    if output_path:
        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON structuré sauvegardé: {output_file}")
    
    return structured


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Post-traitement générique des factures DocCore')
    parser.add_argument('input_json', help='JSON brut généré par main.py')
    parser.add_argument('-o', '--output', help='JSON de sortie structuré')
    
    args = parser.parse_args()
    
    output_path = args.output
    if not output_path:
        input_path = Path(args.input_json)
        output_path = input_path.stem + "_structured.json"
    
    try:
        result = postprocess_invoice(args.input_json, output_path)
        
        print("\n" + "="*60)
        print("📊 RÉSUMÉ DE L'EXTRACTION STRUCTURÉE")
        print("="*60)
        
        info = result["document"]["company_info"]
        if info:
            print("\n🏢 INFORMATIONS DÉTECTÉES:")
            for key, value in list(info.items())[:6]:
                print(f"   • {key.replace('_', ' ').title()}: {value}")
        
        headers = result["document"]["headers"]
        if headers:
            print("\n📌 EN-TÊTES:")
            for h in headers[:5]:
                print(f"   • {h}")
        
        totals = result["document"].get("totals", {})
        if totals:
            print("\n💰 TOTAUX:")
            for key, value in totals.items():
                print(f"   • {key.replace('_', ' ').title()}: {value}")
        
        tables = result["document"]["tables"]
        if tables:
            print(f"\n📊 TABLEAUX: {len(tables)}")
            for i, table in enumerate(tables):
                print(f"\n   Tableau {i+1}: {table['rows']} lignes, {table['columns']} colonnes")
                if table["headers"]:
                    preview = ', '.join(str(h) for h in table["headers"][:6])
                    print(f"   Colonnes: {preview}")
        
        print(f"\n💾 Fichier: {output_path}")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()