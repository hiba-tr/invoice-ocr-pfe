from sqlalchemy import create_engine

# Essayez les différentes variantes
urls = [
    "oracle+oracledb://docling:docling_password@localhost:1521/?service_name=xepdb1",
    "oracle+oracledb://docling:docling_password@localhost:1521/?service_name=XEPDB1",
    "oracle+oracledb://docling:docling_password@localhost:1521/?sid=XE",
    "oracle+oracledb://docling:docling_password@localhost:1521/xe"
]

for url in urls:
    try:
        engine = create_engine(url)
        conn = engine.connect()
        print(f"Réussi : {url}")
        conn.close()
        break
    except Exception as e:
        print(f"Échec : {url} -> {e}")