"""
Backend PDF simplifié mais complet pour DocCore
- Extrait le texte natif avec ses coordonnées
- Gère les mots de passe
- Implémente toutes les méthodes abstraites requises
"""

import logging
from collections.abc import Iterable
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

import pypdfium2 as pdfium
from docling_core.types.doc import BoundingBox, CoordOrigin, Size, TextCell
from docling_core.types.doc.page import BoundingRectangle, SegmentedPdfPage
from pypdfium2 import PdfTextPage
from pypdfium2._helpers.misc import PdfiumError
from PIL import Image

from backend.pdf_backend import PdfDocumentBackend, PdfPageBackend
from datamodel.backend_options import PdfBackendOptions
from utils.locks import pypdfium2_lock

if TYPE_CHECKING:
    from datamodel.document import InputDocument

_log = logging.getLogger(__name__)


class PyPdfiumPageBackend(PdfPageBackend):
    """Backend PDF qui implémente toutes les méthodes abstraites"""
    
    def __init__(
        self, pdfium_doc: pdfium.PdfDocument, document_hash: str, page_no: int
    ):
        self.valid = True
        try:
            self._ppage: pdfium.PdfPage = pdfium_doc[page_no]
        except PdfiumError:
            _log.info(
                f"Erreur chargement page {page_no} du document {document_hash}.",
                exc_info=True,
            )
            self.valid = False
        self.text_page: Optional[PdfTextPage] = None

    def is_valid(self) -> bool:
        return self.valid

    # =========================================================
    # MÉTHODES REQUISES PAR L'INTERFACE ABSTRAITE
    # =========================================================
    
    def get_text_cells(self) -> Iterable[TextCell]:
        """Extrait toutes les cellules de texte de la page"""
        with pypdfium2_lock:
            if not self.text_page:
                self.text_page = self._ppage.get_textpage()

        cells = []
        page_size = self.get_size()

        with pypdfium2_lock:
            for i in range(self.text_page.count_rects()):
                rect = self.text_page.get_rect(i)
                text_piece = self.text_page.get_text_bounded(*rect)
                x0, y0, x1, y1 = rect
                cells.append(
                    TextCell(
                        index=i,
                        text=text_piece,
                        orig=text_piece,
                        from_ocr=False,
                        rect=BoundingRectangle.from_bounding_box(
                            BoundingBox(
                                l=x0,
                                b=y0,
                                r=x1,
                                t=y1,
                                coord_origin=CoordOrigin.BOTTOMLEFT,
                            )
                        ).to_top_left_origin(page_size.height),
                    )
                )
        return cells

    def get_bitmap_rects(self, scale: float = 1) -> Iterable[BoundingBox]:
        """Retourne les positions des images dans la page (version vide si pas d'images)"""
        return []  # Pas besoin d'images pour ton PFE

    def get_page_image(self, scale: float = 1, cropbox: Optional[BoundingBox] = None) -> Image.Image:
        """Génère l'image de la page (pour l'OCR si nécessaire)"""
        page_size = self.get_size()

        if not cropbox:
            cropbox = BoundingBox(
                l=0,
                r=page_size.width,
                t=0,
                b=page_size.height,
                coord_origin=CoordOrigin.TOPLEFT,
            )
            padbox = BoundingBox(
                l=0, r=0, t=0, b=0, coord_origin=CoordOrigin.BOTTOMLEFT
            )
        else:
            padbox = cropbox.to_bottom_left_origin(page_size.height).model_copy()
            padbox.r = page_size.width - padbox.r
            padbox.t = page_size.height - padbox.t

        with pypdfium2_lock:
            image = (
                self._ppage.render(
                    scale=scale * 1.5,
                    rotation=0,
                    crop=padbox.as_tuple(),
                )
                .to_pil()
                .resize(
                    size=(round(cropbox.width * scale), round(cropbox.height * scale))
                )
            )
        return image

    def get_segmented_page(self) -> Optional[SegmentedPdfPage]:
        """Retourne la page segmentée (version simplifiée)"""
        if not self.valid:
            return None

        text_cells = list(self.get_text_cells())
        page_size = self.get_size()

        # Créer une géométrie simple
        from docling_core.types.doc.page import PdfPageGeometry, PdfPageBoundaryType, BoundingRectangle
        
        bbox = BoundingBox(l=0, r=page_size.width, t=0, b=page_size.height, coord_origin=CoordOrigin.TOPLEFT)
        rect = BoundingRectangle.from_bounding_box(bbox)
        
        dimension = PdfPageGeometry(
            angle=0.0,
            rect=rect,
            boundary_type=PdfPageBoundaryType.CROP_BOX,
            art_bbox=bbox,
            bleed_bbox=bbox,
            crop_bbox=bbox,
            media_bbox=bbox,
            trim_bbox=bbox,
        )

        return SegmentedPdfPage(
            dimension=dimension,
            textline_cells=text_cells,
            char_cells=[],
            word_cells=[],
            has_textlines=len(text_cells) > 0,
            has_words=False,
            has_chars=False,
        )

    def get_text_in_rect(self, bbox: BoundingBox) -> str:
        """Extrait le texte dans un rectangle donné"""
        with pypdfium2_lock:
            if not self.text_page:
                self.text_page = self._ppage.get_textpage()

        if bbox.coord_origin != CoordOrigin.BOTTOMLEFT:
            bbox = bbox.to_bottom_left_origin(self.get_size().height)

        with pypdfium2_lock:
            text_piece = self.text_page.get_text_bounded(*bbox.as_tuple())

        return text_piece

    def get_size(self) -> Size:
        with pypdfium2_lock:
            return Size(width=self._ppage.get_width(), height=self._ppage.get_height())

    def unload(self):
        self._ppage = None
        self.text_page = None


class PyPdfiumDocumentBackend(PdfDocumentBackend):
    """Backend PDF simplifié"""
    
    def __init__(
        self,
        in_doc: "InputDocument",
        path_or_stream: Union[BytesIO, Path],
        options: PdfBackendOptions = None,
    ):
        super().__init__(in_doc, path_or_stream, options)

        password = None
        if options is not None and hasattr(options, 'password') and options.password:
            password = options.password.get_secret_value()
            
        try:
            with pypdfium2_lock:
                self._pdoc = pdfium.PdfDocument(self.path_or_stream, password=password)
        except PdfiumError as e:
            raise RuntimeError(
                f"pypdfium n'a pas pu charger le document: {e}"
            ) from e

    def page_count(self) -> int:
        with pypdfium2_lock:
            return len(self._pdoc)

    def load_page(self, page_no: int) -> PyPdfiumPageBackend:
        with pypdfium2_lock:
            return PyPdfiumPageBackend(self._pdoc, self.document_hash, page_no)

    def is_valid(self) -> bool:
        return self.page_count() > 0

    def unload(self):
        super().unload()
        with pypdfium2_lock:
            self._pdoc.close()
            self._pdoc = None