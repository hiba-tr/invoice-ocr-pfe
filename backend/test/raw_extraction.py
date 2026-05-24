import json
from backend.extraction.pipeline import extract_document

pdf_path = "C:\\Factures\\facture pro.png"

result = extract_document(pdf_path)

with open("backend/test/raw_output.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("Extraction brute sauvegardée.")