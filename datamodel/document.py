import hashlib
import logging
from datetime import datetime
from enum import Enum
from io import BytesIO
from pathlib import Path, PurePath
from typing import Optional, Union, List, Dict, Any

from pydantic import BaseModel, Field

# Importer vos propres modèles
from datamodel.base_models import (
    InputFormat, 
    ConversionStatus, 
    ErrorItem,
    PageDimensions
)

_log = logging.getLogger(__name__)

class DocumentSource(str, Enum):
    PATH = "path"
    STREAM = "stream"

class InputDocument(BaseModel):
    """Document d'entrée pour l'extraction"""
    
    source: Union[Path, BytesIO]
    source_type: DocumentSource
    filename: str
    format: InputFormat
    document_hash: str = Field(default="")
    file_size: int = 0
    page_count: int = 0
    valid: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def __init__(self, **data):
        super().__init__(**data)
        
        # Calculer la taille et le hash
        if self.source_type == DocumentSource.PATH:
            path = self.source
            self.file_size = path.stat().st_size
            self.document_hash = self._compute_file_hash(path)
        else:  # STREAM
            stream = self.source
            self.file_size = stream.getbuffer().nbytes
            self.document_hash = self._compute_stream_hash(stream)
    
    def _compute_file_hash(self, path: Path) -> str:
        """Calcule le hash SHA-256 d'un fichier"""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _compute_stream_hash(self, stream: BytesIO) -> str:
        """Calcule le hash SHA-256 d'un stream"""
        sha256 = hashlib.sha256()
        stream.seek(0)
        sha256.update(stream.read())
        stream.seek(0)
        return sha256.hexdigest()
    
    @property
    def name(self) -> str:
        return self.filename
    
    def get_stream(self) -> BytesIO:
        """Retourne un stream du document"""
        if self.source_type == DocumentSource.PATH:
            with open(self.source, "rb") as f:
                return BytesIO(f.read())
        else:
            self.source.seek(0)
            return BytesIO(self.source.read())

class Page(BaseModel):
    """Représentation d'une page dans le document"""
    
    page_no: int
    width: Optional[float] = None
    height: Optional[float] = None
    text: Optional[str] = None
    image_path: Optional[Path] = None
    
class ConversionResult(BaseModel):
    """Résultat complet de la conversion"""
    
    input_document: InputDocument
    status: ConversionStatus = ConversionStatus.PENDING
    pages: List[Page] = Field(default_factory=list)
    markdown: Optional[str] = None
    json_output: Optional[Dict[str, Any]] = None
    text_output: Optional[str] = None
    errors: List[ErrorItem] = Field(default_factory=list)
    processing_time: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    
    def add_error(self, component: str, message: str, details: Optional[str] = None):
        """Ajoute une erreur au résultat"""
        self.errors.append(ErrorItem(
            component=component,
            message=message,
            details=details
        ))
        self.status = ConversionStatus.FAILURE
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour JSON"""
        return {
            "filename": self.input_document.filename,
            "status": self.status.value,
            "page_count": len(self.pages),
            "processing_time": self.processing_time,
            "created_at": self.created_at.isoformat(),
            "errors": [e.dict() for e in self.errors],
            "output": {
                "markdown": self.markdown,
                "text": self.text_output
            }
        }