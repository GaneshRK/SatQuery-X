"""CHANGE_DETECTION specialist model wrapper per §9."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from apps.agent.contracts import ModelInput, ModelOutput


class ChangeDetectionModel:
    model_id = "CHANGE_DETECTION"
    version = "1.0-baseline"
    task = "bi_temporal_change_map"

    def predict(self, inputs: ModelInput) -> ModelOutput:
        start_time = time.perf_counter()

        img_t1, img_t2 = self._load_pair(inputs)
        if img_t1 is None or img_t2 is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="Bi-temporal change detection requires two valid images.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        if img_t1.size != img_t2.size:
            img_t2 = img_t2.resize(img_t1.size, Image.Resampling.BILINEAR)

        arr1 = np.array(img_t1.convert("L"), dtype=np.float32)
        arr2 = np.array(img_t2.convert("L"), dtype=np.float32)

        # Grayscale absolute difference
        diff = np.abs(arr1 - arr2)

        # Adaptive thresholding
        active = diff[diff > 8]
        if len(active) > 0:
            threshold = float(np.percentile(active, 35))
            threshold = max(20.0, min(65.0, threshold))
        else:
            threshold = 30.0

        raw_mask = (diff >= threshold).astype(np.uint8) * 255

        # Morphological noise cleanup
        structure = np.ones((3, 3), dtype=bool)
        cleaned_mask = ndimage.binary_opening(raw_mask > 0, structure=structure)
        cleaned_mask = ndimage.binary_closing(cleaned_mask, structure=structure).astype(np.uint8) * 255

        # Bounding box extraction
        labeled, num_features = ndimage.label(cleaned_mask > 0)
        boxes = []
        for i in range(1, min(num_features + 1, 50)):
            ys, xs = np.where(labeled == i)
            if len(xs) < 25:
                continue
            boxes.append({
                "x1": float(xs.min()),
                "y1": float(ys.min()),
                "x2": float(xs.max()),
                "y2": float(ys.max()),
                "label": "surface_change",
                "confidence": 0.88,
            })

        change_pixels = int(np.count_nonzero(cleaned_mask))
        total_pixels = int(cleaned_mask.size)
        change_pct = (change_pixels / total_pixels) * 100.0 if total_pixels > 0 else 0.0

        # Create overlay visualization
        overlay_img = img_t2.copy()
        mask_rgba = Image.new("RGBA", img_t2.size, (255, 0, 0, 0))
        red_tint = np.zeros((img_t2.height, img_t2.width, 4), dtype=np.uint8)
        red_tint[cleaned_mask > 0] = [239, 68, 68, 140]  # Red overlay with transparency
        mask_rgba = Image.fromarray(red_tint, mode="RGBA")
        overlay_composite = Image.alpha_composite(overlay_img.convert("RGBA"), mask_rgba)

        draw = ImageDraw.Draw(overlay_composite)
        for b in boxes[:15]:
            draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline="#ef4444", width=2)

        buf_mask = io.BytesIO()
        Image.fromarray(cleaned_mask).save(buf_mask, format="PNG")
        mask_bytes = buf_mask.getvalue()

        buf_overlay = io.BytesIO()
        overlay_composite.convert("RGB").save(buf_overlay, format="PNG")
        overlay_bytes = buf_overlay.getvalue()

        latency = int((time.perf_counter() - start_time) * 1000)

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=f"Bi-temporal change detection identified surface alteration across {change_pct:.2f}% of the AOI ({len(boxes)} major change clusters).",
            confidence=round(min(0.94, 0.65 + change_pct / 100.0), 3),
            boxes=boxes,
            change_mask=mask_bytes,
            overlay=overlay_bytes,
            latency_ms=latency,
            status="ok",
            raw={
                "adaptation": "baseline",
                "base_model": "diff-connected-components",
                "change_percent": round(change_pct, 2),
                "change_pixels": change_pixels,
                "total_pixels": total_pixels,
                "threshold_used": threshold,
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
