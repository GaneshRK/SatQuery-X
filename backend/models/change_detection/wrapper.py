"""Bi-temporal change detection baseline (pixel-diff + connected regions)."""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image, ImageDraw

from backend.registry.base import BaseModelWrapper
from backend.registry.contracts import BoundingBox, ModelInput, ModelOutput, ModelStatus, TaskType


class ChangeDetectionModel(BaseModelWrapper):
    model_id = "CHANGE_DETECTION"
    version = "v0.1-baseline"

    def health(self) -> bool:
        return True

    def infer(self, inputs: ModelInput) -> ModelOutput:
        start = time.perf_counter()
        if len(inputs.image_bytes) < 2 and len(inputs.image_paths) < 2:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=TaskType.BI_TEMPORAL_CHANGE_MAP,
                status=ModelStatus.ERROR,
                error="Bi-temporal change detection requires two images.",
            )

        img_t1 = self._load(inputs, 0)
        img_t2 = self._load(inputs, 1)
        if img_t1.size != img_t2.size:
            img_t2 = img_t2.resize(img_t1.size)

        arr1 = np.array(img_t1.convert("L"), dtype=np.float32)
        arr2 = np.array(img_t2.convert("L"), dtype=np.float32)
        diff = np.abs(arr1 - arr2)

        # Adaptive change thresholding
        if diff.max() > 15:
            # Otsu or mean of active diffs
            active_diffs = diff[diff > 10]
            threshold = float(np.percentile(active_diffs, 30)) if len(active_diffs) > 0 else 25.0
            mask = (diff >= threshold).astype(np.uint8) * 255
        else:
            threshold = 30.0
            mask = np.zeros(diff.shape, dtype=np.uint8)

        boxes = self._extract_boxes(mask)
        overlay = self._render_overlay(img_t2, mask, boxes)

        buf = io.BytesIO()
        Image.fromarray(mask).save(buf, format="PNG")
        mask_bytes = buf.getvalue()

        change_pct = float(mask.sum() / 255) / mask.size * 100

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.BI_TEMPORAL_CHANGE_MAP,
            answer=f"Detected change covering approximately {change_pct:.1f}% of the image area.",
            confidence=round(min(0.95, 0.55 + change_pct / 100), 3),
            boxes=boxes,
            change_mask_bytes=mask_bytes,
            overlay_bytes=overlay,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            status=ModelStatus.BASELINE,
            raw={
                "baseline_note": "Diff-based baseline, not Siamese fine-tuned.",
                "threshold": threshold,
                "change_percent": round(change_pct, 2),
            },
        )

    def _load(self, inputs: ModelInput, idx: int) -> Image.Image:
        if inputs.image_bytes:
            return Image.open(io.BytesIO(inputs.image_bytes[idx])).convert("RGB")
        return Image.open(inputs.image_paths[idx]).convert("RGB")

    def _extract_boxes(self, mask: np.ndarray) -> list[BoundingBox]:
        try:
            from scipy import ndimage

            labeled, num = ndimage.label(mask > 0)
            boxes: list[BoundingBox] = []
            for i in range(1, num + 1):
                ys, xs = np.where(labeled == i)
                if len(xs) < 10:
                    continue
                boxes.append(
                    BoundingBox(
                        x1=float(xs.min()),
                        y1=float(ys.min()),
                        x2=float(xs.max()),
                        y2=float(ys.max()),
                        label="change",
                        confidence=0.75,
                    )
                )
            return boxes[:10]
        except Exception:
            ys, xs = np.where(mask > 0)
            if len(xs) > 10:
                return [
                    BoundingBox(
                        x1=float(xs.min()),
                        y1=float(ys.min()),
                        x2=float(xs.max()),
                        y2=float(ys.max()),
                        label="change",
                        confidence=0.70,
                    )
                ]
            return []

    def _render_overlay(
        self, base: Image.Image, mask: np.ndarray, boxes: list[BoundingBox]
    ) -> bytes:
        overlay = base.copy().convert("RGBA")
        red_layer = Image.new("RGBA", base.size, (255, 0, 0, 0))
        red_pixels = np.array(red_layer)
        red_pixels[mask > 0] = [255, 0, 0, 120]
        red_overlay = Image.fromarray(red_pixels, "RGBA")
        combined = Image.alpha_composite(overlay, red_overlay)

        draw = ImageDraw.Draw(combined)
        for box in boxes:
            draw.rectangle([box.x1, box.y1, box.x2, box.y2], outline=(255, 255, 0, 255), width=2)

        buf = io.BytesIO()
        combined.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
