"""Base Model Adapter definitions for SatQuery-X Layer 4 AI Specialist subsystem per §37.

Defines standardized, typed interfaces for all remote-sensing specialist models:
- VQAAdapter (GeoChat / RSVQA)
- CaptionAdapter (RS Captioning)
- GroundingAdapter (Grounding DINO / SAM)
- ChangeDetectionAdapter (ChangeFormer)
- ChangeVQAAdapter (RS Change-VQA)
- OpticalSARFusionAdapter (Cross-Modal Dual Encoders)
- RemoteCLIPAdapter (Auxiliary Semantic Representation & Scoring)
- SLMPlannerAdapter (Qwen SLM Router)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import numpy as np
from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager


class BaseModelAdapter(ABC):
    """Abstract base class for all specialist AI model adapters."""
    model_id: str = "BASE_MODEL"
    version: str = "2.0.0"
    task: str = "general"
    device: str = "cpu"
    gpu_requirement: str = "OPTIONAL"

    def __init__(self) -> None:
        self.device = model_manager.device
        self.dtype = model_manager.dtype

    def health(self) -> dict[str, Any]:
        """Returns runtime health, device status, and memory metrics."""
        return {
            "model_id": self.model_id,
            "version": self.version,
            "task": self.task,
            "device": self.device,
            "dtype": self.dtype,
            "gpu_requirement": self.gpu_requirement,
            "status": "healthy",
        }

    def unload(self) -> bool:
        """Unloads underlying model weights from cache."""
        return model_manager.unload_model(self.model_id)

    def _to_pil(self, img_input: Any) -> Image.Image | None:
        """Helper to convert various image representations to PIL Image."""
        if img_input is None:
            return None
        if isinstance(img_input, Image.Image):
            return img_input.convert("RGB")
        if isinstance(img_input, (bytes, bytearray)):
            import io
            return Image.open(io.BytesIO(img_input)).convert("RGB")
        if isinstance(img_input, np.ndarray):
            if img_input.dtype != np.uint8:
                if img_input.max() <= 1.0:
                    arr = (img_input * 255.0).astype(np.uint8)
                else:
                    arr = np.clip(img_input, 0, 255).astype(np.uint8)
            else:
                arr = img_input
            if len(arr.shape) == 2:
                return Image.fromarray(arr, mode="L").convert("RGB")
            elif len(arr.shape) == 3:
                return Image.fromarray(arr[:, :, :3], mode="RGB")
        if isinstance(img_input, str):
            from pathlib import Path
            p = Path(img_input)
            if p.exists():
                return Image.open(p).convert("RGB")
        return None


class VQAAdapter(BaseModelAdapter):
    """Specialist adapter for remote-sensing Visual Question Answering (VQA)."""
    task = "visual_question_answering"

    @abstractmethod
    def answer(self, image: Any, question: str, **kwargs) -> ModelOutput:
        raise NotImplementedError


class CaptionAdapter(BaseModelAdapter):
    """Specialist adapter for remote-sensing scene captioning and description."""
    task = "image_captioning"

    @abstractmethod
    def caption(self, image: Any, **kwargs) -> ModelOutput:
        raise NotImplementedError


class GroundingAdapter(BaseModelAdapter):
    """Specialist adapter for text-guided visual grounding and localization."""
    task = "text_guided_grounding"

    @abstractmethod
    def ground(self, image: Any, text_prompt: str, **kwargs) -> ModelOutput:
        raise NotImplementedError


class ChangeDetectionAdapter(BaseModelAdapter):
    """Specialist adapter for bi-temporal pixel-level change detection."""
    task = "bi_temporal_change_map"

    @abstractmethod
    def detect_change(
        self,
        image_t1: Any,
        image_t2: Any,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        raise NotImplementedError


class ChangeVQAAdapter(BaseModelAdapter):
    """Specialist adapter for temporal semantic reasoning over measured change masks."""
    task = "change_based_vqa"

    @abstractmethod
    def answer_change(
        self,
        image_t1: Any,
        image_t2: Any,
        change_mask: Any = None,
        question: str = "What changed between these two dates?",
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        raise NotImplementedError


class OpticalSARFusionAdapter(BaseModelAdapter):
    """Specialist adapter for dual-encoder optical and SAR cross-modal fusion."""
    task = "cross_modal_fusion_analysis"

    @abstractmethod
    def fuse(
        self,
        optical_image: Any,
        sar_image: Any,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        raise NotImplementedError


class RemoteCLIPAdapter(BaseModelAdapter):
    """Specialist adapter for auxiliary cross-modal semantic retrieval and classification."""
    task = "semantic_representation_and_retrieval"

    @abstractmethod
    def score_similarity(self, image: Any, text_queries: list[str], **kwargs) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def classify_region(self, image: Any, candidate_classes: list[str], **kwargs) -> list[dict[str, Any]]:
        raise NotImplementedError


class SLMPlannerAdapter(BaseModelAdapter):
    """Specialist adapter for Small Language Model query routing and structured planning."""
    task = "query_planning_and_intent_routing"

    @abstractmethod
    def plan_query(self, query_text: str, session_context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError
