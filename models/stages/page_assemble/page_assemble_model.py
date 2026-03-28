import logging
import re
from collections.abc import Iterable
from typing import List

from pydantic import BaseModel

from datamodel.base_models import (
    AssembledUnit,
    ContainerElement,
    Page,
    PageElement,
    Table,
    TextElement,
)
from datamodel.document import ConversionResult
from models.base_model import BasePageModel
from models.stages.layout.layout_model import LayoutModel
from utils.profiling import TimeRecorder

_log = logging.getLogger(__name__)


class PageAssembleOptions(BaseModel):
    pass


class PageAssembleModel(BasePageModel):
    def __init__(self, options: PageAssembleOptions):
        self.options = options

    def sanitize_text(self, lines):
        if len(lines) <= 1:
            return " ".join(lines)

        for ix, line in enumerate(lines[1:]):
            prev_line = lines[ix]

            if prev_line.endswith("-"):
                prev_words = re.findall(r"\b[\w]+\b", prev_line)
                line_words = re.findall(r"\b[\w]+\b", line)

                if (
                    len(prev_words)
                    and len(line_words)
                    and prev_words[-1].isalnum()
                    and line_words[0].isalnum()
                ):
                    lines[ix] = prev_line[:-1]
            else:
                lines[ix] += " "

        sanitized_text = "".join(lines)

        # Text normalization
        sanitized_text = sanitized_text.replace("⁄", "/")
        sanitized_text = sanitized_text.replace("’", "'")
        sanitized_text = sanitized_text.replace("‘", "'")
        sanitized_text = sanitized_text.replace("“", '"')
        sanitized_text = sanitized_text.replace("”", '"')
        sanitized_text = sanitized_text.replace("•", "·")

        return sanitized_text.strip()

    def __call__(
        self, conv_res: ConversionResult, page_batch: Iterable[Page]
    ) -> Iterable[Page]:
        for page in page_batch:
            assert page._backend is not None
            if not page._backend.is_valid():
                yield page
            else:
                with TimeRecorder(conv_res, "page_assemble"):
                    # layout must be present (even if empty)
                    assert page.predictions.layout is not None

                    elements: List[PageElement] = []
                    headers: List[PageElement] = []
                    body: List[PageElement] = []

                    for cluster in page.predictions.layout.clusters:
                        if cluster.label in LayoutModel.TEXT_ELEM_LABELS:
                            textlines = [
                                cell.text.replace("\x02", "-").strip()
                                for cell in cluster.cells
                                if len(cell.text.strip()) > 0
                            ]
                            text = self.sanitize_text(textlines)
                            text_el = TextElement(
                                label=cluster.label,
                                id=cluster.id,
                                text=text,
                                page_no=page.page_no,
                                cluster=cluster,
                            )
                            elements.append(text_el)

                            if cluster.label in LayoutModel.PAGE_HEADER_LABELS:
                                headers.append(text_el)
                            else:
                                body.append(text_el)
                        elif cluster.label in LayoutModel.TABLE_LABELS:
                            # Try to get structured table from predictions
                            tbl = None
                            if page.predictions.tablestructure:
                                tbl = page.predictions.tablestructure.table_map.get(
                                    cluster.id, None
                                )
                            if not tbl:  # fallback: add table without structure
                                tbl = Table(
                                    label=cluster.label,
                                    id=cluster.id,
                                    text="",
                                    otsl_seq=[],
                                    table_cells=[],
                                    cluster=cluster,
                                    page_no=page.page_no,
                                )
                            elements.append(tbl)
                            body.append(tbl)
                        elif cluster.label in LayoutModel.CONTAINER_LABELS:
                            # Used for key_value_region, etc.
                            container_el = ContainerElement(
                                label=cluster.label,
                                id=cluster.id,
                                page_no=page.page_no,
                                cluster=cluster,
                            )
                            elements.append(container_el)
                            body.append(container_el)
                        # NOTE: FIGURE_LABEL block removed (not needed for invoices)

                    page.assembled = AssembledUnit(
                        elements=elements, headers=headers, body=body
                    )

                yield page