import hashlib
import logging
import sys
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Optional, Type, Union

from pydantic import model_validator
from typing_extensions import Self

from backend.abstract_backend import AbstractDocumentBackend
from backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from backend.image_backend import ImageDocumentBackend

from datamodel.backend_options import BackendOptions, PdfBackendOptions
from datamodel.base_models import (
    BaseFormatOption,
    ConversionStatus,
    DoclingComponentType,
    DocumentStream,
    ErrorItem,
    InputFormat,
)
from datamodel.document import (
    ConversionResult,
    InputDocument,
    _DocumentConversionInput,
)
from datamodel.pipeline_options import PipelineOptions
from datamodel.settings import (
    DEFAULT_PAGE_RANGE,
    DocumentLimits,
    PageRange,
    settings,
)
from exceptions import ConversionError
from pipeline.base_pipeline import BasePipeline
from pipeline.standard_pdf_pipeline import StandardPdfPipeline
from utils.utils import chunkify

_log = logging.getLogger(__name__)


class FormatOption(BaseFormatOption):
    pipeline_cls: Type[BasePipeline]
    backend_options: Optional[BackendOptions] = None

    @model_validator(mode="after")
    def set_optional_field_default(self) -> Self:
        if self.pipeline_options is None:
            self.pipeline_options = self.pipeline_cls.get_default_options()
        return self


class ImageFormatOption(FormatOption):
    pipeline_cls: Type = StandardPdfPipeline
    backend: Type[AbstractDocumentBackend] = ImageDocumentBackend


class PdfFormatOption(FormatOption):
    pipeline_cls: Type = StandardPdfPipeline
    backend: Type[AbstractDocumentBackend] = DoclingParseV4DocumentBackend
    backend_options: Optional[PdfBackendOptions] = None


def _get_default_option(format: InputFormat) -> FormatOption:
    format_to_default_options = {
        InputFormat.IMAGE: ImageFormatOption(),
        InputFormat.PDF: PdfFormatOption(),
    }
    if (options := format_to_default_options.get(format)) is not None:
        return options
    else:
        raise RuntimeError(f"No default options configured for {format}")


