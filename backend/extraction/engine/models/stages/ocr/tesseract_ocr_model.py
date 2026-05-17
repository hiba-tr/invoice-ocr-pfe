import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Type

import pytesseract
from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.page import BoundingRectangle, TextCell

from backend.extraction.engine.datamodel.accelerator_options import AcceleratorOptions
from backend.extraction.engine.datamodel.base_models import Page
from backend.extraction.engine.datamodel.document import ConversionResult
from backend.extraction.engine.datamodel.pipeline_options import OcrOptions, TesseractCliOcrOptions
from backend.extraction.engine.datamodel.settings import settings
from backend.extraction.engine.models.base_ocr_model import BaseOcrModel
from backend.extraction.engine.utils.profiling import TimeRecorder

_log = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class TesseractOcrModel(BaseOcrModel):

    def __init__(
        self,
        enabled: bool,
        artifacts_path: Optional[Path],
        options: "TesseractCliOcrOptions",
        accelerator_options: AcceleratorOptions,
    ):
        super().__init__(
            enabled=enabled,
            artifacts_path=artifacts_path,
            options=options,
            accelerator_options=accelerator_options,
        )
        self.options = options
        self.scale = 5

        if self.enabled:
            try:
                version = pytesseract.get_tesseract_version()
                _log.info("Tesseract version: %s", version)
            except Exception as e:
                raise RuntimeError(
                    f"Tesseract introuvable : {e}\n"
                    "Installez-le depuis https://github.com/UB-Mannheim/tesseract/wiki"
                )

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

                for ocr_rect in ocr_rects:
                    if ocr_rect.area() == 0:
                        continue

                    high_res_image = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )

                    # Preprocessing adaptatif — passthrough si image propre
                    high_res_image = preprocessor.get_enhanced_image(high_res_image)
                    pil_image = high_res_image.convert("RGB")

                    # lang : accepte liste ou string
                    lang_raw = getattr(self.options, "lang", ["fra", "eng"])
                    lang = "+".join(lang_raw) if isinstance(lang_raw, list) else lang_raw

                    # psm=3 : détection automatique — gère texte normal ET tableaux
                    # psm=6 : bloc uniforme — rate les tableaux, ne pas utiliser
                    psm = getattr(self.options, "psm", None)
                    if psm is None:
                        # Zone large = page entière → psm=3 (auto)
                        # Zone petite = cellule/tableau → psm=6 (bloc uniforme)
                        zone_area = (ocr_rect.r - ocr_rect.l) * (ocr_rect.b - ocr_rect.t)
                        page_area = page.size.width * page.size.height
                        psm = 3 if (zone_area / page_area) > 0.5 else 6
                    config = f"--oem 3 --psm {psm}"

                    try:
                        data = pytesseract.image_to_data(
                            pil_image,
                            lang=lang,
                            config=config,
                            output_type=pytesseract.Output.DICT,
                        )
                    except Exception as e:
                        _log.warning("Tesseract failed page %s: %s", page.page_no, e)
                        del high_res_image
                        continue

                    del high_res_image

                    n = len(data["text"])
                    for ix in range(n):
                        text = data["text"][ix].strip()
                        if not text:
                            continue

                        conf_raw = data["conf"][ix]
                        if conf_raw < 0:
                            continue

                        confidence = float(conf_raw) / 100.0

                        # Seuil bas (0.1) pour ne pas perdre les cellules de tableau
                        if confidence < 0.1:
                            continue

                        x = data["left"][ix]
                        y = data["top"][ix]
                        w = data["width"][ix]
                        h = data["height"][ix]

                        if w == 0 or h == 0:
                            continue

                        cells_coord = (
                            (x / self.scale) + ocr_rect.l,
                            (y / self.scale) + ocr_rect.t,
                            ((x + w) / self.scale) + ocr_rect.l,
                            ((y + h) / self.scale) + ocr_rect.t,
                        )

                        all_ocr_cells.append(
                            TextCell(
                                index=ix,
                                text=text,
                                orig=text,
                                confidence=confidence,
                                from_ocr=True,
                                rect=BoundingRectangle.from_bounding_box(
                                    BoundingBox.from_tuple(
                                        coord=cells_coord,
                                        origin=CoordOrigin.TOPLEFT,
                                    )
                                ),
                            )
                        )

                _log.debug(
                    "Page %s : %d cellules OCR extraites", page.page_no, len(all_ocr_cells)
                )
                self.post_process_cells(all_ocr_cells, page)

                if settings.debug.visualize_ocr:
                    self.draw_ocr_rects_and_cells(conv_res, page, ocr_rects)

                yield page

    @classmethod
    def get_options_type(cls) -> Type[OcrOptions]:
        return TesseractCliOcrOptions