"""RS Grounding — Text-guided bounding box detection baseline for remote sensing."""

from __future__ import annotations

import io
import time
from typing import Any

import numpy as np
from PIL import Image

from backend.registry.base import BaseModelWrapper
from backend.registry.contracts import BoundingBox, ModelInput, ModelOutput, ModelStatus, TaskType


class RSGroundingModel(BaseModelWrapper):
    model_id = "RS_GROUNDING"
    version = "v0.1-baseline"

    def health(self) -> bool:
        return True

    def infer(self, inputs: ModelInput) -> ModelOutput:
        start = time.perf_counter()
        if not inputs.image_bytes and not inputs.image_paths:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=TaskType.TEXT_GUIDED_GROUNDING,
                status=ModelStatus.ERROR,
                error="No image provided for grounding.",
            )

        image = self._load_image(inputs)
        prompt = (inputs.text_prompt or inputs.question or "").lower()

        boxes = self._detect_proposals(image, prompt)
        confidence = 0.78 if boxes else 0.40

        answer = (
            f"Grounded {len(boxes)} candidate region(s) matching '{prompt}'."
            if boxes
            else f"No distinct regions matching '{prompt}' detected above confidence threshold."
        )

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.TEXT_GUIDED_GROUNDING,
            answer=answer,
            confidence=confidence,
            boxes=boxes,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            status=ModelStatus.BASELINE,
            raw={
                "baseline_note": "Spectral saliency + contour proposal grounding baseline.",
                "target_prompt": prompt,
                "detected_count": len(boxes),
            },
        )

    def _load_image(self, inputs: ModelInput) -> Image.Image:
        if inputs.image_bytes:
            return Image.open(io.BytesIO(inputs.image_bytes[0])).convert("RGB")
        return Image.open(inputs.image_paths[0]).convert("RGB")

    def _detect_proposals(self, image: Image.Image, prompt: str) -> list[BoundingBox]:
        arr = np.array(image, dtype=np.float32)
        h, w, _ = arr.shape
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        mask = np.zeros((h, w), dtype=bool)

        if any(k in prompt for k in ["vegetation", "forest", "tree", "green", "agriculture", "crop"]):
            # Excess Green index (2G - R - B)
            exg = 2.0 * g - r - b
            mask = exg > max(30.0, float(np.mean(exg)))
            label = "vegetation"
        elif any(k in prompt for k in ["water", "river", "lake", "ocean", "pond"]):
            # Water: blue dominant or low overall reflectance
            mask = ((b > r) & (b > g)) | ((r + g + b) < 90)
            label = "water"
        elif any(k in prompt for k in ["built", "building", "urban", "roof", "structure", "house"]):
            # High brightness or red/urban spectral dominance
            brightness = (r + g + b) / 3.0
            mask = (brightness > 120) | (r > g + 20)
            label = "building"
        elif any(k in prompt for k in ["road", "highway", "runway", "track"]):
            brightness = (r + g + b) / 3.0
            mask = (brightness > 90) & (np.abs(r - g) < 25) & (np.abs(g - b) < 25)
            label = "road"
        else:
            # Saliency / gradient
            dx = np.abs(np.diff(arr, axis=1, prepend=arr[:, :1, :])).sum(axis=2)
            dy = np.abs(np.diff(arr, axis=0, prepend=arr[:1, :, :])).sum(axis=2)
            grad = dx + dy
            mask = grad > np.mean(grad)
            label = prompt or "target"

        return self._connected_components_to_boxes(mask, label, w, h)

    def _connected_components_to_boxes(
        self, mask: np.ndarray, label: str, img_w: int, img_h: int
    ) -> list[BoundingBox]:
        boxes: list[BoundingBox] = []
        try:
            from scipy import ndimage

            labeled, num_features = ndimage.label(mask)
            for i in range(1, min(num_features + 1, 20)):
                ys, xs = np.where(labeled == i)
                if len(xs) < 15:
                    continue
                x1, y1 = float(xs.min()), float(ys.min())
                x2, y2 = float(xs.max()), float(ys.max())
                if (x2 - x1) < 2 or (y2 - y1) < 2:
                    continue
                boxes.append(
                    BoundingBox(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        label=label,
                        confidence=round(float(min(0.92, 0.68 + len(xs) / (img_w * img_h) * 5)), 2),
                    )
                )
        except Exception:
            ys, xs = np.where(mask)
            if len(xs) > 10:
                boxes.append(
                    BoundingBox(
                        x1=float(xs.min()),
                        y1=float(ys.min()),
                        x2=float(xs.max()),
                        y2=float(ys.max()),
                        label=label,
                        confidence=0.72,
                    )
                )

        boxes.sort(key=lambda b: b.confidence, reverse=True)
        return boxes[:8]
