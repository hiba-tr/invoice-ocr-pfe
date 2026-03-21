# main.py
import logging
from pathlib import Path
import json

from datamodel.document import ConversionResult
from document_converter import DocumentConverter
from datamodel.base_models import InputFormat

# Configurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 1️⃣ Chemin de la facture à tester (PDF ou image)
    facture_path = Path("C:\\Factures\\facture_png.png")  # ou facture_test.jpg

    if not facture_path.exists():
        logger.error(f"Fichier non trouvé : {facture_path}")
        return

    # 2️⃣ Créer un DocumentConverter
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
    )

    # 3️⃣ Convertir le document
    try:
        result: ConversionResult = converter.convert(facture_path)
    except Exception as e:
        logger.exception("Erreur lors de la conversion du document")
        return

    # 4️⃣ Construire un dictionnaire JSON de sortie
    output_json = {
        "input_file": str(facture_path),
        "status": result.status.value,
        "errors": [e.error_message for e in result.errors],
        "page_count": getattr(result.input, "page_count", None),
        "filesize": getattr(result.input, "filesize", None),
        "document": result.assembled.model_dump() if hasattr(result, "assembled") else {},
    }

    # 5️⃣ Sauvegarder le JSON dans un fichier externe
    output_file = facture_path.with_suffix(".json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)

    logger.info(f"Conversion terminée. Résultat sauvegardé dans {output_file}")
    print(json.dumps(output_json, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()