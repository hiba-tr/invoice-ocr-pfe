from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Type

from datamodel.base_models import LayoutPrediction, Page
from datamodel.document import ConversionResult
from datamodel.pipeline_options import BaseLayoutOptions
from models.base_model import BaseModelWithOptions, BasePageModel


class BaseLayoutModel(BasePageModel, BaseModelWithOptions, ABC):
    """Shared interface for layout models."""

    @classmethod
    @abstractmethod
    def get_options_type(cls) -> Type[BaseLayoutOptions]:
        """Return the options type supported by this layout model."""

    @abstractmethod
    def predict_layout(
        self,
        conv_res: ConversionResult,
        pages: Sequence[Page],
    ) -> Sequence[LayoutPrediction]:
        """Produce layout predictions for the provided pages."""

    def __call__(
        self,
        conv_res: ConversionResult,
        page_batch: Iterable[Page],
    ) -> Iterable[Page]:
        pages = list(page_batch)
        predictions = self.predict_layout(conv_res, pages)

        for page, prediction in zip(pages, predictions):
            page.predictions.layout = prediction
            yield page
