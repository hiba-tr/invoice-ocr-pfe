from pathlib import Path
import json
from datamodel.backend_options import PdfBackendOptions
from datamodel.document import InputDocument
from backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend

pdf_path = Path("C:\\Factures\\facture3.pdf")
backend_options = PdfBackendOptions()

input_doc = InputDocument(
    path_or_stream=pdf_path,
    format="pdf",
    backend=DoclingParseV4DocumentBackend
)

input_doc._backend.options = backend_options
backend = input_doc._backend

doc_json = {
    "file_name": pdf_path.name,
    "page_count": backend.page_count(),
    "pages": []
}

for i in range(backend.page_count()):
    page_backend = backend.load_page(i)
    page_data = {
        "page_number": i + 1,
        "width": page_backend.get_size().width,
        "height": page_backend.get_size().height,
        "text_lines": []
    }

    for cell in page_backend.get_text_cells():
        bbox = cell.rect.to_bounding_box()  # <-- IMPORTANT
        page_data["text_lines"].append({
            "text": cell.text,
            "bbox": {
                "left": bbox.l,
                "top": bbox.t,
                "right": bbox.r,
                "bottom": bbox.b
            }
        })

    doc_json["pages"].append(page_data)

output_path = Path("C:\\Factures\\facture_structured.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(doc_json, f, ensure_ascii=False, indent=4)

print(f"Document JSON structuré créé : {output_path}")