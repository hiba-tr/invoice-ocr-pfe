# Pipeline d'Extraction Documentaire Avancé

Ce projet fournit un pipeline modulaire pour extraire le contenu de divers types de documents (PDF, images, Excel, CSV) en utilisant des techniques d'OCR, d'analyse de layout, d'extraction de tableaux, de NLP et de VLM.

## Installation
1. Installer les dépendances : `pip install -r requirements.txt`
2. Installer Tesseract OCR (voir documentation)
3. Télécharger les modèles nécessaires (certains se téléchargent automatiquement)
4. Configurer `.env`

## Utilisation
```bash
python scripts/run_extractor.py facture.png --output facture_extrait.json
