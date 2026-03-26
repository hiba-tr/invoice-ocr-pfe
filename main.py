#!/usr/bin/env python3
"""
DocCore - Facture Extraction Tool
Extraction complète de toutes les informations d'une facture PDF
"""

import json
import logging
import sys
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from document_converter import DocumentConverter
from datamodel.base_models import InputFormat

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_log = logging.getLogger(__name__)


def extract_cells_from_cluster(cluster) -> List[Dict[str, Any]]:
    """Extrait toutes les cellules d'un cluster avec leurs métadonnées"""
    cells = []
    if hasattr(cluster, 'cells') and cluster.cells:
        for cell in cluster.cells:
            if hasattr(cell, 'text') and cell.text and cell.text.strip():
                cell_data = {
                    "text": cell.text.strip(),
                    "from_ocr": getattr(cell, 'from_ocr', False),
                    "confidence": getattr(cell, 'confidence', 1.0)
                }
                if hasattr(cell, 'rect') and cell.rect:
                    bbox = cell.rect.to_bounding_box()
                    cell_data["bbox"] = {
                        "l": bbox.l,
                        "t": bbox.t,
                        "r": bbox.r,
                        "b": bbox.b
                    }
                cells.append(cell_data)
    return cells


def extract_invoice_complete(
    input_path: str,
    output_path: Optional[str] = None,
    max_pages: int = 100,
    page_range: tuple = (1, 999999)
) -> Dict[str, Any]:
    """
    Extraction COMPLÈTE de la facture avec toutes les informations
    """
    
    input_file = Path(input_path)
    
    if not input_file.exists():
        raise FileNotFoundError(f"Fichier introuvable: {input_path}")
    
    suffix = input_file.suffix.lower()
    if suffix in ['.pdf']:
        input_format = InputFormat.PDF
    elif suffix in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp']:
        input_format = InputFormat.IMAGE
    else:
        raise ValueError(f"Format non supporté: {suffix}")
    
    _log.info(f"Traitement du fichier: {input_file.name}")
    
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
    )
    
    try:
        result = converter.convert(
            source=input_file,
            raises_on_error=False,
            max_num_pages=max_pages,
            page_range=page_range
        )
        
        _log.info(f"Statut de conversion: {result.status.value}")
        
        # Structure complète du résultat
        output_data = {
            "file": str(input_file),
            "format": input_format.value,
            "status": result.status.value,
            "metadata": {
                "page_count": len(result.pages),
                "document_hash": result.input.document_hash if result.input else None
            },
            "pages": [],
            
            "all_text": "",
            "totals": {
                "total_usd": None,
                "total_omv_share": None,
                "total_etap_share": None
                }
        }
        
        full_text_parts = []
        
        for page_idx, page in enumerate(result.pages):
            page_data = {
                "page_no": page.page_no,
                "size": {
                    "width": page.size.width if page.size else 0,
                    "height": page.size.height if page.size else 0
                } if page.size else None,
                "headers": [],
                "info_block": [],
                "key_values": [],
                "text_cells": [],
                "tables": [],
                "raw_text": ""
            }
            
            page_text_parts = []
            
            # =========================================================
            # 1. EXTRAIRE LES EN-TÊTES DE PAGE
            # =========================================================
            if hasattr(page, 'assembled') and page.assembled:
                if hasattr(page.assembled, 'headers') and page.assembled.headers:
                    for header in page.assembled.headers:
                        if hasattr(header, 'text') and header.text and header.text.strip():
                            header_text = header.text.strip()
                            page_data["headers"].append({
                                "text": header_text,
                                "label": header.label.value if hasattr(header, 'label') else "page_header"
                            })
                            page_text_parts.append(f"[EN-TETE] {header_text}")
                
                # =========================================================
                # 2. EXTRAIRE LE BLOC D'INFORMATIONS (key_value_region)
                # =========================================================
                if hasattr(page.assembled, 'body') and page.assembled.body:
                    for element in page.assembled.body:
                        elem_label = ""
                        if hasattr(element, 'label'):
                            elem_label = element.label.value if hasattr(element.label, 'value') else str(element.label)
                        
                        if elem_label == "key_value_region":
                            kv_info = {
                                "type": "key_value_region",
                                "cells": []
                            }
                            
                            # Extraire les cellules du cluster
                            if hasattr(element, 'cluster') and element.cluster:
                                cells = extract_cells_from_cluster(element.cluster)
                                kv_info["cells"] = cells
                                page_data["key_values"].append(kv_info)
                                
                                for cell in cells:
                                    page_text_parts.append(f"[INFO] {cell['text']}")
                            
                            # Texte direct
                            if hasattr(element, 'text') and element.text and element.text.strip():
                                kv_info["text"] = element.text.strip()
                                page_text_parts.append(f"[INFO] {element.text.strip()}")
            
            # =========================================================
            # 3. EXTRAIRE TOUTES LES CELLULES TEXTE (parsed_page)
            # =========================================================
            if hasattr(page, 'parsed_page') and page.parsed_page:
                if hasattr(page.parsed_page, 'textline_cells'):
                    for cell in page.parsed_page.textline_cells:
                        if cell.text and cell.text.strip():
                            cell_data = {
                                "text": cell.text.strip(),
                                "from_ocr": getattr(cell, 'from_ocr', False),
                                "confidence": getattr(cell, 'confidence', 1.0)
                            }
                            if hasattr(cell, 'rect') and cell.rect:
                                bbox = cell.rect.to_bounding_box()
                                cell_data["bbox"] = {
                                    "l": bbox.l,
                                    "t": bbox.t,
                                    "r": bbox.r,
                                    "b": bbox.b
                                }
                            page_data["text_cells"].append(cell_data)
                            page_text_parts.append(cell.text.strip())
            
            # =========================================================
            # 4. EXTRAIRE LES TABLEAUX AVEC TOUTES LES CELLULES
            # =========================================================
            if hasattr(page, 'predictions') and page.predictions:
                if hasattr(page.predictions, 'tablestructure') and page.predictions.tablestructure:
                    for table_id, table in page.predictions.tablestructure.table_map.items():
                        table_data = {
                            "table_id": table_id,
                            "num_rows": table.num_rows,
                            "num_cols": table.num_cols,
                            "cells": [],
                            "matrix": []
                        }
                        
                        # Créer une matrice pour faciliter l'analyse
                        matrix = [[None for _ in range(table.num_cols)] for _ in range(table.num_rows)]
                        
                        for cell in table.table_cells:
                            row = cell.start_row_offset_idx if hasattr(cell, 'start_row_offset_idx') else 0
                            col = cell.start_col_offset_idx if hasattr(cell, 'start_col_offset_idx') else 0
                            
                            cell_text = ""
                            if hasattr(cell, 'text'):
                                cell_text = cell.text or ""
                            elif hasattr(cell, 'token'):
                                cell_text = cell.token or ""
                            
                            cell_data = {
                                "row": row,
                                "col": col,
                                "text": cell_text,
                                "row_span": cell.row_span if hasattr(cell, 'row_span') else 1,
                                "col_span": cell.col_span if hasattr(cell, 'col_span') else 1,
                                "column_header": cell.column_header if hasattr(cell, 'column_header') else False,
                                "row_header": cell.row_header if hasattr(cell, 'row_header') else False
                            }
                            
                            if hasattr(cell, 'bbox') and cell.bbox:
                                cell_data["bbox"] = {
                                    "l": cell.bbox.l,
                                    "t": cell.bbox.t,
                                    "r": cell.bbox.r,
                                    "b": cell.bbox.b
                                }
                            
                            table_data["cells"].append(cell_data)
                            
                            # Remplir la matrice
                            if row < table.num_rows and col < table.num_cols:
                                matrix[row][col] = cell_text
                            
                            # Ajouter le texte au flux principal
                            if cell_text and cell_text.strip():
                                page_text_parts.append(cell_text.strip())
                        
                        # Construire la matrice complète
                        table_data["matrix"] = matrix
                        
                        # Calculer les totaux si présents
                        matrix_str = str(matrix).upper()
                        if "TOTAL" in matrix_str:
                            # Chercher les totaux dans la dernière ligne ou colonne
                            for row_idx, row in enumerate(matrix):
                                for col_idx, cell in enumerate(row):
                                    if cell and "TOTAL" in str(cell).upper():
                                        # Essayer d'extraire les montants dans la même ligne
                                        for c_idx, val in enumerate(row):
                                            if val and re.match(r'^[\d,\.\-\(\)]+$', str(val)):
                                                if "OMV" in str(row).upper():
                                                    output_data["totals"]["total_omv_share"] = val
                                                elif "ETAP" in str(row).upper():
                                                    output_data["totals"]["total_etap_share"] = val
                                                elif "USD" in str(row).upper() or c_idx == len(row)-1:
                                                    output_data["totals"]["total_usd"] = val
                        
                        page_data["tables"].append(table_data)
            
            # =========================================================
            # 5. EXTRAIRE LES ÉLÉMENTS ASSEMBLÉS (pour les blocs de texte)
            # =========================================================
            if hasattr(page, 'assembled') and page.assembled:
                if hasattr(page.assembled, 'elements') and page.assembled.elements:
                    for element in page.assembled.elements:
                        if hasattr(element, 'text') and element.text and element.text.strip():
                            elem_text = element.text.strip()
                            if not any(cell.get("text") == elem_text for cell in page_data["text_cells"]):
                                elem_data = {
                                    "text": elem_text,
                                    "label": element.label.value if hasattr(element, 'label') else "unknown"
                                }
                                page_data["text_cells"].append(elem_data)
                                page_text_parts.append(elem_text)
            
            # =========================================================
            # 6. ASSEMBLER LE TEXTE DE LA PAGE
            # =========================================================
            page_data["raw_text"] = "\n".join(page_text_parts)
            full_text_parts.append(f"--- Page {page.page_no} ---\n{page_data['raw_text']}")
            output_data["pages"].append(page_data)
        
        output_data["all_text"] = "\n".join(full_text_parts)
        
        # =========================================================
        # 7. ANALYSE DES TOTAUX DANS LE TEXTE GLOBAL
        # =========================================================
        all_text = output_data["all_text"]
        
        # Définir les patterns de recherche (pattern, key)
        total_patterns: List[Tuple[str, str]] = [
            (r'TOTAL\s+USD\s*:?\s*([\d,\.\-\(\)]+)', "total_usd"),
            (r'Total\s+USD\s*:?\s*([\d,\.\-\(\)]+)', "total_usd"),
            (r'Grand\s+Total\s*:?\s*([\d,\.\-\(\)]+)', "total_usd"),
            (r'OMV\s+Share\s*:?\s*([\d,\.\-\(\)]+)', "total_omv_share"),
            (r'ETAP\s+Share\s*:?\s*([\d,\.\-\(\)]+)', "total_etap_share"),
        ]
        
        # Chercher aussi des motifs comme "xxx USD" en fin de ligne
        usd_pattern = re.compile(r'([\d,\.]+)\s+USD', re.IGNORECASE)
        usd_matches = usd_pattern.findall(all_text)
        if usd_matches and not output_data["totals"]["total_usd"]:
            # Prendre le dernier montant USD trouvé comme total probable
            output_data["totals"]["total_usd"] = usd_matches[-1]
        
        for pattern, key in total_patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)
            if match and not output_data["totals"][key]:
                output_data["totals"][key] = match.group(1)
        
        # =========================================================
        # 8. EXTRAIRE LES INFORMATIONS CLÉS DE LA FACTURE
        # =========================================================
        invoice_info = {
            "company": None,
            "concession": None,
            "document_type": None,
            "month_ended": None,
            "docusign_id": None
        }
        
        for page in output_data["pages"]:
            for kv in page.get("key_values", []):
                for cell in kv.get("cells", []):
                    text = cell.get("text", "")
                    if "OMV" in text:
                        invoice_info["company"] = text
                    elif "Concession" in text and not invoice_info["concession"]:
                        # Chercher la concession dans les cellules suivantes
                        idx = kv["cells"].index(cell) if cell in kv["cells"] else -1
                        if idx >= 0 and idx + 1 < len(kv["cells"]):
                            invoice_info["concession"] = kv["cells"][idx + 1]["text"]
                    elif "JOINT INTEREST" in text:
                        invoice_info["document_type"] = text
                    elif "MONTH ENDED" in text:
                        month_part = text.replace("MONTH ENDED:", "").strip()
                        invoice_info["month_ended"] = month_part
                    elif "Docusign" in text:
                        docu_part = text.replace("Docusign Envelope ID:", "").strip()
                        invoice_info["docusign_id"] = docu_part
        
        output_data["invoice_info"] = invoice_info
        
        # =========================================================
        # 9. SAUVEGARDE EN JSON
        # =========================================================
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
    import argparse
    
    parser = argparse.ArgumentParser(description='DocCore - Extraction complète de factures')
    parser.add_argument('input', help='Chemin vers le fichier PDF ou image')
    parser.add_argument('-o', '--output', help='Chemin de sortie pour le JSON (optionnel)')
    parser.add_argument('--max-pages', type=int, default=100, help='Nombre maximum de pages')
    parser.add_argument('-v', '--verbose', action='store_true', help='Afficher les logs détaillés')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    output_path = args.output
    if not output_path:
        input_file = Path(args.input)
        output_path = input_file.stem + "_complete.json"
    
    try:
        result = extract_invoice_complete(
            input_path=args.input,
            output_path=output_path,
            max_pages=args.max_pages
        )
        
        print("\n" + "="*70)
        print("✅ EXTRACTION COMPLÈTE DE LA FACTURE")
        print("="*70)
        print(f"📄 Fichier: {result['file']}")
        print(f"📊 Statut: {result['status']}")
        print(f"📑 Pages traitées: {result['metadata']['page_count']}")
        
        # Afficher les informations de la facture
        info = result.get('invoice_info', {})
        if any(info.values()):
            print("\n📋 INFORMATIONS FACTURE:")
            if info.get('company'):
                print(f"   • Société: {info['company']}")
            if info.get('concession'):
                print(f"   • Concession: {info['concession']}")
            if info.get('document_type'):
                print(f"   • Document: {info['document_type']}")
            if info.get('month_ended'):
                print(f"   • Période: {info['month_ended']}")
            if info.get('docusign_id'):
                docusign_short = info['docusign_id'][:40] if info['docusign_id'] else ""
                print(f"   • DocuSign ID: {docusign_short}...")
        
        # Afficher les totaux
        totals = result.get('totals', {})
        if any(totals.values()):
            print("\n💰 TOTAUX:")
            if totals.get('total_usd'):
                print(f"   • Total USD: {totals['total_usd']}")
            if totals.get('total_omv_share'):
                print(f"   • Part OMV: {totals['total_omv_share']}")
            if totals.get('total_etap_share'):
                print(f"   • Part ETAP: {totals['total_etap_share']}")
        
        # Compter les tableaux
        table_count = 0
        for page in result['pages']:
            table_count += len(page.get('tables', []))
        
        if table_count > 0:
            print(f"\n📊 TABLEAUX DÉTECTÉS: {table_count}")
            for page in result['pages']:
                for table in page.get('tables', []):
                    print(f"   • Tableau {table['table_id']}: {table['num_rows']}x{table['num_cols']}")
        
        print(f"\n💾 Fichier JSON: {output_path}")
        print(f"📝 Taille du texte extrait: {len(result['all_text'])} caractères")
        print("="*70)
        
        # Afficher un extrait des informations clés
        print("\n📌 EXTRAIT DES INFORMATIONS CLÉS:")
        print("-"*50)
        preview_lines = []
        for page in result['pages'][:1]:  # Première page seulement
            for header in page.get('headers', [])[:3]:
                preview_lines.append(f"📌 {header['text']}")
            for kv in page.get('key_values', [])[:2]:
                for cell in kv.get('cells', [])[:5]:
                    preview_lines.append(f"📋 {cell['text']}")
        
        for line in preview_lines[:10]:
            print(line)
        print("-"*50)
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()