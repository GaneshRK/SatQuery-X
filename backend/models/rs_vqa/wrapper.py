"""RS-VQA baseline using BLIP-VQA (zero-shot, clearly labeled)."""

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
    from transformers import BlipForQuestionAnswering, BlipProcessor

    HAS_ML = True
except ImportError:
    HAS_ML = False


class RSVQAModel(BaseModelWrapper):
    model_id = "RS_VQA"
    version = "v0.1-baseline"

    def __init__(self) -> None:
        self._processor = None
        self._model = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded or not HAS_ML:
            return
        settings = get_settings()
        self._processor = BlipProcessor.from_pretrained(settings.rs_vqa_model)
        self._model = BlipForQuestionAnswering.from_pretrained(settings.rs_vqa_model)
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
                task=TaskType.VISUAL_QUESTION_ANSWERING,
                status=ModelStatus.ERROR,
                error="No image provided.",
            )

        question = inputs.question or inputs.text_prompt or "What is in this image?"
        image = self._load_image(inputs)

        if HAS_ML:
            return self._infer_ml(image, question, start)
        return self._infer_heuristic(image, question, start)

    def _load_image(self, inputs: ModelInput) -> Image.Image:
        if inputs.image_bytes:
            return Image.open(io.BytesIO(inputs.image_bytes[0])).convert("RGB")
        return Image.open(inputs.image_paths[0]).convert("RGB")

    def _infer_ml(self, image: Image.Image, question: str, start: float) -> ModelOutput:
        settings = get_settings()
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None

        inputs_pt = self._processor(image, question, return_tensors="pt").to(settings.model_device)
        with torch.no_grad():
            outputs = self._model.generate(**inputs_pt, output_scores=True, return_dict_in_generate=True)

        answer = self._processor.decode(outputs.sequences[0], skip_special_tokens=True)
        confidence = self._estimate_confidence(outputs)

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.VISUAL_QUESTION_ANSWERING,
            answer=answer,
            confidence=confidence,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=ModelStatus.BASELINE,
            raw={"baseline_note": "Zero-shot BLIP-VQA, not RS fine-tuned."},
        )

    def _infer_heuristic(self, image: Image.Image, question: str, start: float) -> ModelOutput:
        arr = np.array(image)
        mean_rgb = arr.mean(axis=(0, 1))
        dominant = ["red", "green", "blue"][int(np.argmax(mean_rgb))]
        answer = (
            f"[Baseline heuristic — install torch/transformers for BLIP-VQA] "
            f"Image appears {dominant}-dominant. Question: {question}"
        )
        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=TaskType.VISUAL_QUESTION_ANSWERING,
            answer=answer,
            confidence=0.35,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=ModelStatus.BASELINE,
            raw={"baseline_note": "Heuristic fallback without ML deps."},
        )

    def _estimate_confidence(self, outputs) -> float:
        if hasattr(outputs, "sequences_scores") and outputs.sequences_scores:
            scores = outputs.sequences_scores[0]
            if scores:
                import torch

                probs = torch.softmax(torch.tensor(scores), dim=-1)
                return float(probs.max().item())
        return 0.65
