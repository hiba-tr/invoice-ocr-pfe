import logging
import os
import traceback
from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Type, List

from backend.extraction.engine.datamodel.accelerator_options import AcceleratorOptions
from backend.extraction.engine.datamodel.base_models import Page
from backend.extraction.engine.datamodel.document import ConversionResult
from backend.extraction.engine.datamodel.pipeline_options import (
    EasyOcrOptions,
    OcrAutoOptions,
    OcrOptions,
    RapidOcrOptions,
    TesseractCliOcrOptions,
)
from backend.extraction.engine.models.base_ocr_model import BaseOcrModel
from backend.extraction.engine.models.stages.ocr.easyocr_model import EasyOcrModel
from backend.extraction.engine.models.stages.ocr.rapid_ocr_model import RapidOcrModel
from backend.extraction.engine.models.stages.ocr.tesseract_ocr_model import TesseractOcrModel

_log = logging.getLogger(__name__)

_TESSERACT_WIN_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class OcrAutoModel(BaseOcrModel):
    """
    Automatic OCR engine with Runtime Fallback capability.
    Attempts extraction using the highest priority available engine.
    If an engine fails on a specific page, it gracefully falls back to the next available engine.
    """
    def __init__(
        self,
        enabled: bool,
        artifacts_path: Optional[Path],
        options: OcrAutoOptions,
        accelerator_options: AcceleratorOptions,
    ):
        super().__init__(
            enabled=enabled,
            artifacts_path=artifacts_path,
            options=options,
            accelerator_options=accelerator_options,
        )
        self.options: OcrAutoOptions
        
        # We will hold a list of available engines instead of just one.
        self._available_engines: List[BaseOcrModel] = []

        if self.enabled:
            # Initialize engines in order of priority. 
            # If an engine fails to initialize, it simply won't be added to the fallback list.

            # ── PRIORITY 1: RapidOCR ────────────────────────────────────────
            try:
                import onnxruntime 
                from rapidocr import RapidOCR
                engine = RapidOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=RapidOcrOptions(
                        backend="onnxruntime",
                        bitmap_area_threshold=self.options.bitmap_area_threshold,
                        force_full_page_ocr=self.options.force_full_page_ocr,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("✅ Auto OCR Registered: RapidOCR (Priority 1)")
            except Exception as e:
                _log.warning("Failed to initialize RapidOCR: %s", e)

            # ── PRIORITY 2: EasyOCR ─────────────────────────────────────────
            try:
                import easyocr  # noqa
                engine = EasyOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=EasyOcrOptions(
                        lang=["fr", "en"],
                        bitmap_area_threshold=self.options.bitmap_area_threshold,
                        force_full_page_ocr=self.options.force_full_page_ocr,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("✅ Auto OCR Registered: EasyOCR (Priority 2)")
            except Exception as e:
                _log.warning("Failed to initialize EasyOCR: %s", e)

            # ── PRIORITY 3: TesseractCli ─────────────────────────────────────
            try:
                import pytesseract
                if os.name == "nt":
                    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WIN_PATH
                pytesseract.get_tesseract_version()
                engine = TesseractOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=TesseractCliOcrOptions(
                        lang=["fra", "eng"],
                        tesseract_cmd=_TESSERACT_WIN_PATH if os.name == "nt" else "tesseract",
                        psm=3,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("✅ Auto OCR Registered: TesseractCli (Priority 3)")
            except Exception as e:
                _log.warning("Failed to initialize TesseractCli: %s", e)

            # ── PRIORITY 4: PaddleOCR (If available) ───────────────────────
            try:
                from paddleocr import PaddleOCR  # noqa
                from backend.extraction.engine.models.stages.ocr.paddle_ocr_model import PaddleOcrModel
                from backend.extraction.engine.datamodel.pipeline_options import PaddleOcrOptions
                engine = PaddleOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=PaddleOcrOptions(
                        lang="fr",
                        confidence_threshold=0.3,
                        bitmap_area_threshold=self.options.bitmap_area_threshold,
                        force_full_page_ocr=self.options.force_full_page_ocr,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("✅ Auto OCR Registered: PaddleOCR (Priority 4)")
            except Exception as e:
                _log.debug("PaddleOCR not available (expected if not installed).")

            if not self._available_engines:
                _log.error("❌ CRITICAL: No OCR engines could be initialized. Please check your installations.")

    def __call__(
        self, conv_res: ConversionResult, page_batch: Iterable[Page]
    ) -> Iterable[Page]:
        if not self.enabled or not self._available_engines:
            yield from page_batch
            return

        for page in page_batch:
            success = False
            
            # Try engines in order of priority for this specific page
            for i, engine in enumerate(self._available_engines):
                engine_name = engine.__class__.__name__
                _log.debug("Attempting OCR on page %s with %s (Attempt %d/%d)", 
                           page.page_no, engine_name, i + 1, len(self._available_engines))
                
                try:
                    # We pass the page as a single-item list because engines expect an Iterable
                    # We must fully consume the generator to trigger any errors
                    list(engine(conv_res, [page])) 
                    
                    # If we reach here, the engine succeeded without raising an exception
                    success = True
                    _log.info("✅ OCR successful on page %s using %s", page.page_no, engine_name)
                    break # Break out of the engine loop, move to next page
                    
                except Exception as e:
                    # Log the failure with full stacktrace for debugging
                    _log.error(
                        "⚠️ Fallback Triggered: %s failed on page %s. Reason: %s", 
                        engine_name, page.page_no, str(e),
                        exc_info=True 
                    )
                    # Proceed to the next engine in the loop
                    continue

            if not success:
                _log.error("❌ FATAL: All available OCR engines failed for page %s.", page.page_no)
                # Depending on your pipeline's error handling strategy, 
                # you might want to raise here, or let the page pass without OCR cells.
                # Currently, it passes the page (which will likely have no textlines).

            yield page

    @classmethod
    def get_options_type(cls) -> Type[OcrOptions]:
        return OcrAutoOptions