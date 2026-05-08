from backend.extraction.engine.models.base_layout_model import BaseLayoutModel
from backend.extraction.engine.models.factories.base_factory import BaseFactory


class LayoutFactory(BaseFactory[BaseLayoutModel]):
    def __init__(self, *args, **kwargs):
        super().__init__("layout_engines", *args, **kwargs)
