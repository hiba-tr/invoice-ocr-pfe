from collections import defaultdict
from enum import Enum
from typing import TYPE_CHECKING, Optional, Type, Union

import numpy as np
from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    NodeItem,
    PictureDataType,
    Size,
    TableCell,
)
from docling_core.types.doc.base import PydanticSerCtxKey, round_pydantic_float
from docling_core.types.doc.page import SegmentedPdfPage, TextCell
from docling_core.types.io import DocumentStream

# DO NOT REMOVE; explicitly exposed from this location
from PIL.Image import Image
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FieldSerializationInfo,
    computed_field,
    field_serializer,
    field_validator,
)

if TYPE_CHECKING:
    from backend.pdf_backend import PdfPageBackend

from backend.abstract_backend import AbstractDocumentBackend
from datamodel.pipeline_options import PipelineOptions


class BaseFormatOption(BaseModel):
    """Base class for format options used by _DocumentConversionInput."""

    pipeline_options: Optional[PipelineOptions] = None
    backend: Type[AbstractDocumentBackend]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConversionStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    FAILURE = "failure"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    SKIPPED = "skipped"


class InputFormat(str, Enum):
    """A document format supported by document backend parsers."""
    IMAGE = "image"
    PDF = "pdf"


FormatToExtensions: dict[InputFormat, list[str]] = {
    InputFormat.PDF: ["pdf"],
    InputFormat.IMAGE: ["jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp"],
}

FormatToMimeType: dict[InputFormat, list[str]] = {
    InputFormat.IMAGE: [
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/gif",
        "image/bmp",
        "image/webp",
    ],
    InputFormat.PDF: ["application/pdf"],
}

MimeTypeToFormat: dict[str, list[InputFormat]] = {
    mime: [fmt for fmt in FormatToMimeType if mime in FormatToMimeType[fmt]]
    for value in FormatToMimeType.values()
    for mime in value
}


class DoclingComponentType(str, Enum):
    DOCUMENT_BACKEND = "document_backend"
    MODEL = "model"
    DOC_ASSEMBLER = "doc_assembler"
    USER_INPUT = "user_input"
    PIPELINE = "pipeline"


class ErrorItem(BaseModel):
    component_type: DoclingComponentType
    module_name: str
    error_message: str


class Cluster(BaseModel):
    id: int
    label: DocItemLabel
    bbox: BoundingBox
    confidence: float = 1.0
    cells: list[TextCell] = []
    children: list["Cluster"] = []  # Add child cluster support

    @field_serializer("confidence")
    def _serialize(self, value: float, info: FieldSerializationInfo) -> float:
        return round_pydantic_float(value, info.context, PydanticSerCtxKey.CONFID_PREC)


class BasePageElement(BaseModel):
    label: DocItemLabel
    id: int
    page_no: int
    cluster: Cluster
    text: Optional[str] = None


class LayoutPrediction(BaseModel):
    clusters: list[Cluster] = []


class ContainerElement(
    BasePageElement
):  # Used for Form and Key-Value-Regions, only for typing.
    pass


class Table(BasePageElement):
    otsl_seq: list[str]
    num_rows: int = 0
    num_cols: int = 0
    table_cells: list[TableCell]


class TableStructurePrediction(BaseModel):
    table_map: dict[int, Table] = {}


class TextElement(BasePageElement):
    text: str


class PagePredictions(BaseModel):
    layout: Optional[LayoutPrediction] = None
    tablestructure: Optional[TableStructurePrediction] = None


PageElement = Union[TextElement, Table, ContainerElement]


class AssembledUnit(BaseModel):
    elements: list[PageElement] = []
    body: list[PageElement] = []
    headers: list[PageElement] = []

class Page(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    page_no: int
    # page_hash: Optional[str] = None
    size: Optional[Size] = None
    parsed_page: Optional[SegmentedPdfPage] = None
    predictions: PagePredictions = PagePredictions()
    assembled: Optional[AssembledUnit] = None

    _backend: Optional["PdfPageBackend"] = (
        None  # Internal PDF backend. By default it is cleared during assembling.
    )
    _default_image_scale: float = 1.0  # Default image scale for external usage.
    _image_cache: dict[
        float, Image
    ] = {}  # Cache of images in different scales. By default it is cleared during assembling.

    @property
    def cells(self) -> list[TextCell]:
        """Return text cells as a read-only view of parsed_page.textline_cells."""
        if self.parsed_page is not None:
            return self.parsed_page.textline_cells
        else:
            return []

    def get_image(
        self,
        scale: float = 1.0,
        max_size: Optional[int] = None,
        cropbox: Optional[BoundingBox] = None,
    ) -> Optional[Image]:
        if self._backend is None:
            return self._image_cache.get(scale, None)

        if max_size:
            assert self.size is not None
            scale = min(scale, max_size / max(self.size.as_tuple()))

        if scale not in self._image_cache:
            if cropbox is None:
                self._image_cache[scale] = self._backend.get_page_image(scale=scale)
            else:
                return self._backend.get_page_image(scale=scale, cropbox=cropbox)

        if cropbox is None:
            return self._image_cache[scale]
        else:
            page_im = self._image_cache[scale]
            assert self.size is not None
            return page_im.crop(
                cropbox.to_top_left_origin(page_height=self.size.height)
                .scaled(scale=scale)
                .as_tuple()
            )

    @property
    def image(self) -> Optional[Image]:
        return self.get_image(scale=self._default_image_scale)



# Create a type alias for score values
# =========================================================
# CONFIDENCE SCORES (minimal pour compatibilité)
# =========================================================

ScoreValue = float

class PageConfidenceScores(BaseModel):
    parse_score: ScoreValue = np.nan
    layout_score: ScoreValue = np.nan
    table_score: ScoreValue = np.nan
    ocr_score: ScoreValue = np.nan

    @field_validator("parse_score", "layout_score", "table_score", "ocr_score", mode="before")
    @classmethod
    def _coerce_none_or_nan_str(cls, v):
        if v is None:
            return np.nan
        if isinstance(v, str) and v.strip().lower() in {"nan", "null", "none", ""}:
            return np.nan
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)

class ConfidenceReport(PageConfidenceScores):
    pages: dict[int, PageConfidenceScores] = Field(
        default_factory=lambda: defaultdict(PageConfidenceScores)
    )
    model_config = ConfigDict(arbitrary_types_allowed=True)
