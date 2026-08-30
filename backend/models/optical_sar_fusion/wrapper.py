"""Optical+SAR cross-modal fusion baseline."""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from backend.registry.base import BaseModelWrapper
from backend.registry.contracts import ModelInput, ModelOutput, ModelStatus, TaskType


class OpticalSARFusionModel(BaseModelWrapper):
    model_id = "OPTICAL_SAR_FUSION"
    version = "v0.1-baseline"

    LAND_COVER_HINTS = ["water", "vegetation", "built-up", "bare soil", "mixed urban"]

    def health(self) -> bool:
        return True

    def infer(self, inputs: ModelInput) -> ModelOutput:
        start = time.perf_counter()
        if len(inputs.image_bytes) < 2 and len(inputs.image_paths) < 2:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=TaskType.CROSS_MODAL_FUSION,
                status=ModelStatus.ERROR,
                error="Cross-modal fusion requires optical + SAR image pair.",
            )

        optical = self._load(inputs, 0)
        sar = self._load(inputs, 1)
        opt_arr = np.array(optical.convert("RGB"), dtype=np.float32)
        sar_arr = np.array(sar.convert("L"), dtype=np.float32)

        opt_mean = opt_arr.mean(axis=(0, 1))
        sar_mean = sar_arr.mean()
        green_dom = opt_mean[1] > opt_mean[0] and opt_mean[1] > opt_mean[2]
        bright_sar = sar_mean > 80

        if green_dom and not bright_sar:
            label = "vegetation"
            confidence = 0.78
        elif bright_sar and opt_mean.mean() > 100:
            label = "built-up"
            confidence = 0.74
        elif sar_mean < 40 and opt_mean[2] > opt_mean[0]:
            label = "water"
            confidence = 0.76
        else:
            label = "mixed urban"
            confidence = 0.62

        question = inputs.question or inputs.text_prompt or "Describe this area."
        answer = (
            f"Fused optical+SAR analysis suggests predominant land cover: {label}. "
            f"Query context: {question}"
        )

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.CROSS_MODAL_FUSION,
            answer=answer,
            confidence=confidence,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=ModelStatus.BASELINE,
            raw={
                "baseline_note": "Feature-statistics fusion baseline, not BigEarthNet fine-tuned.",
                "predicted_class": label,
                "optical_mean_rgb": opt_mean.tolist(),
                "sar_mean": float(sar_mean),
            },
        )

    def _load(self, inputs: ModelInput, idx: int) -> Image.Image:
        if inputs.image_bytes:
            return Image.open(io.BytesIO(inputs.image_bytes[idx])).convert("RGB")
        return Image.open(inputs.image_paths[idx]).convert("RGB")
