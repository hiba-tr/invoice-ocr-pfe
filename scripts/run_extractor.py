import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import DocumentProcessor
from src.ocr.tesseract_engine import TesseractEngine
from src.layout import DummyLayoutDetector   # <-- Nouvel import
from src.table.extractor import TableExtractor
from src.nlp.entity_extractor import EntityExtractor
from config import settings

def main():
    parser = argparse.ArgumentParser(description="Extract document content")
    parser.add_argument("file", help="Path to the input file")
    parser.add_argument("--output", help="Output JSON file (optional)")
    args = parser.parse_args()

    ocr = TesseractEngine()
    
    # Utilisation du détecteur factice
    layout = DummyLayoutDetector()
    
    table = TableExtractor()
    nlp = EntityExtractor()

    processor = DocumentProcessor(
        ocr_engine=ocr,
        layout_detector=layout,   # <-- On passe le détecteur factice
        table_extractor=table,
        entity_extractor=nlp
    )

    doc = processor.process(args.file)

    output_json = doc.model_dump_json(indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
    else:
        print(output_json)

if __name__ == "__main__":
    main()