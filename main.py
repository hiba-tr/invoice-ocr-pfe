#!/usr/bin/env python3
"""
DocCore - Facture Extraction Tool
Test script for PDF and image invoice extraction
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Ajouter le chemin du projet si nécessaire
sys.path.insert(0, str(Path(__file__).parent))

from document_converter import DocumentConverter
from datamodel.base_models import InputFormat
from datamodel.settings import settings

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_log = logging.getLogger(__name__)


def extract_invoice(
    input_path: str,
    output_path: Optional[str] = None,
    max_pages: int = 100,
    page_range: tuple = (1, 999999)
) -> dict:
    """
    Extrait le contenu d'une facture (PDF ou image)
    
    Args:
        input_path: Chemin vers le fichier (PDF, JPG, PNG, etc.)
        output_path: Chemin de sortie pour le JSON (optionnel)
        max_pages: Nombre maximum de pages à traiter
        page_range: Plage de pages (début, fin)
    
    Returns:
        Dictionnaire contenant le résultat de l'extraction
    """
    
    input_file = Path(input_path)
    
    if not input_file.exists():
        raise FileNotFoundError(f"Fichier introuvable: {input_path}")
    
    # Déterminer le format d'entrée
    suffix = input_file.suffix.lower()
    if suffix in ['.pdf']:
        input_format = InputFormat.PDF
    elif suffix in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp']:
        input_format = InputFormat.IMAGE
    else:
        raise ValueError(f"Format non supporté: {suffix}. Utilisez PDF ou image.")
    
    _log.info(f"Traitement du fichier: {input_file.name} ({input_format.value})")
    
    # Créer le convertisseur
    # Autoriser uniquement les formats PDF et IMAGE
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
    )
    
    # Effectuer la conversion
    try:
        result = converter.convert(
            source=input_file,
            raises_on_error=False,
            max_num_pages=max_pages,
            page_range=page_range
        )
        
        _log.info(f"Statut de conversion: {result.status.value}")
        
        # Construire le résultat
        output_data = {
            "file": str(input_file),
            "format": input_format.value,
            "status": result.status.value,
            "pages": [],
            "text": "",
            "metadata": {
                "page_count": len(result.pages),
                "document_hash": result.input.document_hash if result.input else None
            }
        }
        
        # Extraire le texte de chaque page
        full_text = []
        
        for page in result.pages:
            page_data = {
                "page_no": page.page_no,
                "size": {
                    "width": page.size.width if page.size else 0,
                    "height": page.size.height if page.size else 0
                } if page.size else None,
                "text": ""
            }
            
            # Extraire le texte des cellules
            if hasattr(page, 'cells') and page.cells:
                page_text = "\n".join([cell.text for cell in page.cells if cell.text])
                page_data["text"] = page_text
                full_text.append(f"--- Page {page.page_no} ---\n{page_text}")
            
            # Alternative: utiliser parsed_page si disponible
            elif hasattr(page, 'parsed_page') and page.parsed_page:
                if hasattr(page.parsed_page, 'textline_cells'):
                    page_text = "\n".join([
                        cell.text for cell in page.parsed_page.textline_cells 
                        if cell.text
                    ])
                    page_data["text"] = page_text
                    full_text.append(f"--- Page {page.page_no} ---\n{page_text}")
            
            output_data["pages"].append(page_data)
        
        output_data["text"] = "\n".join(full_text)
        
        # Ajouter les informations sur les tables si présentes
        tables = []
        for page in result.pages:
            if hasattr(page, 'predictions') and page.predictions:
                if hasattr(page.predictions, 'tablestructure') and page.predictions.tablestructure:
                    for table_id, table in page.predictions.tablestructure.table_map.items():
                        table_data = {
                            "page_no": page.page_no,
                            "table_id": table_id,
                            "num_rows": table.num_rows,
                            "num_cols": table.num_cols,
                            "cells": []
                        }
                        for cell in table.table_cells:
                            table_data["cells"].append({
                                "text": cell.text if hasattr(cell, 'text') else "",
                                "row": cell.start_row_offset_idx if hasattr(cell, 'start_row_offset_idx') else 0,
                                "col": cell.start_col_offset_idx if hasattr(cell, 'start_col_offset_idx') else 0,
                                "row_span": cell.row_span if hasattr(cell, 'row_span') else 1,
                                "col_span": cell.col_span if hasattr(cell, 'col_span') else 1
                            })
                        tables.append(table_data)
        
        output_data["tables"] = tables
        
        # Ajouter les erreurs éventuelles
        if result.errors:
            output_data["errors"] = [
                {"message": err.error_message, "component": err.component_type.value}
                for err in result.errors
            ]
        
        # Sauvegarder en JSON si output_path est fourni
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            _log.info(f"Résultat sauvegardé dans: {output_file}")
        
        return output_data
        
    except Exception as e:
        _log.error(f"Erreur lors de la conversion: {e}")
        raise


def main():
    """Fonction principale pour le test"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='DocCore - Extraction de factures PDF/Image')
    parser.add_argument('input', help='Chemin vers le fichier PDF ou image')
    parser.add_argument('-o', '--output', help='Chemin de sortie pour le JSON (optionnel)')
    parser.add_argument('--max-pages', type=int, default=100, help='Nombre maximum de pages')
    parser.add_argument('--start-page', type=int, default=1, help='Page de début')
    parser.add_argument('--end-page', type=int, default=999999, help='Page de fin')
    parser.add_argument('-v', '--verbose', action='store_true', help='Afficher les logs détaillés')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Déterminer le chemin de sortie par défaut
    output_path = args.output
    if not output_path:
        input_file = Path(args.input)
        output_path = input_file.stem + "_output.json"
    
    # Extraire la facture
    try:
        result = extract_invoice(
            input_path=args.input,
            output_path=output_path,
            max_pages=args.max_pages,
            page_range=(args.start_page, args.end_page)
        )
        
        print("\n" + "="*50)
        print(f"✅ Extraction terminée avec succès!")
        print(f"📄 Fichier: {result['file']}")
        print(f"📊 Statut: {result['status']}")
        print(f"📑 Pages traitées: {result['metadata']['page_count']}")
        print(f"📝 Texte extrait: {len(result['text'])} caractères")
        
        if result.get('tables'):
            print(f"📊 Tables détectées: {len(result['tables'])}")
        
        if result.get('errors'):
            print(f"⚠️  Erreurs: {len(result['errors'])}")
            for err in result['errors']:
                print(f"   - {err['message']}")
        
        print(f"💾 Résultat sauvegardé: {output_path}")
        print("="*50)
        
        # Afficher un extrait du texte
        if result['text']:
            print("\n📝 Extrait du texte extrait:")
            print("-"*30)
            preview = result['text'][:500]
            print(preview)
            if len(result['text']) > 500:
                print("...")
            print("-"*30)
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()