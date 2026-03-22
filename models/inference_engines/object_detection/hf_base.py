

from __future__ import annotations

import logging
from numbers import Integral, Real
from typing import Any, Dict, Iterable, Sequence

import numpy as np

from models.inference_engines.object_detection.base import (
    BaseObjectDetectionEngine,
    BaseObjectDetectionEngineOptions,
    ObjectDetectionEngineInput,
    ObjectDetectionEngineOutput,
)

_log = logging.getLogger(__name__)


class SimpleObjectDetectionEngineBase(BaseObjectDetectionEngine):
    
    def __init__(
        self,
        *,
        options: BaseObjectDetectionEngineOptions,
    ) -> None:
        super().__init__(options=options)
        self.options: BaseObjectDetectionEngineOptions = options

        # Mapping optionnel (si tu veux l'utiliser plus tard)
        self._id_to_label: Dict[int, str] = {}

    # ---------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------

    def get_label_mapping(self) -> Dict[int, str]:
        """Retourne mapping id → label (optionnel)."""
        return self._id_to_label

    # ---------------------------------------------------------------------
    # Core output builder
    # ---------------------------------------------------------------------

    def _build_output(
        self,
        *,
        input_item: ObjectDetectionEngineInput,
        labels: Iterable[Any],
        scores: Iterable[Any],
        boxes: Iterable[Sequence[Any]],
        apply_score_threshold: bool = False,
    ) -> ObjectDetectionEngineOutput:
        """
        Construit un output standardisé.

        Compatible avec:
        - LayoutModel
        - TableModel
        """

        label_ids: list[int] = []
        output_scores: list[float] = []
        bboxes: list[list[float]] = []

        for label, score, box in zip(labels, scores, boxes):
            score_float = self._as_float(score)

            if apply_score_threshold and score_float < self.options.score_threshold:
                continue

            label_ids.append(self._as_int(label))
            output_scores.append(score_float)
            bboxes.append([self._as_float(v) for v in box])

        return ObjectDetectionEngineOutput(
            label_ids=label_ids,
            scores=output_scores,
            bboxes=bboxes,
            metadata=input_item.metadata.copy(),
        )

    # ---------------------------------------------------------------------
    # Utils robustes (gardés car utiles)
    # ---------------------------------------------------------------------

    @staticmethod
    def _as_float(value: Any) -> float:
        """Convertit vers float (robuste)."""
        if isinstance(value, Real):
            return float(value)

        if isinstance(value, np.ndarray):
            if value.size != 1:
                raise TypeError(
                    f"Expected scalar ndarray, got shape={value.shape}"
                )
            return float(value.reshape(-1)[0])

        try:
            import torch

            if isinstance(value, torch.Tensor):
                if value.numel() != 1:
                    raise TypeError(
                        f"Expected scalar tensor, got shape={tuple(value.shape)}"
                    )
                return float(value.item())
        except ImportError:
            pass

        raise TypeError(f"Unsupported value type: {type(value)!r}")

    @staticmethod
    def _as_int(value: Any) -> int:
        """Convertit vers int (robuste)."""
        if isinstance(value, Integral):
            return int(value)

        if isinstance(value, np.ndarray):
            if value.size != 1:
                raise TypeError(
                    f"Expected scalar ndarray, got shape={value.shape}"
                )
            return int(value.reshape(-1)[0])

        try:
            import torch

            if isinstance(value, torch.Tensor):
                if value.numel() != 1:
                    raise TypeError(
                        f"Expected scalar tensor, got shape={tuple(value.shape)}"
                    )
                return int(value.item())
        except ImportError:
            pass

        raise TypeError(f"Unsupported value type: {type(value)!r}")