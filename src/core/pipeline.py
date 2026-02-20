import time
from pathlib import Path
from typing import Optional, Union
from ..loaders.factory import LoaderFactory
from ..ocr.tesseract_engine import TesseractEngine
from ..layout.detector import LayoutDetector
from ..table.extractor import TableExtractor
from ..nlp.entity_extractor import EntityExtractor
from ..vlm.base import VLMProcessor
from ..utils.logger import get_logger
from .document import Document, Page, BoundingBox, TextBlock, BlockType, Table
from .exceptions import ProcessingError

logger = get_logger(__name__)

class DocumentProcessor:
    def __init__(
        self,
        ocr_engine: Optional[TesseractEngine] = None,
        layout_detector: Optional[LayoutDetector] = None,
        table_extractor: Optional[TableExtractor] = None,
        entity_extractor: Optional[EntityExtractor] = None,
        vlm_processor: Optional[VLMProcessor] = None,
    ):
        self.loader_factory = LoaderFactory()
        self.ocr_engine = ocr_engine
        self.layout_detector = layout_detector
        self.table_extractor = table_extractor
        self.entity_extractor = entity_extractor
        self.vlm_processor = vlm_processor

    def process(self, source: Union[str, Path], **kwargs) -> Document:
        start_time = time.time()
        source_path = Path(source)

        if not source_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {source_path}")

        loader = self.loader_factory.get_loader(source_path)
        if not loader:
            raise ValueError(f"Aucun loader trouvé pour {source_path}")

        logger.info(f"Chargement avec {loader.__class__.__name__}")
        raw_pages = loader.load(source_path)

        doc = Document(
            source=str(source_path),
            filename=source_path.name,
            file_type=loader.get_type(),
        )

        for page_idx, page_data in enumerate(raw_pages):
            page = self._process_page(page_data, page_idx, **kwargs)
            doc.pages.append(page)

        if self.entity_extractor:
            doc.metadata["entities"] = self.entity_extractor.extract(doc.get_all_text())

        doc.processing_time = time.time() - start_time
        doc.layout_model = self.layout_detector.model_name if self.layout_detector else None
        doc.table_model = self.table_extractor.model_name if self.table_extractor else None
        doc.vlm_used = self.vlm_processor.model_name if self.vlm_processor else None

        logger.info(f"Traitement terminé en {doc.processing_time:.2f}s")
        return doc

    def _process_page(self, page_data, page_num: int, **kwargs):
        if hasattr(page_data, "mode"):  # Image
            image = page_data
            width, height = image.size
            text = self.ocr_engine.extract_text_from_image(image) if self.ocr_engine else ""
            ocr_applied = bool(self.ocr_engine)
        else:  # Texte
            text = page_data
            width, height = 0, 0
            image = None
            ocr_applied = False

        page = Page(page_num=page_num, width=width, height=height, text=text)

        if image and self.layout_detector:
            layout_blocks = self.layout_detector.detect(image)
            for block in layout_blocks:
                bbox = BoundingBox(
                    x1=block['bbox'][0], y1=block['bbox'][1],
                    x2=block['bbox'][2], y2=block['bbox'][3],
                    page=page_num
                )
                if self.ocr_engine:
                    cropped = image.crop((bbox.x1, bbox.y1, bbox.x2, bbox.y2))
                    block_text = self.ocr_engine.extract_text_from_image(cropped)
                else:
                    block_text = ""
                page.blocks.append(TextBlock(
                    bbox=bbox,
                    text=block_text,
                    block_type=BlockType(block['type']),
                    confidence=block.get('confidence', 1.0)
                ))

        if image and self.table_extractor:
            tables = self.table_extractor.extract(image)
            for tbl in tables:
                table_obj = Table(
                    bbox=BoundingBox(**tbl['bbox'], page=page_num),
                    text="",
                    block_type=BlockType.TABLE,
                    data=tbl.get('data', []),
                    cells=[TableCell(**cell) for cell in tbl.get('cells', [])]
                )
                page.tables.append(table_obj)

        return page