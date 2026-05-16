#!/usr/bin/env python3
"""
Test d'extraction brute Docling - Version corrigée
"""

import json
import sys
from pathlib import Path

# Ajout du chemin pour pouvoir importer correctement
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.extraction.main import extract_invoice_complete


def test_raw_extraction(input_path: str):
    input_path = Path(input_path)
    if not input_path.exists():
        print(f"❌ Fichier non trouvé : {input_path}")
        return None

    print(f"🚀 Test extraction brute Docling")
    print(f"Fichier : {input_path.name}")

    try:
        result = extract_invoice_complete(
            input_path=str(input_path),
            output_path=None,
            max_pages=100
        )

        # Sauvegarde du JSON brut
        output_file = input_path.with_name(input_path.stem + "_RAW_DOCLING.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ Extraction terminée avec succès !")
        print(f"📄 JSON brut sauvegardé → {output_file.name}")
        print(f"📊 Pages traitées : {result.get('metadata', {}).get('page_count', 'N/A')}")
        
        # Résumé rapide
        tables_count = sum(len(page.get('tables', [])) for page in result.get('pages', []))
        print(f"📋 Nombre de tableaux détectés : {tables_count}")
        
        return result

    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("   python test_raw_docling.py \"C:\\Factures\\facture2.pdf\"")
        sys.exit(1)

    test_raw_extraction(sys.argv[1])