from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class BlockType(str, Enum):
    TEXT = "text"
    TITLE = "title"
    LIST = "list"
    TABLE = "table"
    FIGURE = "figure"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    page: Optional[int] = None

class TextBlock(BaseModel):
    bbox: BoundingBox
    text: str
    block_type: BlockType
    confidence: float = 1.0
    metadata: Dict[str, Any] = {}

class TableCell(BaseModel):
    row: int
    col: int
    text: str
    bbox: Optional[BoundingBox] = None
    is_header: bool = False

class Table(TextBlock):
    cells: List[TableCell] = []
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    data: List[List[str]] = []

class Page(BaseModel):
    page_num: int
    width: float
    height: float
    blocks: List[TextBlock] = []
    tables: List[Table] = []
    images: List[Any] = []
    text: str = ""

class Document(BaseModel):
    source: str
    filename: str
    file_type: str
    pages: List[Page] = []
    metadata: Dict[str, Any] = {}
    extraction_date: datetime = datetime.now()
    processing_time: float = 0.0
    ocr_applied: bool = False
    layout_model: Optional[str] = None
    table_model: Optional[str] = None
    vlm_used: Optional[str] = None

    def get_all_text(self) -> str:
        return "\n".join([p.text for p in self.pages])

    def get_tables(self) -> List[Table]:
        tables = []
        for page in self.pages:
            tables.extend(page.tables)
        return tables