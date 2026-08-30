"""Change-based VQA — reasons over CHANGE_DETECTION output."""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from backend.registry.base import BaseModelWrapper
from backend.registry.contracts import ModelInput, ModelOutput, ModelStatus, TaskType


class ChangeVQAModel(BaseModelWrapper):
    model_id = "CHANGE_VQA"
    version = "v0.1-baseline"

    def health(self) -> bool:
        return True

    def infer(self, inputs: ModelInput) -> ModelOutput:
        start = time.perf_counter()
        question = (inputs.question or inputs.text_prompt or "What changed?").lower()
        change_mask = inputs.change_mask or inputs.params.get("change_mask_bytes")

        if change_mask is None and len(inputs.image_bytes) >= 2:
            from backend.models.change_detection.wrapper import ChangeDetectionModel

            cd = ChangeDetectionModel()
            cd_out = cd.infer(inputs)
            change_mask = cd_out.change_mask_bytes
            change_pct = cd_out.raw.get("change_percent", 0)
            boxes = cd_out.boxes
        elif change_mask:
            mask_arr = np.array(Image.open(io.BytesIO(change_mask)).convert("L"))
            change_pct = float((mask_arr > 0).sum()) / mask_arr.size * 100
            boxes = []
        else:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=TaskType.CHANGE_BASED_VQA,
                status=ModelStatus.ERROR,
                error="Change mask or bi-temporal images required.",
            )

        answer, confidence = self._answer_question(question, change_pct, boxes)

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.CHANGE_BASED_VQA,
            answer=answer,
            confidence=confidence,
            boxes=boxes,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=ModelStatus.BASELINE,
            raw={"baseline_note": "Rule-based change VQA over detection mask.", "change_percent": change_pct},
        )

    def _answer_question(self, question: str, change_pct: float, boxes: list) -> tuple[str, float]:
        if any(k in question for k in ["increase", "more", "expanded", "growth", "built"]):
            if change_pct > 5:
                return (
                    f"Yes — built-up or surface change increased, covering ~{change_pct:.1f}% of the area "
                    f"across {len(boxes)} detected regions.",
                    min(0.92, 0.6 + change_pct / 200),
                )
            return (
                f"No significant increase detected; change covers only ~{change_pct:.1f}%.",
                0.75,
            )
        if any(k in question for k in ["decrease", "loss", "reduced", "less"]):
            if change_pct > 5:
                return (
                    f"Change detected (~{change_pct:.1f}% area) — may indicate vegetation or surface loss.",
                    0.7,
                )
            return "No significant decrease detected in the change mask.", 0.72
        return (
            f"Change analysis: ~{change_pct:.1f}% of pixels changed across {len(boxes)} regions.",
            min(0.88, 0.55 + change_pct / 150),
        )
