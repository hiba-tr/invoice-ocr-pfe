"""Base classes for object-detection inference engines."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PIL.Image import Image
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from docling.datamodel.stage_model_specs import EngineModelConfig

_log = logging.getLogger(__name__)


class ObjectDetectionEngineType(str, Enum):
    """Supported inference engine types for object-detection models."""

    ONNXRUNTIME = "onnxruntime"
    TRANSFORMERS = "transformers"


class BaseObjectDetectionEngineOptions(BaseModel):
    """Base configuration shared across object-detection engines."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    engine_type: ObjectDetectionEngineType = Field(
        description="Type of inference engine to use",
    )

    score_threshold: float = Field(
        default=0.3,
        description="Minimum confidence score to keep a detection (0.0 to 1.0)",
    )


class ObjectDetectionEngineInput(BaseModel):
    pass


class ObjectDetectionEngineOutput(BaseModel):
    pass


class BaseObjectDetectionEngine(ABC):
    """Abstract base-class for object-detection engines."""

    def __init__(
        self,
        options: BaseObjectDetectionEngineOptions,
        model_config: Optional[EngineModelConfig] = None,
    ) -> None:
        """Initialize the engine.

        Args:
            options: Engine-specific configuration options
            model_config: Model configuration (repo_id, revision, extra_config)
        """
        self.options = options
        self.model_config = model_config
        self._initialized = False

    @abstractmethod
    def initialize(self) -> None:
        """Initialize engine resources (load models, allocate buffers, etc.)."""

    @abstractmethod
    def predict_batch(
        self, input_batch: List[ObjectDetectionEngineInput]
    ) -> List[ObjectDetectionEngineOutput]:
        """Run inference on a batch of inputs."""

    @abstractmethod
    def get_label_mapping(self) -> Dict[int, str]:
        """Get the label mapping for this model.

        Returns:
            Dictionary mapping label IDs to label names
        """

    def predict(
        self, input_data: ObjectDetectionEngineInput
    ) -> ObjectDetectionEngineOutput:
        """Helper to run inference on a single input."""
        if not self._initialized:
            _log.debug("Initializing %s for single prediction", type(self).__name__)
            self.initialize()

        results = self.predict_batch([input_data])
        return results[0]

    def __call__(
        self,
        input_data: ObjectDetectionEngineInput | List[ObjectDetectionEngineInput],
    ) -> ObjectDetectionEngineOutput | List[ObjectDetectionEngineOutput]:
        if not self._initialized:
            _log.debug("Initializing %s for call", type(self).__name__)
            self.initialize()

        if isinstance(input_data, list):
            return self.predict_batch(input_data)
        return self.predict(input_data)
