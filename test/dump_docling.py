import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
# Ajuste l'import si ta classe DocumentConverter n'est pas dans docling directement
# mais dans ton module personnalisé. Ici, on suppose que ton convertisseur est
# celui que tu as montré, donc :
from backend.extraction.engine.document_converter import DocumentConverter
from backend.extraction.engine.datamodel.base_models import InputFormat

def dump_conversion_result(pdf_path: str, output_path: str = None):
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"Fichier introuvable : {pdf_file}")
        sys.exit(1)

    conv = DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.IMAGE])
    print(f"Conversion de {pdf_file.name} en cours...")
    result = conv.convert(source=pdf_file, raises_on_error=False)

    # Convertir en dict (si la méthode s'appelle .dict() ou .model_dump())
    try:
        data = result.model_dump()  # pydantic v2
    except AttributeError:
        data = result.dict()        # pydantic v1

    if output_path is None:
        output_path = pdf_file.stem + "_docling_dump.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Dump sauvegardé dans : {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python dump_docling.py chemin/vers/facture.pdf [sortie.json]")
        sys.exit(1)
    dump_conversion_result(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)