#!/usr/bin/env python3
"""
Afficher la structure de ConversionResult
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from document_converter import DocumentConverter
from datamodel.base_models import InputFormat


def show_structure(result):
    """Affiche la structure simple de l'objet"""
    
    print("\n" + "=" * 60)
    print("📊 STRUCTURE DE CONVERSIONRESULT")
    print("=" * 60)
    
    # 1. Infos de base
    print(f"\n✅ Statut: {result.status}")
    print(f"📄 Fichier: {result.input.file}")
    print(f"📑 Pages: {len(result.pages)}")
    
    # 2. Parcourir les pages
    for i, page in enumerate(result.pages[:2]):  # Afficher max 2 pages
        print(f"\n--- PAGE {i+1} ---")
        
        # Texte OCR
        if hasattr(page, 'parsed_page') and page.parsed_page:
            cells = getattr(page.parsed_page, 'textline_cells', [])
            print(f"  📝 Texte: {len(cells)} cellules")
            if cells:
                print(f"     Exemple: '{cells[0].text[:80]}'")
        
        # Tableaux
        if hasattr(page, 'predictions') and page.predictions:
            if hasattr(page.predictions, 'tablestructure') and page.predictions.tablestructure:
                tables = page.predictions.tablestructure.table_map
                print(f"  📊 Tableaux: {len(tables)}")
                for tid, table in tables.items():
                    print(f"     Table {tid}: {table.num_rows} x {table.num_cols}")
        
        # Structure logique
        if hasattr(page, 'assembled') and page.assembled:
            headers = getattr(page.assembled, 'headers', [])
            body = getattr(page.assembled, 'body', [])
            print(f"  🏷️  En-têtes: {len(headers)}")
            print(f"  📄 Éléments: {len(body)}")
    
    print("\n" + "=" * 60)


def main():
    # Chemin du fichier
    file_path = "C:\\Factures\\facture.pdf"  # ← MODIFIE ICI
    
    if not Path(file_path).exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        return
    
    # Créer le convertisseur
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
    )
    
    # Convertir
    print("⏳ Conversion en cours...")
    result = converter.convert(file_path, raises_on_error=False, max_num_pages=2)
    
    # Afficher la structure
    show_structure(result)


if __name__ == "__main__":
    main()