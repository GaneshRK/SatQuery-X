"""RS_GROUNDING specialist model wrapper per §9."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from apps.agent.contracts import ModelInput, ModelOutput


class RSGroundingModel:
    model_id = "RS_GROUNDING"
    version = "1.0-baseline"
    task = "text_guided_grounding"

    def predict(self, inputs: ModelInput) -> ModelOutput:
        start_time = time.perf_counter()
        img = self._load_image(inputs)
        if img is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="No valid image provided for RS_GROUNDING.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        prompt = (inputs.text_prompt or inputs.question or "water").lower()
        w, h = img.size
        arr = np.array(img)

        # Spectral saliency proposal based on prompt target
        if "water" in prompt or "river" in prompt or "lake" in prompt:
            # Water saliency: high blue/green absorption
            if len(arr.shape) == 3 and arr.shape[2] >= 3:
                r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
                saliency = ((b > r) & (b > g * 0.85) & (b < 140)).astype(np.uint8)
            else:
                saliency = (arr < 60).astype(np.uint8)
            label = "water_body"
        elif "built-up" in prompt or "building" in prompt or "urban" in prompt:
            if len(arr.shape) == 3 and arr.shape[2] >= 3:
                r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
                saliency = ((np.abs(r - g) < 25) & (np.abs(g - b) < 25) & (r > 120)).astype(np.uint8)
            else:
                saliency = (arr > 160).astype(np.uint8)
            label = "built_up"
        else:
            # Vegetation or generic salient features
            if len(arr.shape) == 3 and arr.shape[2] >= 3:
                r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
                saliency = ((g > r * 1.1) & (g > b)).astype(np.uint8)
            else:
                saliency = ((arr > 80) & (arr < 180)).astype(np.uint8)
            label = "vegetation"

        # Morphological clustering
        labeled, num_features = ndimage.label(saliency > 0)
        boxes = []

        # Find largest clusters
        for i in range(1, min(num_features + 1, 20)):
            ys, xs = np.where(labeled == i)
            if len(xs) < 50:
                continue
            x1, x2 = float(xs.min()), float(xs.max())
            y1, y2 = float(ys.min()), float(ys.max())
            confidence = round(min(0.92, 0.70 + len(xs) / (w * h * 0.1)), 3)
            boxes.append({
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "label": label,
                "confidence": confidence,
            })

        # Generate overlay image
        overlay_img = img.copy()
        draw = ImageDraw.Draw(overlay_img)
        for b in boxes:
            draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline="#3b82f6", width=3)

        buf = io.BytesIO()
        overlay_img.save(buf, format="PNG")
        overlay_bytes = buf.getvalue()

        latency = int((time.perf_counter() - start_time) * 1000)

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=f"Grounded {len(boxes)} region(s) matching '{label}' via spectral saliency proposals.",
            boxes=boxes,
            overlay=overlay_bytes,
            confidence=0.84 if boxes else 0.50,
            latency_ms=latency,
            status="ok",
            raw={
                "adaptation": "baseline",
                "base_model": "spectral-saliency-region-proposals",
                "regions_found": len(boxes),
            },
        )

    def _load_image(self, inputs: ModelInput) -> Image.Image | None:
        if inputs.image_bytes and len(inputs.image_bytes) > 0:
            return Image.open(io.BytesIO(inputs.image_bytes[0])).convert("RGB")
        if inputs.image_paths and len(inputs.image_paths) > 0:
            path = Path(inputs.image_paths[0])
            if path.exists():
                return Image.open(path).convert("RGB")
        return None
