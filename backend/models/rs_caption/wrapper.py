"""RS-Caption baseline using BLIP image captioning."""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from backend.config import get_settings
from backend.registry.base import BaseModelWrapper
from backend.registry.contracts import ModelInput, ModelOutput, ModelStatus, TaskType

try:
    import torch
    from transformers import BlipForConditionalGeneration, BlipProcessor

    HAS_ML = True
except ImportError:
    HAS_ML = False


class RSCaptionModel(BaseModelWrapper):
    model_id = "RS_CAPTION"
    version = "v0.1-baseline"

    def __init__(self) -> None:
        self._processor = None
        self._model = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded or not HAS_ML:
            return
        settings = get_settings()
        self._processor = BlipProcessor.from_pretrained(settings.rs_caption_model)
        self._model = BlipForConditionalGeneration.from_pretrained(settings.rs_caption_model)
        self._model.to(settings.model_device)
        self._model.eval()
        self._loaded = True

    def health(self) -> bool:
        if not HAS_ML:
            return True
        try:
            self._ensure_loaded()
            return self._model is not None
        except Exception:
            return False

    def infer(self, inputs: ModelInput) -> ModelOutput:
        start = time.perf_counter()
        if not inputs.image_bytes and not inputs.image_paths:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=TaskType.IMAGE_CAPTIONING,
                status=ModelStatus.ERROR,
                error="No image provided.",
            )

        image = (
            Image.open(io.BytesIO(inputs.image_bytes[0])).convert("RGB")
            if inputs.image_bytes
            else Image.open(inputs.image_paths[0]).convert("RGB")
        )

        if HAS_ML:
            settings = get_settings()
            self._ensure_loaded()
            assert self._processor is not None and self._model is not None
            inputs_pt = self._processor(image, return_tensors="pt").to(settings.model_device)
            with torch.no_grad():
                out = self._model.generate(**inputs_pt, max_new_tokens=50)
            caption = self._processor.decode(out[0], skip_special_tokens=True)
            confidence = 0.72
        else:
            arr = np.array(image)
            brightness = arr.mean()
            caption = (
                f"[Baseline heuristic] A satellite image with average brightness {brightness:.1f}."
            )
            confidence = 0.3

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.IMAGE_CAPTIONING,
            caption=caption,
            answer=caption,
            confidence=confidence,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=ModelStatus.BASELINE,
            raw={"baseline_note": "Zero-shot BLIP captioning, not RS fine-tuned."},
        )
