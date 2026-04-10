# 🧾 DocCore – Extraction et gestion intelligente de factures

DocCore est une application complète d’extraction de données de factures (PDF, images) qui combine :

- 🔍 OCR et analyse de layout
- 🧠 Post-traitement adaptatif pour tout type de facture
- 🗄️ Stockage normalisé dans une base Oracle
- 🤖 Correspondance sémantique (fuzzy + embeddings)
- 🎨 Interface utilisateur moderne avec Streamlit

---

## ✨ Fonctionnalités principales

### 📥 Extraction intelligente
- Dépôt de factures (PDF, PNG, JPG)
- Extraction automatique :
  - Fournisseur
  - Date
  - Devise
  - Concession
  - Lignes d’articles

### 🧠 Post-traitement avancé
- Détection universelle des tableaux
- Conservation des noms de colonnes originaux
- Gestion robuste des montants (EU / US)
- Filtrage intelligent des lignes inutiles
- Fallback sur texte libre si aucun tableau détecté

### ✏️ Édition interactive
- Modification en temps réel avec `st.data_editor`
- Ajout / suppression de lignes
- Validation avant enregistrement

### 🔎 Correspondance sémantique
- Détection des doublons intelligents
- Matching via :
  - Similarité floue (fuzzy)
  - Embeddings (FAISS)
- Score de confiance affiché
- Message clair si aucune correspondance

### 📊 Historique & visualisation
- Liste complète des factures
- Métadonnées affichées
- Tableau pivoté des items

### 🗃️ Explorateur de base de données
- Onglets :
  - Items
  - Colonnes
  - Factures
  - Valeurs
- Suppression multiple via sélection

---

## 🏗️ Architecture du projet
doccore/
│
├── api/                          # Backend FastAPI
│   ├── main.py                  # points d’entrée API (endpoints)
│   ├── database.py             # Connexion et configuration Oracle
│   ├── models_sql.py           # Modèles SQLAlchemy (ORM)
│   ├── schemas.py              # Schémas Pydantic (validation)
│   ├── crud.py                 # Opérations CRUD (Create, Read, Update, Delete)
│   ├── semantic.py             # Moteur de matching sémantique (FAISS + fuzzy)
│   └── resume.py               # Génération de résumé de facture
│
├── streamlit_app.py            # Interface utilisateur (Streamlit)
├── postprocess.py              # Post-traitement des données extraites
├── main.py                     # Pipeline d’extraction OCR (Docling)
├── document_converter.py       # Orchestre la conversion des documents (PDF/images) via le pipeline adapté.
│
├── commande.txt                # Commande pour lancer le projet
├── requirements.txt            # Dépendances du projet
├── requirements_api.txt        # Dépendances backend/API
├── table.txt                   # Script de création des tables Oracle

---

## 🚀 Installation

### 1. Prérequis

- Python 3.10 ou supérieur
- Oracle Database (Express Edition recommandée)
- Git

---

### 2. Cloner le projet


git clone https://github.com/hiba-tr/invoice-ocr-pfe.git
cd invoice-ocr-pfe

### 3. Créer un environnement virtuel
python -m venv venv

Activer l’environnement

Windows :
venv\Scripts\activate

Linux / Mac :
source venv/bin/activate

### 4. Installer les dépendances
pip install -r requirements.txt
pip install -r requirements_api.txt

### 5. Configuration Oracle:
Connexion SQL*Plus
sqlplus sys as sysdba
ALTER SESSION SET CONTAINER = xepdb1;

CREATE USER doccore IDENTIFIED BY doccore;

GRANT CONNECT, RESOURCE, CREATE TABLE, CREATE SEQUENCE TO doccore;

ALTER USER doccore QUOTA UNLIMITED ON USERS;

CONNECT doccore/doccore@//localhost:1521/xepdb1;

### 6. Création des tables : 
copier le contenu de table.txt

### 7. Lancement de l'application :

Backend (FastAPI)

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Frontend (Streamlit)

streamlit run streamlit_app.py

Accès
Interface : http://localhost:8501
API : http://localhost:8000/docs


### Moteur sémantique :
Fuzzy matching
Embeddings vectoriels (FAISS)
Index reconstruit automatiquement
Optimisé pour performance et précision

### Version actuelle : 
v2.0 – Mise à jour majeure
Nouveau moteur de post-traitement
Interface Streamlit modernisée
API enrichie
Robustesse améliorée
Meilleure performance globale

### Auteurs :
Sirine Ouerghemmi
Hiba Trabelsi

### Licence :
Projet académique – PFE (Projet de Fin d’Études)
