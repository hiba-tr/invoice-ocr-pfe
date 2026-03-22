import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import List, Optional

from backend.abstract_backend import (
    AbstractDocumentBackend,
    PaginatedDocumentBackend,
)
from datamodel.base_models import (
    ConversionStatus,
    DoclingComponentType,
    ErrorItem,
    Page,
)
from datamodel.document import ConversionResult, InputDocument
from datamodel.pipeline_options import PipelineOptions, ConvertPipelineOptions

_log = logging.getLogger(__name__)


# =========================
# BASE PIPELINE
# =========================
class BasePipeline(ABC):
    def __init__(self, pipeline_options: PipelineOptions):
        self.pipeline_options = pipeline_options

    def execute(self, in_doc: InputDocument, raises_on_error: bool = False) -> ConversionResult:
        conv_res = ConversionResult(input=in_doc)

        _log.info(f"Processing document {in_doc.file}")

        try:
            # 1. Build document (core step)
            conv_res = self._build_document(conv_res)

            # 2. Determine final status
            conv_res.status = self._determine_status(conv_res)

        except Exception as e:
            conv_res.status = ConversionStatus.FAILURE

            if not raises_on_error:
                conv_res.errors.append(
                    ErrorItem(
                        component_type=DoclingComponentType.PIPELINE,
                        module_name=self.__class__.__name__,
                        error_message=str(e),
                    )
                )
            else:
                raise RuntimeError(f"Pipeline {self.__class__.__name__} failed") from e

        finally:
            self._unload(conv_res)

        return conv_res

    @abstractmethod
    def _build_document(self, conv_res: ConversionResult) -> ConversionResult:
        pass

    @abstractmethod
    def _determine_status(self, conv_res: ConversionResult) -> ConversionStatus:
        pass

    def _unload(self, conv_res: ConversionResult):
        pass

    @classmethod
    @abstractmethod
    def is_backend_supported(cls, backend: AbstractDocumentBackend):
        pass



# =========================
# ConvertPipeline
# =========================

class ConvertPipeline(BasePipeline):
    def __init__(self, pipeline_options: ConvertPipelineOptions):
        super().__init__(pipeline_options)
        self.pipeline_options: ConvertPipelineOptions

        # Pour DocCore factures, pas d'enrichment ni modèles IA
        self.enrichment_pipe = []  # vide, inutile pour PDF/Image de facture

    @classmethod
    @abstractmethod
    def get_default_options(cls) -> ConvertPipelineOptions:
        pass


    @classmethod
    @abstractmethod
    def get_default_options(cls) -> ConvertPipelineOptions:
        pass

# =========================
# PAGINATED PIPELINE (PDF + IMAGE)
# =========================
class PaginatedPipeline(BasePipeline):
    def __init__(self, pipeline_options: PipelineOptions):
        super().__init__(pipeline_options)
        self.keep_backend = False

    def _build_document(self, conv_res: ConversionResult) -> ConversionResult:
        backend = conv_res.input._backend

        # Vérifier backend compatible
        if not isinstance(backend, PaginatedDocumentBackend):
            raise RuntimeError(
                f"Backend {type(backend).__name__} is not paginated."
            )

        start_page, end_page = conv_res.input.limits.page_range

        # Création des pages
        for i in range(conv_res.input.page_count):
            if (start_page - 1) <= i <= (end_page - 1):
                page = Page(page_no=i + 1)

                # Charger backend page
                page._backend = backend.load_page(i)

                conv_res.pages.append(page)

        return conv_res

    def _unload(self, conv_res: ConversionResult):
        # Nettoyage des pages
        for page in conv_res.pages:
            if page._backend is not None:
                page._backend.unload()

        # Nettoyage document
        if conv_res.input._backend:
            conv_res.input._backend.unload()

    def _determine_status(self, conv_res: ConversionResult) -> ConversionStatus:
        status = ConversionStatus.SUCCESS

        for page in conv_res.pages:
            if page._backend is None or not page._backend.is_valid():
                conv_res.errors.append(
                    ErrorItem(
                        component_type=DoclingComponentType.DOCUMENT_BACKEND,
                        module_name=type(page._backend).__name__ if page._backend else "None",
                        error_message=f"Page {page.page_no} failed to load.",
                    )
                )
                status = ConversionStatus.PARTIAL_SUCCESS

        return status

    @classmethod
    def is_backend_supported(cls, backend: AbstractDocumentBackend):
        return isinstance(backend, PaginatedDocumentBackend)