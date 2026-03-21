
import logging
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Set

from pydantic import BaseModel, Field


from docling.models.inference_engines.object_detection.base import (
    ObjectDetectionEngineType,
)

if TYPE_CHECKING:
    from docling.datamodel.object_detection_engine_options import (
        BaseObjectDetectionEngineOptions,
    )

_log = logging.getLogger(__name__)


# =============================================================================
# ENGINE-SPECIFIC MODEL CONFIGURATION
# =============================================================================





class EngineModelConfig(BaseModel):
    """Engine-specific model configuration.

    Allows overriding model settings for specific engines.
    For example, MLX might use a different repo_id than Transformers.
    """

    repo_id: Optional[str] = Field(
        default=None, description="Override model repository ID for this engine"
    )

    revision: Optional[str] = Field(
        default=None, description="Override model revision for this engine"
    )

    torch_dtype: Optional[str] = Field(
        default=None,
        description="Override torch dtype for this engine (e.g., 'bfloat16')",
    )

    extra_config: Dict[str, Any] = Field(
        default_factory=dict, description="Additional engine-specific configuration"
    )

    def merge_with(
        self, base_repo_id: str, base_revision: str = "main"
    ) -> "EngineModelConfig":
        """Merge with base configuration.

        Args:
            base_repo_id: Base repository ID
            base_revision: Base revision

        Returns:
            Merged configuration with overrides applied
        """
        return EngineModelConfig(
            repo_id=self.repo_id or base_repo_id,
            revision=self.revision or base_revision,
            torch_dtype=self.torch_dtype,
            extra_config=self.extra_config,
        )






# =============================================================================
# OBJECT DETECTION MODEL SPECIFICATION
# =============================================================================


class ObjectDetectionModelSpec(BaseModel):
    """Specification for an object detection model.

    Simpler than VlmModelSpec - no prompts, no preprocessing params.
    Preprocessing comes from HuggingFace preprocessor configs.
    Model files are assumed to be at the root of the HuggingFace repo.
    """

    name: str = Field(description="Human-readable model name")

    repo_id: str = Field(description="Default HuggingFace repository ID")

    revision: str = Field(default="main", description="Default model revision")

    engine_overrides: Dict["ObjectDetectionEngineType", EngineModelConfig] = Field(
        default_factory=dict,
        description="Engine-specific configuration overrides",
    )

    def get_engine_config(
        self, engine_type: "ObjectDetectionEngineType"
    ) -> EngineModelConfig:
        """Get EngineModelConfig for a specific object-detection engine.

        Args:
            engine_type: The engine type being requested

        Returns:
            EngineModelConfig populated with repo/revision and engine overrides
        """
        override = self.engine_overrides.get(engine_type)
        if override is not None:
            return override.merge_with(self.repo_id, self.revision)
        return EngineModelConfig(repo_id=self.repo_id, revision=self.revision)

    def get_repo_id(self, engine_type: "ObjectDetectionEngineType") -> str:
        """Get repository ID for specific engine.

        Args:
            engine_type: The engine type

        Returns:
            Repository ID (with engine override if applicable)
        """
        override = self.engine_overrides.get(engine_type)
        if override and override.repo_id:
            return override.repo_id
        return self.repo_id

    def get_revision(self, engine_type: "ObjectDetectionEngineType") -> str:
        """Get revision for specific engine.

        Args:
            engine_type: The engine type

        Returns:
            Model revision (with engine override if applicable)
        """
        override = self.engine_overrides.get(engine_type)
        if override and override.revision:
            return override.revision
        return self.revision


# =============================================================================
# STAGE PRESET SYSTEM
# =============================================================================






class ObjectDetectionStagePreset(BaseModel):
    """Preset definition for object detection-powered stages."""

    preset_id: str = Field(description="Preset identifier")
    name: str = Field(description="Human-readable preset name")
    description: str = Field(description="Description of this preset")
    model_spec: ObjectDetectionModelSpec = Field(
        description="Object detection model specification"
    )
    default_engine_type: ObjectDetectionEngineType = Field(
        default=ObjectDetectionEngineType.ONNXRUNTIME,
        description="Default inference engine to use",
    )
    stage_options: Dict[str, Any] = Field(
        default_factory=dict, description="Additional stage-specific defaults"
    )


class ObjectDetectionStagePresetMixin:
    """Mixin to enable preset loading for object detection stages."""

    _presets: ClassVar[Dict[str, ObjectDetectionStagePreset]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._presets = {}

    @classmethod
    def register_preset(cls, preset: ObjectDetectionStagePreset) -> None:
        if preset.preset_id not in cls._presets:
            cls._presets[preset.preset_id] = preset
        else:
            _log.error(
                f"Preset '{preset.preset_id}' already registered for {cls.__name__}"
            )

    @classmethod
    def get_preset(cls, preset_id: str) -> ObjectDetectionStagePreset:
        if preset_id not in cls._presets:
            raise KeyError(
                f"Preset '{preset_id}' not found for {cls.__name__}. "
                f"Available presets: {list(cls._presets.keys())}"
            )
        return cls._presets[preset_id]

    @classmethod
    def list_presets(cls) -> List[ObjectDetectionStagePreset]:
        return list(cls._presets.values())

    @classmethod
    def list_preset_ids(cls) -> List[str]:
        return list(cls._presets.keys())

    @classmethod
    def get_preset_info(cls) -> List[Dict[str, str]]:
        return [
            {
                "preset_id": p.preset_id,
                "name": p.name,
                "description": p.description,
                "model": p.model_spec.name,
                "default_engine": p.default_engine_type.value,
            }
            for p in cls._presets.values()
        ]

    @classmethod
    def from_preset(
        cls,
        preset_id: str,
        engine_options: Optional["BaseObjectDetectionEngineOptions"] = None,
        **overrides: Any,
    ):
        from docling.datamodel.object_detection_engine_options import (
            OnnxRuntimeObjectDetectionEngineOptions,
            TransformersObjectDetectionEngineOptions,
        )

        preset = cls.get_preset(preset_id)

        if engine_options is None:
            if preset.default_engine_type == ObjectDetectionEngineType.ONNXRUNTIME:
                engine_options = OnnxRuntimeObjectDetectionEngineOptions()
            elif preset.default_engine_type == ObjectDetectionEngineType.TRANSFORMERS:
                engine_options = TransformersObjectDetectionEngineOptions()
            else:
                raise ValueError(
                    f"Unsupported engine type {preset.default_engine_type} for presets"
                )

        instance = cls(  # type: ignore[call-arg]
            model_spec=preset.model_spec,
            engine_options=engine_options,
            **preset.stage_options,
        )

        for key, value in overrides.items():
            setattr(instance, key, value)

        return instance


# =============================================================================
# PRESET DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# SHARED MODEL SPECS (for reuse across multiple stages)
# -----------------------------------------------------------------------------






# -----------------------------------------------------------------------------
# OBJECT DETECTION PRESETS
# -----------------------------------------------------------------------------

OBJECT_DETECTION_LAYOUT_HERON = ObjectDetectionStagePreset(
    preset_id="layout_heron_default",
    name="Layout Heron",
    description="RT-DETR layout-heron model (ResNet50)",
    model_spec=ObjectDetectionModelSpec(
        name="layout_heron",
        repo_id="docling-project/docling-layout-heron",
        revision="main",
        engine_overrides={
            ObjectDetectionEngineType.ONNXRUNTIME: EngineModelConfig(
                repo_id="docling-project/docling-layout-heron-onnx",
                extra_config={"model_filename": "model.onnx"},
            )
        },
    ),
    default_engine_type=ObjectDetectionEngineType.TRANSFORMERS,
)


