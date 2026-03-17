# backend/image_backend.py

from pathlib import Path
from typing import List, Optional, Union
from PIL import Image

from backend.abstract_backend import AbstractDocumentBackend
from backend.pdf_backend import PdfDocumentBackend, PdfPageBackend
from datamodel.base_models import InputFormat, Size

class _ImagePageBackend(PdfPageBackend):
    def __init__(self, image: Image.Image):
        self._image: Optional[Image.Image] = image
        self.valid: bool = self._image is not None

    def is_valid(self) -> bool:
        return self.valid

    def get_size(self) -> Size:
        assert self._image is not None
        return Size(width=self._image.width, height=self._image.height)

    def get_page_image(self, scale: float = 1) -> Image.Image:
        assert self._image is not None
        img = self._image
        if scale != 1:
            new_w = max(1, round(img.width * scale))
            new_h = max(1, round(img.height * scale))
            img = img.resize((new_w, new_h))
        return img

    def unload(self):
        self._image = None

class ImageDocumentBackend(PdfDocumentBackend):
    """Backend pour traiter directement les images comme documents."""

    def __init__(self, in_doc, path_or_stream: Union[Path, str], options=None):
        AbstractDocumentBackend.__init__(self, in_doc, path_or_stream, options)
        img = Image.open(path_or_stream)
        self._frames: List[Image.Image] = [img.convert("RGB")]

    def is_valid(self) -> bool:
        return len(self._frames) > 0

    def page_count(self) -> int:
        return len(self._frames)

    def load_page(self, page_no: int) -> _ImagePageBackend:
        return _ImagePageBackend(self._frames[page_no])

    @classmethod
    def supported_formats(cls) -> set[InputFormat]:
        return {InputFormat.IMAGE}

    @classmethod
    def supports_pagination(cls) -> bool:
        return True

    def unload(self):
        for f in self._frames:
            f.close()
        self._frames = []