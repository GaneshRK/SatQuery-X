from __future__ import annotations
import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any
from django.conf import settings
from .base import AIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)


class HuggingFaceProvider(AIProvider):
    name = "Hugging Face Inference Provider"
    INFERENCE_BASE_URL = "https://api-inference.huggingface.co/models/"

    @property
    def hf_token(self) -> str:
        return getattr(settings, "HF_TOKEN", None) or os.getenv("HF_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.hf_token and len(self.hf_token) > 10)

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.is_configured():
            return AIResponse(
                provider="huggingface",
                model_name="unconfigured",
                text="",
                status="unconfigured",
                error="HF_TOKEN not configured",
            )

        t0 = time.perf_counter()
        # Default specialized remote sensing vision-language model on HF
        model_id = request.extra_params.get("hf_model_id", "Salesforce/blip-vqa-base")
        url = f"{self.INFERENCE_BASE_URL}{model_id}"

        payload = {"inputs": request.prompt}

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.hf_token}",
                    "User-Agent": "SatQuery-AI/2.0 (Hugging Face Provider)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = ""
                    if isinstance(data, list) and len(data) > 0:
                        text = str(data[0].get("answer") or data[0].get("generated_text") or data[0])
                    elif isinstance(data, dict):
                        text = str(data.get("answer") or data.get("generated_text") or data)

                    latency = int((time.perf_counter() - t0) * 1000)
                    return AIResponse(
                        provider="huggingface",
                        model_name=model_id,
                        text=text,
                        confidence=0.89,
                        latency_ms=latency,
                        status="ok",
                    )
        except Exception as e:
            logger.warning("Hugging Face API request failed: %s", e)
            return AIResponse(
                provider="huggingface",
                model_name=model_id,
                text="",
                status="failed",
                error=str(e),
            )

        return AIResponse(provider="huggingface", model_name=model_id, text="", status="failed")

    def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "name": self.name,
                "status": "not_configured",
                "message": "HF_TOKEN not configured in environment.",
                "healthy": False,
            }
        return {
            "name": self.name,
            "status": "configured",
            "healthy": True,
        }
