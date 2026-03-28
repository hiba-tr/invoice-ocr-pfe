import importlib
import json
import logging
import platform
import sys
from io import BytesIO
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Iterable, Mapping, Optional, Type, Union, cast
from enum import Enum

import filetype
from pydantic import BaseModel, Field
from typing_extensions import Annotated, deprecated

from docling_core.types.doc import (
    DoclingDocument,
)
from docling_core.utils.file import resolve_source_to_stream
from docling_core.utils.legacy import docling_document_to_legacy

from backend.abstract_backend import (
    AbstractDocumentBackend,
    PaginatedDocumentBackend,
)
from datamodel.backend_options import BackendOptions
from datamodel.base_models import (
    ConfidenceReport,
    AssembledUnit,
    ConversionStatus,
    DocumentStream,
    ErrorItem,
    FormatToExtensions,
    FormatToMimeType,
    InputFormat,
    MimeTypeToFormat,
    Page,
)
from datamodel.settings import DocumentLimits
from utils.profiling import ProfilingItem
from utils.utils import create_file_hash

from pydantic import BaseModel, Field, ConfigDict


if TYPE_CHECKING:
    from datamodel.base_models import BaseFormatOption
    from document_converter import FormatOption

_log = logging.getLogger(__name__)

_EMPTY_DOCLING_DOC = DoclingDocument(name="dummy")


class InputDocument(BaseModel):
    """A document as an input of a Docling conversion."""

    file: Annotated[PurePath, Field(description="A path representation the input document.")]
    document_hash: Annotated[str, Field(description="A stable hash of the input document.")]
    valid: bool = Field(True, description="Whether this is a valid input document.")
    backend_options: Optional[BackendOptions] = None
    limits: DocumentLimits = DocumentLimits()
    format: Annotated[InputFormat, Field(description="The document format.")]
    filesize: Optional[int] = None
    page_count: int = 0

    _backend: AbstractDocumentBackend

    def __init__(
        self,
        path_or_stream: Union[BytesIO, Path],
        format: InputFormat,
        backend: Type[AbstractDocumentBackend],
        backend_options: Optional[BackendOptions] = None,
        filename: Optional[str] = None,
        limits: Optional[DocumentLimits] = None,
    ) -> None:
        super().__init__(
            file="",
            document_hash="",
            format=format,
            backend_options=backend_options,
        )
        self.limits = limits or DocumentLimits()

        try:
            if isinstance(path_or_stream, Path):
                self.file = path_or_stream
                self.filesize = path_or_stream.stat().st_size
            elif isinstance(path_or_stream, BytesIO):
                assert filename is not None
                self.file = PurePath(filename)
                self.filesize = path_or_stream.getbuffer().nbytes
            else:
                raise RuntimeError(f"Unexpected type path_or_stream: {type(path_or_stream)}")

            self.document_hash = create_file_hash(path_or_stream)
            self._backend = backend(self, path_or_stream=path_or_stream, options=backend_options)
            if not self._backend.is_valid():
                self.valid = False

            if self.valid and self._backend.supports_pagination() and isinstance(
                self._backend, PaginatedDocumentBackend
            ):
                self.page_count = self._backend.page_count()
                if not self.page_count <= self.limits.max_num_pages:
                    self.valid = False
                elif self.page_count < self.limits.page_range[0]:
                    self.valid = False

        except (FileNotFoundError, OSError) as e:
            self.valid = False
            _log.exception(f"File {getattr(self.file, 'name', str(self.file))} not found.", exc_info=e)
        except RuntimeError as e:
            self.valid = False
            _log.exception(
                f"Unexpected error opening {getattr(self.file, 'name', str(self.file))}.",
                exc_info=e,
            )


class DoclingVersion(BaseModel):
    docling_core_version: str = importlib.metadata.version("docling-core")
    platform_str: str = platform.platform()
    py_impl_version: str = sys.implementation.cache_tag
    py_lang_version: str = platform.python_version()


class ConversionAssets(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True) 

    version: DoclingVersion = DoclingVersion()
    timestamp: Optional[str] = None
    status: ConversionStatus = ConversionStatus.PENDING
    errors: list[ErrorItem] = []
    pages: list[Page] = []
    timings: dict[str, ProfilingItem] = {}
    confidence: ConfidenceReport = Field(default_factory=ConfidenceReport)
    document: DoclingDocument = _EMPTY_DOCLING_DOC

    @property
    @deprecated("Use document instead.")
    def legacy_document(self):
        return docling_document_to_legacy(self.document)


class ConversionResult(ConversionAssets):
    input: InputDocument
    assembled: AssembledUnit = AssembledUnit()

    
class _DocumentConversionInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    path_or_stream_iterator: Iterable[Union[Path, str, DocumentStream]]
    headers: Optional[dict[str, str]] = None
    limits: Optional[DocumentLimits] = DocumentLimits()

    def docs(self, format_options: Mapping[InputFormat, "BaseFormatOption"]) -> Iterable[InputDocument]:
        for item in self.path_or_stream_iterator:
            obj = resolve_source_to_stream(item, self.headers) if isinstance(item, str) else item
            format = self._guess_format(obj)
            if not format or format not in format_options:
                _log.error(f"Input document {obj.name} with format {format} does not match allowed formats")
                continue  # ← IGNORER CE DOCUMENT
            
            options = format_options[format]
            backend = options.backend
            backend_options: Optional[BackendOptions] = None
            if "backend_options" in options.model_fields_set:
                backend_options = cast("FormatOption", options).backend_options

            path_or_stream: Union[BytesIO, Path]
            if isinstance(obj, Path):
                path_or_stream = obj
            elif isinstance(obj, DocumentStream):
                path_or_stream = obj.stream
            else:
                raise RuntimeError(f"Unexpected obj type in iterator: {type(obj)}")

            yield InputDocument(
                path_or_stream=path_or_stream,
                format=format,
                filename=obj.name,
                limits=self.limits,
                backend=backend,
                backend_options=backend_options,
            )

    def _guess_format(self, obj: Union[Path, DocumentStream]) -> Optional[InputFormat]:
        content = b""
        mime = None
        if isinstance(obj, Path):
            mime = filetype.guess_mime(str(obj))
            if mime is None:
                ext = obj.suffix[1:]
                mime = _DocumentConversionInput._mime_from_extension(ext)
        elif isinstance(obj, DocumentStream):
            content = obj.stream.read(8192)
            obj.stream.seek(0)
            mime = filetype.guess_mime(content)
            if mime is None:
                ext = obj.name.rsplit(".", 1)[-1] if "." in obj.name else ""
                mime = _DocumentConversionInput._mime_from_extension(ext.lower())
        formats = MimeTypeToFormat.get(mime or "text/plain", [])
        if formats:
            return formats[0]
        return None

    @staticmethod
    def _mime_from_extension(ext: str) -> Optional[str]:
        for fmt in InputFormat:
            if ext in FormatToExtensions.get(fmt, []):
                return FormatToMimeType[fmt][0]
        return None