import pandas as pd
from pathlib import Path
from typing import List, Union
from .base import BaseLoader

class CSVLoader(BaseLoader):
    def load(self, file_path: Path) -> List[Union[str, 'PIL.Image.Image']]:
        df = pd.read_csv(file_path)
        return [df.to_string()]

    def get_type(self) -> str:
        return "csv"

    def supports(self, file_ext: str, mime_type: str = None) -> bool:
        return file_ext.lower() == '.csv'