import logging

from models.base_ocr_model import BaseOcrModel
from models.factories.base_factory import BaseFactory

logger = logging.getLogger(__name__)


class OcrFactory(BaseFactory[BaseOcrModel]):
    def __init__(self, *args, **kwargs):
        super().__init__("ocr_engines", *args, **kwargs)
