from backend.extraction.invoice_extraction_bridge import extract_invoice
import json

result = extract_invoice("C:\\Factures\\facture.pdf", max_pages=50)
with open("extraction_debug.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False, default=str)

# Afficher les headers et sémantiques du premier tableau
tables = result["tables"]
if tables:
    t = tables[0]
    print("Headers bruts fusionnés :", t["column_headers_raw"])
    print("Sémantiques attribuées :", t["column_semantics"])
    print("Nombre de colonnes :", t["num_cols"])
    # Vérifier la matrice (5 premières lignes)
    print("Matrice (5 premières lignes) :")
    for row in t["matrix"][:5]:
        print(row)
else:
    print("Aucune table trouvée !")