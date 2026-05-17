import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Type

import numpy as np
from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.page import BoundingRectangle, TextCell

from backend.extraction.engine.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from backend.extraction.engine.datamodel.base_models import Page
from backend.extraction.engine.datamodel.document import ConversionResult
from backend.extraction.engine.datamodel.pipeline_options import OcrOptions, PaddleOcrOptions
from backend.extraction.engine.datamodel.settings import settings
from backend.extraction.engine.models.base_ocr_model import BaseOcrModel
from backend.extraction.engine.utils.accelerator_utils import decide_device
from backend.extraction.engine.utils.profiling import TimeRecorder

_log = logging.getLogger(__name__)


class PaddleOcrModel(BaseOcrModel):
    """
    Moteur OCR basé sur PaddleOCR v3.
    - Supporte le français, l'anglais, le manuscrit et les images floues
    - Meilleur que Tesseract sur les tableaux denses et les documents dégradés
    - Utilise les modèles mobile pour compatibilité CPU Windows
    """

    def __init__(
        self,
        enabled: bool,
        artifacts_path: Optional[Path],
        options: "PaddleOcrOptions",
        accelerator_options: AcceleratorOptions,
    ):
        super().__init__(
            enabled=enabled,
            artifacts_path=artifacts_path,
            options=options,
            accelerator_options=accelerator_options,
        )
        self.options = options
        self.scale = 4  # 72 dpi × 4 = 288 dpi

        if self.enabled:
            try:
                from paddleocr import PaddleOCR

                # ── Désactive oneDNN qui cause des crashes sur Windows CPU ──
                os.environ["FLAGS_use_mkldnn"] = "0"
                os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

                device = decide_device(accelerator_options.device)
                use_gpu = str(AcceleratorDevice.CUDA.value).lower() in device

                lang = getattr(self.options, "lang", "fr")

                self.reader = PaddleOCR(
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_det_thresh=0.3,
                    text_rec_score_thresh=0.3,
                    enable_mkldnn=False,      # ← désactive MKL-DNN
                    engine="paddle_dynamic",  # ← bypass oneDNN complètement
                )

                _log.info(
                    "PaddleOCR v3 initialisé (mobile, CPU=%s, lang=%s)",
                    not use_gpu, lang
                )

            except ImportError:
                raise ImportError(
                    "PaddleOCR n'est pas installé. "
                    "Installez-le via : pip install paddlepaddle paddleocr"
                )
            except Exception as e:
                raise RuntimeError(f"Erreur initialisation PaddleOCR: {e}")

    def __call__(
        self, conv_res: ConversionResult, page_batch: Iterable[Page]
    ) -> Iterable[Page]:
        if not self.enabled:
            yield from page_batch
            return

        from backend.extraction.engine.models.utils.image_preprocessing.image_preprocessor import ImagePreprocessor
        preprocessor = ImagePreprocessor()

        for page in page_batch:
            assert page._backend is not None
            if not page._backend.is_valid():
                yield page
                continue

            with TimeRecorder(conv_res, "ocr"):
                ocr_rects = self.get_ocr_rects(page)
                all_ocr_cells = []

                confidence_threshold = getattr(
                    self.options, "confidence_threshold", 0.3
                )

                for ocr_rect in ocr_rects:
                    if ocr_rect.area() == 0:
                        continue

                    # Image native haute résolution
                    high_res_image = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )

                    # Preprocessing adaptatif — passthrough si image propre
                    high_res_image = preprocessor.get_enhanced_image(high_res_image)

                    # PaddleOCR v3 attend un array numpy RGB
                    im = np.array(high_res_image.convert("RGB"))

                    try:
                        # PaddleOCR v3 : utilise predict() au lieu de ocr()
                        result = self.reader.predict(im)
                    except Exception as e:
                        _log.error(
                            "PaddleOCR failed page %s: %s",
                            page.page_no, e, exc_info=True
                        )
                        del high_res_image
                        continue

                    del high_res_image

                    if not result:
                        continue

                    # PaddleOCR v3 retourne une liste de dicts :
                    # "dt_polys"   : boîtes (4 points chacune)
                    # "rec_texts"  : textes reconnus
                    # "rec_scores" : scores de confiance
                    for res in result:
                        if res is None:
                            continue

                        # Supporte dict et objet avec attributs
                        if isinstance(res, dict):
                            boxes  = res.get("dt_polys", [])
                            texts  = res.get("rec_texts", [])
                            scores = res.get("rec_scores", [])
                        else:
                            boxes  = getattr(res, "dt_polys",   [])
                            texts  = getattr(res, "rec_texts",  [])
                            scores = getattr(res, "rec_scores", [])

                        if not boxes:
                            continue

                        for box, text, score in zip(boxes, texts, scores):
                            text = str(text).strip()

                            if not text:
                                continue
                            if float(score) < confidence_threshold:
                                continue

                            # box = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                            # Rectangle englobant
                            xs = [float(p[0]) for p in box]
                            ys = [float(p[1]) for p in box]
                            x0, y0 = min(xs), min(ys)
                            x1, y1 = max(xs), max(ys)

                            # Conversion pixel → coordonnées PDF
                            coord = (
                                (x0 / self.scale) + ocr_rect.l,
                                (y0 / self.scale) + ocr_rect.t,
                                (x1 / self.scale) + ocr_rect.l,
                                (y1 / self.scale) + ocr_rect.t,
                            )

                            all_ocr_cells.append(
                                TextCell(
                                    index=len(all_ocr_cells),
                                    text=text,
                                    orig=text,
                                    confidence=float(score),
                                    from_ocr=True,
                                    rect=BoundingRectangle.from_bounding_box(
                                        BoundingBox.from_tuple(
                                            coord=coord,
                                            origin=CoordOrigin.TOPLEFT,
                                        )
                                    ),
                                )
                            )

                _log.debug(
                    "Page %s : %d cellules OCR extraites (PaddleOCR)",
                    page.page_no, len(all_ocr_cells)
                )

                self.post_process_cells(all_ocr_cells, page)

                if settings.debug.visualize_ocr:
                    self.draw_ocr_rects_and_cells(conv_res, page, ocr_rects)

                yield page

    @classmethod
    def get_options_type(cls) -> Type[OcrOptions]:
        return PaddleOcrOptions