from typing import Optional, Literal, Union
from pydantic import BaseModel, Field, SecretStr

class BaseBackendOptions(BaseModel):
    """Options communes à tous les backends"""
    
    max_file_size: int = 100 * 1024 * 1024  # 100 MB
    password: Optional[SecretStr] = None  # Pour PDF protégés

class PdfBackendOptions(BaseBackendOptions):
    """Options spécifiques aux PDF"""
    
    kind: Literal["pdf"] = Field("pdf", exclude=True)
    
    # Extraction
    extract_text: bool = True
    extract_tables: bool = True
    extract_images: bool = False
    
    # Rendu
    dpi: int = 150
    enable_ocr: bool = False
    ocr_language: str = "fra+eng"
    
    # Pages
    start_page: int = 1
    end_page: Optional[int] = None
    
    # Moteur
    engine: Literal["pypdfium2", "docling_parse"] = "pypdfium2"

class ImageBackendOptions(BaseBackendOptions):
    """Options spécifiques aux images"""
    
    kind: Literal["image"] = Field("image", exclude=True)
    
    # OCR
    ocr_language: str = "fra+eng"
    ocr_engine: Literal["tesseract", "easyocr"] = "tesseract"
    min_confidence: float = 0.5
    
    # Prétraitement
    preprocess: bool = True
    deskew: bool = False
    denoise: bool = False
    
    # Layout
    detect_layout: bool = True

# Union des options pour discrimination
BackendOptions = Union[
    PdfBackendOptions,
    ImageBackendOptions,
]