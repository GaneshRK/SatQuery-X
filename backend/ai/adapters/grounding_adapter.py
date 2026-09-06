"""Grounding DINO / SAM Specialist Adapter per §13, §37.

Implements text-guided visual grounding and region segmentation:
Text Prompt + Satellite Image → Grounding → Bounding Boxes + Segmentation Masks
"""

from __future__ import annotations

import io
import os
import time
from typing import Any

from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager
from apps.models_ai.rs_grounding.wrapper import RSGroundingModel
from .base import GroundingAdapter as BaseGroundingAdapter


class GroundingDINOAdapter(BaseGroundingAdapter):
    """
    Specialist adapter encapsulating text-guided visual grounding (Grounding DINO / SAM).
    Produces oriented bounding boxes, detection clusters, and spatial coordinates.
    """
    model_id = "GroundingDINO/SAM"
    version = "2.1-grounding"
    task = "text_guided_grounding"
    gpu_requirement = "OPTIONAL"

    def __init__(self) -> None:
        super().__init__()
        self._grounding_backend = RSGroundingModel()
        self.model_name = os.getenv("GROUNDING_MODEL_NAME", "Grounding-DINO-Tiny + SAM")

    def ground(self, image: Any, text_prompt: str, **kwargs) -> ModelOutput:
        """Executes spatial localization for the requested text target."""
        start_t = time.perf_counter()
        img = self._to_pil(image)
        if img is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="GroundingDINOAdapter: No valid image provided for grounding.",
                latency_ms=int((time.perf_counter() - start_t) * 1000),
            )

        buf = io.BytesIO()
        img.save(buf, format="PNG")

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[buf.getvalue()],
            text_prompt=text_prompt,
            params=kwargs,
        )

        out = self._grounding_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        if out.raw:
            out.raw["specialist_adapter"] = "GroundingDINOAdapter"
            out.raw["grounding_model"] = self.model_name
        return out
