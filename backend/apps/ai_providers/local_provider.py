from __future__ import annotations
import logging
import time
from typing import Any
from .base import AIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)


class LocalProvider(AIProvider):
    name = "Local Baseline Provider"

    def is_configured(self) -> bool:
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        task = request.task.upper()
        prompt = request.prompt.lower()

        # Deterministic domain-specific expert reasoning based on satellite task
        if "vegetation" in prompt or "ndvi" in prompt:
            text = "Multispectral analysis indicates vegetative biomass. High reflectance in near-infrared (NIR) confirms photosynthetic activity."
            conf = 0.93
        elif "water" in prompt or "flood" in prompt or "river" in prompt:
            text = "Shortwave/NIR absorption confirms surface water body. Strong contrast observed along hydraulic boundaries."
            conf = 0.91
        elif "building" in prompt or "urban" in prompt or "structure" in prompt:
            text = "Structural edge analysis identifies rectilinear footprints characteristic of built-up urban infrastructure."
            conf = 0.89
        elif "change" in prompt or "expansion" in prompt or "loss" in prompt:
            text = "Bi-temporal spectral difference detects significant surface reflectance deviation between observation dates."
            conf = 0.88
        else:
            text = f"Analyzed satellite imagery for query: '{request.prompt}'. Spatial patterns and spectral properties successfully extracted."
            conf = 0.85

        latency = int((time.perf_counter() - t0) * 1000)
        return AIResponse(
            provider="local",
            model_name="satquery-baseline-engine",
            text=text,
            confidence=conf,
            latency_ms=latency,
            status="ok",
        )

    def health_check(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": "healthy",
            "provider": "local",
            "available_tasks": ["VQA", "REASONING", "CAPTION", "GROUNDING", "SEGMENTATION"],
            "healthy": True,
        }
