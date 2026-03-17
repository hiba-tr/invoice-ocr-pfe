from models.base_layout_model import BaseLayoutModel
from models.factories.base_factory import BaseFactory


class LayoutFactory(BaseFactory[BaseLayoutModel]):
    def __init__(self, *args, **kwargs):
        super().__init__("layout_engines", *args, **kwargs)
