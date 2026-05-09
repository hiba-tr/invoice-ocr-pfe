from backend.extraction.engine.models.factories.layout_factory import LayoutFactory
from backend.extraction.engine.models.factories.ocr_factory import OcrFactory
from backend.extraction.engine.models.factories.table_factory import TableStructureFactory

_LAYOUT_FACTORY = None
_OCR_FACTORY = None
_TABLE_FACTORY = None


def get_layout_factory(allow_external_plugins: bool = False):
    global _LAYOUT_FACTORY
    if _LAYOUT_FACTORY is None:
        _LAYOUT_FACTORY = LayoutFactory()
        _LAYOUT_FACTORY.load_from_plugins(allow_external_plugins=allow_external_plugins)
    return _LAYOUT_FACTORY


def get_ocr_factory(allow_external_plugins: bool = False):
    global _OCR_FACTORY
    if _OCR_FACTORY is None:
        _OCR_FACTORY = OcrFactory()
        _OCR_FACTORY.load_from_plugins(allow_external_plugins=allow_external_plugins)
    return _OCR_FACTORY


def get_table_structure_factory(allow_external_plugins: bool = False):
    global _TABLE_FACTORY
    if _TABLE_FACTORY is None:
        _TABLE_FACTORY = TableStructureFactory()
        _TABLE_FACTORY.load_from_plugins(allow_external_plugins=allow_external_plugins)
    return _TABLE_FACTORY