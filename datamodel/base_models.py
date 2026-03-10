from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict
from pathlib import Path
from io import BytesIO

class InputFormat(str, Enum):
    """Formats d'entrée supportés"""
    PDF = "pdf"
    IMAGE = "image"

class ConversionStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    FAILURE = "failure"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    SKIPPED = "skipped"

class OutputFormat(str, Enum):
    MARKDOWN = "md"
    JSON = "json"
    TEXT = "text"

# Mapping extensions -> formats
FormatToExtensions: dict[InputFormat, list[str]] = {
    InputFormat.PDF: ["pdf"],
    InputFormat.IMAGE: ["jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp"],
}

# Mapping mime types -> formats
FormatToMimeType: dict[InputFormat, list[str]] = {
    InputFormat.PDF: ["application/pdf"],
    InputFormat.IMAGE: [
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/gif",
        "image/bmp",
        "image/webp",
    ],
}

# Inverse mapping
MimeTypeToFormat: dict[str, list[InputFormat]] = {
    mime: [fmt for fmt in FormatToMimeType if mime in FormatToMimeType[fmt]]
    for value in FormatToMimeType.values()
    for mime in value
}

class ErrorItem(BaseModel):
    component: str
    message: str
    details: Optional[str] = None

class PageDimensions(BaseModel):
    width: float
    height: float
    unit: str = "px"