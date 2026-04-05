import oracledb

try:
    conn = oracledb.connect(
        user="docling",
        password="docling_password",
        dsn="localhost:1521/xepdb1"
    )
    print("Connexion réussie à Oracle !")
    conn.close()
except Exception as e:
    print("Erreur :", e)