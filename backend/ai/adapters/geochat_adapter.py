"""GeoChat / RS-VLM Specialist Adapter per §11, §12, §37.

Provides remote-sensing conversational understanding, Visual Question Answering (VQA),
and land-cover scene captioning using specialized RS-VLM architectures (GeoChat / BLIP-VQA).
"""

from __future__ import annotations

import io
import os
import time
from typing import Any

import numpy as np
from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager
from apps.models_ai.rs_vqa.wrapper import RSVQAModel
from apps.models_ai.rs_caption.wrapper import RSCaptionModel
from .base import VQAAdapter, CaptionAdapter


class GeoChatVQAAdapter(VQAAdapter, CaptionAdapter):
    """
    Specialist Vision-Language Model adapter representing GeoChat / RS-VLM.
    Serves both VQA and Scene Captioning tasks with spectral grounding and
    graceful low-hardware CPU/GPU execution.
    """
    model_id = "GeoChat"
    version = "2.1-rs-vlm"
    task = "visual_question_answering"
    gpu_requirement = "OPTIONAL"

    def __init__(self) -> None:
        super().__init__()
        self._vqa_backend = RSVQAModel()
        self._caption_backend = RSCaptionModel()
        self.model_name = os.getenv("GEOCHAT_MODEL_NAME", "GeoChat-7B-LoRA / RS-VLM")

    def answer(self, image: Any, question: str, **kwargs) -> ModelOutput:
        """Executes VQA query against the satellite image."""
        start_t = time.perf_counter()
        pil_img = self._to_pil(image)
        if pil_img is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="GeoChatAdapter: No valid image provided for VQA inference.",
                latency_ms=int((time.perf_counter() - start_t) * 1000),
            )

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[raw_bytes],
            question=question,
            params=kwargs,
        )

        out = self._vqa_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        if out.raw:
            out.raw["specialist_adapter"] = "GeoChatVQAAdapter"
            out.raw["vlm_architecture"] = self.model_name
        return out

    def caption(self, image: Any, **kwargs) -> ModelOutput:
        """Generates comprehensive remote-sensing scene caption and land-cover description."""
        start_t = time.perf_counter()
        pil_img = self._to_pil(image)
        if pil_img is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task="image_captioning",
                status="error",
                error="GeoChatAdapter: No valid image provided for captioning.",
                latency_ms=int((time.perf_counter() - start_t) * 1000),
            )

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[raw_bytes],
            params=kwargs,
        )

        out = self._caption_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        if out.raw:
            out.raw["specialist_adapter"] = "GeoChatCaptionAdapter"
            out.raw["vlm_architecture"] = self.model_name
        return out
