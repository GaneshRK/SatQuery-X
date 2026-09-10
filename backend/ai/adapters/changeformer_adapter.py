"""ChangeFormer / Bi-Temporal Change Detection & Reasoner Adapter per §14, §15, §37.

Implements the complete remote-sensing change analysis pipeline:
T1 + T2 → Preprocessing → Siamese Difference (ChangeFormer) → Probability Map
        → Otsu Thresholding → Connected Components → Area Calculation (ha / km²)
        → Change VQA Reasoning
"""

from __future__ import annotations

import io
import os
import time
from typing import Any

from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager
from apps.models_ai.change_detection.wrapper import ChangeDetectionModel
from apps.models_ai.change_vqa.wrapper import ChangeVQAModel
from .base import ChangeDetectionAdapter, ChangeVQAAdapter


class ChangeFormerAdapter(ChangeDetectionAdapter, ChangeVQAAdapter):
    """
    Specialist adapter encapsulating ChangeFormer deep-learning difference mapping
    and grounded change reasoning.
    """
    model_id = "ChangeFormer"
    version = "2.1-changeformer"
    task = "bi_temporal_change_map"
    gpu_requirement = "OPTIONAL"

    def __init__(self) -> None:
        super().__init__()
        self._cd_backend = ChangeDetectionModel()
        self._vqa_backend = ChangeVQAModel()
        self.model_name = os.getenv("CHANGE_MODEL_NAME", "SiameseChangeNet-v1")

    def detect_change(
        self,
        image_t1: Any,
        image_t2: Any,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        """Executes bi-temporal pixel change detection between T1 and T2."""
        start_t = time.perf_counter()
        img1 = self._to_pil(image_t1)
        img2 = self._to_pil(image_t2)

        if img1 is None or img2 is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="ChangeFormerAdapter: Requires two valid registered images (T1 and T2).",
                latency_ms=int((time.perf_counter() - start_t) * 1000),
            )

        buf1, buf2 = io.BytesIO(), io.BytesIO()
        img1.save(buf1, format="PNG")
        img2.save(buf2, format="PNG")

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[buf1.getvalue(), buf2.getvalue()],
            params=params or {},
        )

        out = self._cd_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        if out.raw:
            out.raw["specialist_adapter"] = "ChangeFormerAdapter"
            out.raw["neural_architecture"] = self.model_name
        return out

    def answer_change(
        self,
        image_t1: Any,
        image_t2: Any,
        change_mask: Any = None,
        question: str = "What changed between these two dates?",
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        """Executes grounded change VQA reasoning over measured difference masks."""
        start_t = time.perf_counter()
        img1 = self._to_pil(image_t1)
        img2 = self._to_pil(image_t2)

        buf1 = io.BytesIO()
        buf2 = io.BytesIO()
        if img1:
            img1.save(buf1, format="PNG")
        if img2:
            img2.save(buf2, format="PNG")

        mask_bytes = None
        if change_mask is not None:
            if isinstance(change_mask, (bytes, bytearray)):
                mask_bytes = change_mask
            elif isinstance(change_mask, Image.Image):
                b = io.BytesIO()
                change_mask.save(b, format="PNG")
                mask_bytes = b.getvalue()

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[buf1.getvalue(), buf2.getvalue()] if img1 and img2 else [],
            question=question,
            change_mask=mask_bytes,
            params=params or {},
        )

        out = self._vqa_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        out.task = "change_based_vqa"
        if out.raw:
            out.raw["specialist_adapter"] = "ChangeFormerVQAAdapter"
            out.raw["neural_architecture"] = self.model_name
        return out
