import pandas as pd
from pathlib import Path
from typing import List, Union
from .base import BaseLoader

class ExcelLoader(BaseLoader):
    def load(self, file_path: Path) -> List[Union[str, 'PIL.Image.Image']]:
        xl = pd.ExcelFile(file_path)
        pages = []
        for sheet in xl.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet)
            pages.append(f"--- Sheet: {sheet} ---\n" + df.to_string())
        return pages

    def get_type(self) -> str:
        return "excel"

    def supports(self, file_ext: str, mime_type: str = None) -> bool:
        return file_ext.lower() in ['.xlsx', '.xls', '.xlsm']