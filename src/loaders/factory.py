from pathlib import Path
from typing import List, Optional
from .base import BaseLoader
from .pdf_loader import PDFLoader
from .image_loader import ImageLoader
from .excel_loader import ExcelLoader
from .csv_loader import CSVLoader
from ..utils.file_detector import detect_file_type

class LoaderFactory:
    def __init__(self):
        self._loaders: List[BaseLoader] = [
            PDFLoader(),
            ImageLoader(),
            ExcelLoader(),
            CSVLoader()
        ]

    def get_loader(self, file_path: Path) -> Optional[BaseLoader]:
        ext, mime = detect_file_type(file_path)
        for loader in self._loaders:
            if loader.supports(ext, mime):
                return loader
        return None