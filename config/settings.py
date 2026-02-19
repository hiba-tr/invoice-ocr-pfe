import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# Dossier temporaire
TEMP_DIR = BASE_DIR / "data" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Modèles pré-entraînés
MODELS_DIR = BASE_DIR / "data" / "models"
MODELS_DIR.mkdir(exist_ok=True)

# OCR
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "fra+eng").split("+")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")

# Layout model
LAYOUT_MODEL = os.getenv("LAYOUT_MODEL", "yolox")  # ou "layoutparser"
LAYOUT_CONFIG = {
    "yolox": {"model_path": MODELS_DIR / "yolox" / "layout.pt"},
    "layoutparser": {"config_path": "lp://PubLayNet/faster_rcnn_r50_fpn_dcn"}
}

# Table model
TABLE_MODEL = os.getenv("TABLE_MODEL", "table-transformer")
TABLE_CONFIG = {
    "table-transformer": {"model_path": "microsoft/table-transformer-detection"}
}

# VLM (optionnel)
VLM_MODEL = os.getenv("VLM_MODEL", None)  # ex: "granite-docling"