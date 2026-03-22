from models.base_table_model import BaseTableStructureModel
from models.factories.base_factory import BaseFactory


class TableStructureFactory(BaseFactory[BaseTableStructureModel]):
    def __init__(self, *args, **kwargs):
        super().__init__("table_structure_engines", *args, **kwargs)
