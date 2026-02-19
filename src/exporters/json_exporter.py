import json
from ..core.document import Document

class JSONExporter:
    @staticmethod
    def export(document: Document, file_path: str):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(document.dict(), f, indent=2, default=str)