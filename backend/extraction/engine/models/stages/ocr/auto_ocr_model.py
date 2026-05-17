import logging
import os
from pathlib import Path
from typing import Optional, Type, List

from backend.extraction.engine.datamodel.accelerator_options import AcceleratorOptions
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
        self._available_engines: List[BaseOcrModel] = []

        if self.enabled:
            # RapidOCR
            try:
                engine = RapidOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=RapidOcrOptions(
                        backend="onnxruntime",
                        text_score=0.3,
                        bitmap_area_threshold=self.options.bitmap_area_threshold,
                        force_full_page_ocr=self.options.force_full_page_ocr,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("OCR enregistre : RapidOCR (Priorite 1)")
            except Exception as e:
                _log.warning("RapidOCR non disponible : %s", e)

            # EasyOCR
            try:
                engine = EasyOcrModel(
                    enabled=self.enabled,
                    artifacts_path=artifacts_path,
                    options=EasyOcrOptions(
                        lang=["fr", "en"],
                        confidence_threshold=0.3,
                        bitmap_area_threshold=self.options.bitmap_area_threshold,
                        force_full_page_ocr=self.options.force_full_page_ocr,
                    ),
                    accelerator_options=accelerator_options,
                )
                self._available_engines.append(engine)
                _log.info("OCR enregistre : EasyOCR (Priorite 2)")
            except Exception as e:
                _log.warning("EasyOCR non disponible : %s", e)

            # Tesseract
            try:
                if os.name == "nt":
                    import pytesseract
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
                _log.info("OCR enregistre : Tesseract (Priorite 3)")
            except Exception as e:
                _log.warning("Tesseract non disponible : %s", e)

            if not self._available_engines:
                _log.error("Aucun moteur OCR disponible !")

    def __call__(self, conv_res, page_batch):
        if not self.enabled or not self._available_engines:
            yield from page_batch
            return

        for page in page_batch:
            success = False
            for i, engine in enumerate(self._available_engines):
                engine_name = engine.__class__.__name__
                try:
                    list(engine(conv_res, [page]))
                    success = True
                    _log.info("OCR reussi avec %s", engine_name)
                    break
                except Exception as e:
                    _log.warning("%s echoue -> fallback", engine_name)
                    continue

            if not success:
                _log.error("Tous les moteurs OCR ont echoue")

            yield page

    @classmethod
    def get_options_type(cls) -> Type[OcrOptions]:
        return OcrAutoOptions