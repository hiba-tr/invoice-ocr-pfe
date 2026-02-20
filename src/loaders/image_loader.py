from PIL import Image
from pathlib import Path
from typing import List, Union
from .base import BaseLoader

class ImageLoader(BaseLoader):
    def load(self, file_path: Path) -> List[Union[str, 'PIL.Image.Image']]:
        img = Image.open(file_path).convert('RGB')
        return [img]

    def get_type(self) -> str:
        return "image"

    def supports(self, file_ext: str, mime_type: str = None) -> bool:
        ext = file_ext.lower()
        return ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif']