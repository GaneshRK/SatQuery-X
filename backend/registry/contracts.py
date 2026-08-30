"""Common model input/output contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    VISUAL_QUESTION_ANSWERING = "visual_question_answering"
    IMAGE_CAPTIONING = "image_captioning"
    TEXT_GUIDED_GROUNDING = "text_guided_grounding"
    BI_TEMPORAL_CHANGE_MAP = "bi_temporal_change_map"
    CHANGE_BASED_VQA = "change_based_vqa"
    CROSS_MODAL_FUSION = "cross_modal_fusion_analysis"


class ModelStatus(str, Enum):
    READY = "ready"
    BASELINE = "baseline"
    NOT_IMPLEMENTED = "not_implemented"
    ERROR = "error"


@dataclass
class ModelInput:
    model_id: str
    image_paths: list[str] = field(default_factory=list)
    image_bytes: list[bytes] = field(default_factory=list)
    question: str | None = None
    text_prompt: str | None = None
    change_mask: bytes | None = None
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str | None = None
    confidence: float | None = None


@dataclass
class ModelOutput:
    model_id: str
    version: str
    task: TaskType
    answer: str | None = None
    caption: str | None = None
    confidence: float = 0.0
    boxes: list[BoundingBox] = field(default_factory=list)
    change_mask_bytes: bytes | None = None
    overlay_bytes: bytes | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    status: ModelStatus = ModelStatus.READY
    error: str | None = None
