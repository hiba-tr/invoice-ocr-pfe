from sentence_transformers import SentenceTransformer
import os

# Le chemin vers ton dossier
dossier_cible = r"C:\doccore_new\backend\models"

# Cela télécharge les fichiers du modèle DANS ton dossier
model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=dossier_cible)
print("Modèle téléchargé avec succès !")