import logging
from functools import lru_cache

from models.factories.layout_factory import LayoutFactory
from models.factories.ocr_factory import OcrFactory

from models.factories.table_factory import TableStructureFactory

logger = logging.getLogger(__name__)


@lru_cache
def get_ocr_factory(allow_external_plugins: bool = False) -> OcrFactory:
    factory = OcrFactory()
    factory.load_from_plugins(allow_external_plugins=allow_external_plugins)
    logger.info("Registered ocr engines: %r", factory.registered_kind)
    return factory



@lru_cache
def get_layout_factory(allow_external_plugins: bool = False) -> LayoutFactory:
    factory = LayoutFactory()
    factory.load_from_plugins(allow_external_plugins=allow_external_plugins)
    logger.info("Registered layout engines: %r", factory.registered_kind)
    return factory


@lru_cache
def get_table_structure_factory(
    allow_external_plugins: bool = False,
) -> TableStructureFactory:
    factory = TableStructureFactory()
    factory.load_from_plugins(allow_external_plugins=allow_external_plugins)
    logger.info("Registered table structure engines: %r", factory.registered_kind)
    return factory
