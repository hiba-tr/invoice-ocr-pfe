from document_converter import DocumentConverter
from datamodel.base_models import InputFormat

converter = DocumentConverter(
    allowed_formats=[InputFormat.PDF]
)

result = converter.convert("C:\\Factures\\facture.pdf")

print("Status:", result.status)
print("Pages:", len(result.pages))

page = result.pages[0]

print("\n=== PAGE OBJECT ===")
print(page)

print("\n=== TEXT (OCR) ===")
print(page.parsed_page.textline_cells[:5])

print("\n=== TABLES ===")
print(page.predictions.tablestructure)

print("\n=== ASSEMBLED ===")
print(page.assembled)