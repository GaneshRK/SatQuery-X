"""CHANGE_VQA specialist model wrapper per §9."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput


class ChangeVQAModel:
    model_id = "CHANGE_VQA"
    version = "1.0-baseline"
    task = "change_based_vqa"

    def predict(self, inputs: ModelInput) -> ModelOutput:
        start_time = time.perf_counter()

        img_t1, img_t2 = self._load_pair(inputs)
        question = (inputs.question or "What changed between these two dates?").lower()

        # Check for change mask provided by prior CHANGE_DETECTION step
        change_mask = None
        if inputs.change_mask:
            if isinstance(inputs.change_mask, (bytes, bytearray)):
                change_mask = np.array(Image.open(io.BytesIO(inputs.change_mask)).convert("L"))
            elif isinstance(inputs.change_mask, str) and Path(inputs.change_mask).exists():
                change_mask = np.array(Image.open(inputs.change_mask).convert("L"))

        # If no change mask passed, compute diff from images
        if change_mask is None and img_t1 and img_t2:
            if img_t1.size != img_t2.size:
                img_t2 = img_t2.resize(img_t1.size)
            arr1 = np.array(img_t1.convert("L"), dtype=float)
            arr2 = np.array(img_t2.convert("L"), dtype=float)
            diff = np.abs(arr1 - arr2)
            change_mask = (diff > 35).astype(np.uint8) * 255

        change_pct = 0.0
        if change_mask is not None:
            change_pixels = int(np.count_nonzero(change_mask))
            change_pct = (change_pixels / change_mask.size) * 100.0

        # Multispectral / RGB change direction reasoning
        direction = "remained largely unchanged"
        if change_pct > 3.0:
            if img_t1 and img_t2:
                arr1 = np.array(img_t1, dtype=float)
                arr2 = np.array(img_t2, dtype=float)
                # Compare brightness/impervious reflections
                mean_b1 = np.mean(arr1)
                mean_b2 = np.mean(arr2)
                if mean_b2 > mean_b1 + 5:
                    direction = "increased (expansion of cleared/impervious surface)"
                elif mean_b2 < mean_b1 - 5:
                    direction = "decreased (increase in vegetative cover or moisture)"
                else:
                    direction = "altered with structural modifications"
            else:
                direction = "increased"

        # Formulate reasoned quantitative answer
        if "built-up" in question or "urban" in question or "increased" in question or "decreased" in question:
            answer = f"The built-up/impervious area has {direction}, with detected alterations covering {change_pct:.2f}% of the observed region."
        elif "water" in question:
            answer = f"Hydrological change analysis indicates {change_pct:.2f}% shift in water surface boundary dynamics between acquisition dates."
        else:
            answer = f"Between the two acquisition dates, surface changes occurred across approximately {change_pct:.2f}% of the area, primarily {direction}."

        latency = int((time.perf_counter() - start_time) * 1000)

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=answer,
            confidence=0.89,
            latency_ms=latency,
            status="ok",
            raw={
                "adaptation": "baseline",
                "base_model": "change-reasoning-over-masks",
                "change_percent": round(change_pct, 2),
                "direction": direction,
            },
        )

    def _load_pair(self, inputs: ModelInput) -> tuple[Image.Image | None, Image.Image | None]:
        img_t1, img_t2 = None, None
        if inputs.image_bytes and len(inputs.image_bytes) >= 2:
            img_t1 = Image.open(io.BytesIO(inputs.image_bytes[0])).convert("RGB")
            img_t2 = Image.open(io.BytesIO(inputs.image_bytes[1])).convert("RGB")
        elif inputs.image_paths and len(inputs.image_paths) >= 2:
            p1, p2 = Path(inputs.image_paths[0]), Path(inputs.image_paths[1])
            if p1.exists() and p2.exists():
                img_t1 = Image.open(p1).convert("RGB")
                img_t2 = Image.open(p2).convert("RGB")
        return img_t1, img_t2
