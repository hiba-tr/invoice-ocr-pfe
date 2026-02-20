import pypdf
from pdf2image import convert_from_path
from pathlib import Path
from typing import List, Union
from .base import BaseLoader
from ..utils.logger import get_logger

logger = get_logger(__name__)

class PDFLoader(BaseLoader):
    def __init__(self, dpi=300, use_ocr_fallback=True):
        self.dpi = dpi
        self.use_ocr_fallback = use_ocr_fallback

    def load(self, file_path: Path) -> List[Union[str, 'PIL.Image.Image']]:
        pages = []
        with open(file_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text = page.extract_text()
                if text and text.strip() and not self.use_ocr_fallback:
                    pages.append(text)
                else:
                    images = convert_from_path(file_path, first_page=page_num+1, last_page=page_num+1, dpi=self.dpi)
                    pages.extend(images)
        return pages

    def get_type(self) -> str:
        return "pdf"

    def supports(self, file_ext: str, mime_type: str = None) -> bool:
        return file_ext.lower() == '.pdf' or (mime_type and 'pdf' in mime_type)