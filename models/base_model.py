from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Protocol, Type

from datamodel.base_models import Page
from datamodel.document import ConversionResult
from datamodel.pipeline_options import BaseOptions


class BaseModelWithOptions(Protocol):
    @classmethod
    def get_options_type(cls) -> Type[BaseOptions]: ...
    def __init__(self, *, options: BaseOptions, **kwargs): ...


class BasePageModel(ABC):
    @abstractmethod
    def __call__(
        self, conv_res: ConversionResult, page_batch: Iterable[Page]
    ) -> Iterable[Page]:
        pass