class DocumentConverter:
    _default_download_filename = "file"

    def __init__(
        self,
        allowed_formats: Optional[list[InputFormat]] = None,
        format_options: Optional[dict[InputFormat, FormatOption]] = None,
    ) -> None:
        self.allowed_formats: list[InputFormat] = (
            allowed_formats if allowed_formats is not None else list(InputFormat)
        )

        normalized_format_options = format_options or {}

        # Options par format
        self.format_to_options: dict[InputFormat, FormatOption] = {
            format: (
                _get_default_option(format=format)
                if (custom_option := normalized_format_options.get(format)) is None
                else custom_option
            )
            for format in self.allowed_formats
        }

        #  SIMPLIFICATION : création unique des pipelines
        self._pipelines: dict[InputFormat, BasePipeline] = {}
        for fmt, opt in self.format_to_options.items():
            if opt.pipeline_options is not None:
                self._pipelines[fmt] = opt.pipeline_cls(   #le stocker pour réutilisation
                    pipeline_options=opt.pipeline_options  
                )
                _log.info(f"Pipeline initialisé pour {fmt.value}")

    #Sert juste à vérifier qu’un pipeline existe pour ce format.
    def initialize_pipeline(self, format: InputFormat):
        """Vérifie qu'un pipeline est disponible pour le format"""
        if format not in self._pipelines:
            raise ConversionError(f"No pipeline could be initialized for format {format}")

    def convert(
        self,
        source: Union[Path, str, DocumentStream],
        raises_on_error: bool = True,
        max_num_pages: int = sys.maxsize,
        max_file_size: int = sys.maxsize,
        page_range: PageRange = DEFAULT_PAGE_RANGE,
    ) -> ConversionResult:
        all_res = self.convert_all(
            source=[source],
            raises_on_error=raises_on_error,
            max_num_pages=max_num_pages,
            max_file_size=max_file_size,
            page_range=page_range,
        )
        #convert_all() retourne plusieurs résultats (un par fichier)
        return next(all_res) #donne-moi le premier résultat de conversion

    def convert_all(
        self,
        source: Iterable[Union[Path, str, DocumentStream]],
        raises_on_error: bool = True,
        max_num_pages: int = sys.maxsize,
        max_file_size: int = sys.maxsize,
        page_range: PageRange = DEFAULT_PAGE_RANGE,
    ) -> Iterator[ConversionResult]:
        limits = DocumentLimits(
            max_num_pages=max_num_pages,
            max_file_size=max_file_size,
            page_range=page_range,
        )
        conv_input = _DocumentConversionInput(
            path_or_stream_iterator=source, limits=limits
        )
        conv_res_iter = self._convert(conv_input, raises_on_error=raises_on_error)

        had_result = False
        for conv_res in conv_res_iter:
            had_result = True
            if raises_on_error and conv_res.status not in {
                ConversionStatus.SUCCESS,
                ConversionStatus.PARTIAL_SUCCESS,
            }:
                error_details = ""
                if conv_res.errors:
                    error_messages = [err.error_message for err in conv_res.errors]
                    error_details = f" Errors: {'; '.join(error_messages)}"
                raise ConversionError(
                    f"Conversion failed for: {conv_res.input.file} with status: "
                    f"{conv_res.status}.{error_details}"
                )
            else:
                yield conv_res

        if not had_result and raises_on_error:
            raise ConversionError(
                "Conversion failed because the provided file has no recognizable "
                "format or it wasn't in the list of allowed formats."
            )

    def _convert(
        self, conv_input: _DocumentConversionInput, raises_on_error: bool
    ) -> Iterator[ConversionResult]:
        start_time = time.monotonic()

        for input_batch in chunkify(
            conv_input.docs(self.format_to_options),
            settings.perf.doc_batch_size,
        ):
            _log.info("Going to convert document batch...")
            process_func = partial(
                self._process_document, raises_on_error=raises_on_error
            )

            #  CONVERSION PARALLÈLE CONSERVÉE
            if (
                settings.perf.doc_batch_concurrency > 1
                and settings.perf.doc_batch_size > 1
            ):
                with ThreadPoolExecutor(
                    max_workers=settings.perf.doc_batch_concurrency
                ) as pool:
                    for item in pool.map(
                        process_func,
                        input_batch,
                    ):
                        yield item
            else:
                for item in map(
                    process_func,
                    input_batch,
                ):
                    elapsed = time.monotonic() - start_time
                    start_time = time.monotonic()
                    _log.info(
                        f"Finished converting document {item.input.file.name} in {elapsed:.2f} sec."
                    )
                    yield item

    # SIMPLIFICATION : récupération directe du pipeline (pas de hash, pas de cache)
    def _get_pipeline(self, doc_format: InputFormat) -> Optional[BasePipeline]:
        """Retourne le pipeline pour un format (simple et direct)"""
        return self._pipelines.get(doc_format)

    def _process_document(
        self, in_doc: InputDocument, raises_on_error: bool
    ) -> ConversionResult:
        valid = (
            self.allowed_formats is not None and in_doc.format in self.allowed_formats
        )
        if valid:
            conv_res = self._execute_pipeline(in_doc, raises_on_error=raises_on_error)
        else:
            error_message = f"File format not allowed: {in_doc.file}"
            if raises_on_error:
                raise ConversionError(error_message)
            else:
                error_item = ErrorItem(
                    component_type=DoclingComponentType.USER_INPUT,
                    module_name="",
                    error_message=error_message,
                )
                conv_res = ConversionResult(
                    input=in_doc, status=ConversionStatus.SKIPPED, errors=[error_item]
                )

        return conv_res

    def _execute_pipeline(
        self, in_doc: InputDocument, raises_on_error: bool
    ) -> ConversionResult:
        if in_doc.valid:
            pipeline = self._get_pipeline(in_doc.format)
            if pipeline is not None:
                conv_res = pipeline.execute(in_doc, raises_on_error=raises_on_error)
            else:
                if raises_on_error:
                    raise ConversionError(
                        f"No pipeline could be initialized for {in_doc.file}."
                    )
                else:
                    conv_res = ConversionResult(
                        input=in_doc,
                        status=ConversionStatus.FAILURE,
                    )
        else:
            if raises_on_error:
                raise ConversionError(f"Input document {in_doc.file} is not valid.")
            else:
                conv_res = ConversionResult(
                    input=in_doc,
                    status=ConversionStatus.FAILURE,
                )

        return conv_res