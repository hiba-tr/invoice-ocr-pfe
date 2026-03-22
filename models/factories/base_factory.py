import enum
import logging
from abc import ABCMeta
from typing import Generic, Optional, Type, TypeVar

from pluggy import PluginManager
from pydantic import BaseModel

from datamodel.pipeline_options import BaseOptions
from models.base_model import BaseModelWithOptions

A = TypeVar("A", bound=BaseModelWithOptions)


logger = logging.getLogger(__name__)


class FactoryMeta(BaseModel):
    kind: str
    plugin_name: str
    module: str


class BaseFactory(Generic[A], metaclass=ABCMeta):
    default_plugin_name = "docling"

    def __init__(self, plugin_attr_name: str, plugin_name=default_plugin_name):
        self.plugin_name = plugin_name
        self.plugin_attr_name = plugin_attr_name

        self._classes: dict[Type[BaseOptions], Type[A]] = {}
        self._meta: dict[Type[BaseOptions], FactoryMeta] = {}

    @property
    def registered_kind(self) -> list[str]:
        return [opt.kind for opt in self._classes.keys()]

    def get_enum(self) -> enum.Enum:
        return enum.Enum(
            self.plugin_attr_name + "_enum",
            names={kind: kind for kind in self.registered_kind},
            type=str,
            module=__name__,
        )

    @property
    def classes(self):
        return self._classes

    @property
    def registered_meta(self):
        return self._meta

    def create_instance(self, options: BaseOptions, **kwargs) -> A:
        try:
            _cls = self._classes[type(options)]
            return _cls(options=options, **kwargs)
        except KeyError:
            raise RuntimeError(self._err_msg_on_class_not_found(options.kind))

    def create_options(self, kind: str, *args, **kwargs) -> BaseOptions:
        for opt_cls, _ in self._classes.items():
            if opt_cls.kind == kind:
                return opt_cls(*args, **kwargs)
        raise RuntimeError(self._err_msg_on_class_not_found(kind))

    def _err_msg_on_class_not_found(self, kind: str):
        msg = []

        for opt, cls in self._classes.items():
            msg.append(f"\t{opt.kind!r} => {cls!r}")

        msg_str = "\n".join(msg)

        return f"No class found with the name {kind!r}, known classes are:\n{msg_str}"

    def register(self, cls: Type[A], plugin_name: str, plugin_module_name: str):
        opt_type = cls.get_options_type()

        if opt_type in self._classes:
            raise ValueError(
                f"{opt_type.kind!r} already registered to class {self._classes[opt_type]!r}"
            )

        self._classes[opt_type] = cls
        self._meta[opt_type] = FactoryMeta(
            kind=opt_type.kind, plugin_name=plugin_name, module=plugin_module_name
        )

    def load_local_engines(self):
        """Charge directement les moteurs locaux sans passer par les plugins"""
        if self.plugin_attr_name == "ocr_engines":
            try:
                from models.stages.ocr.auto_ocr_model import OcrAutoModel
                from models.stages.ocr.easyocr_model import EasyOcrModel
                from models.stages.ocr.ocr_mac_model import OcrMacModel
                from models.stages.ocr.rapid_ocr_model import RapidOcrModel
                
                engines = [OcrAutoModel, EasyOcrModel, OcrMacModel, RapidOcrModel]
                
                for engine in engines:
                    try:
                        self.register(engine, "local", "models.stages.ocr")
                        logger.info(f"Registered local OCR engine: {engine.__name__}")
                    except ValueError:
                        logger.debug(f"Engine {engine.__name__} already registered")
            except ImportError as e:
                logger.warning(f"Could not import OCR engines: {e}")
                
        elif self.plugin_attr_name == "layout_engines":
            try:
                from models.stages.layout.layout_model import LayoutModel
                from models.stages.layout.layout_object_detection_model import LayoutObjectDetectionModel
                
                engines = [LayoutObjectDetectionModel, LayoutModel]
                
                try:
                    from experimental.models.table_crops_layout_model import TableCropsLayoutModel
                    engines.append(TableCropsLayoutModel)
                except ImportError:
                    pass
                    
                for engine in engines:
                    try:
                        self.register(engine, "local", "models.stages.layout")
                        logger.info(f"Registered local layout engine: {engine.__name__}")
                    except ValueError:
                        logger.debug(f"Engine {engine.__name__} already registered")
            except ImportError as e:
                logger.warning(f"Could not import layout engines: {e}")
                
        elif self.plugin_attr_name == "table_structure_engines":
            try:
                from models.stages.table_structure.table_structure_model import TableStructureModel
                
                self.register(TableStructureModel, "local", "models.stages.table_structure")
                logger.info(f"Registered local table structure engine: {TableStructureModel.__name__}")
            except ImportError as e:
                logger.warning(f"Could not import table structure engines: {e}")
            except ValueError:
                logger.debug("Table structure engine already registered")

    def load_from_plugins(
        self, plugin_name: Optional[str] = None, allow_external_plugins: bool = False
    ):
        # TOUJOURS charger les moteurs locaux en premier
        logger.info(f"Loading local {self.plugin_attr_name} engines")
        self.load_local_engines()
        
        # Optionnel : aussi charger les plugins externes si autorisé
        if allow_external_plugins:
            plugin_name = plugin_name or self.plugin_name
            plugin_manager = PluginManager(plugin_name)
            plugin_manager.load_setuptools_entrypoints(plugin_name)

            for plugin_name, plugin_module in plugin_manager.list_name_plugin():
                plugin_module_name = str(plugin_module.__name__)

                if not plugin_module_name.startswith(("docling.", "models.")):
                    logger.warning(
                        f"The plugin {plugin_name} will not be loaded because Docling is being executed with allow_external_plugins=false."
                    )
                    continue

                attr = getattr(plugin_module, self.plugin_attr_name, None)

                if callable(attr):
                    logger.info("Loading plugin %r", plugin_name)
                    config = attr()
                    self.process_plugin(config, plugin_name, plugin_module_name)

    def process_plugin(self, config, plugin_name: str, plugin_module_name: str):
        for item in config[self.plugin_attr_name]:
            try:
                self.register(item, plugin_name, plugin_module_name)
            except ValueError:
                logger.warning("%r already registered", item)