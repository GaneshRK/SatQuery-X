from __future__ import annotations
import base64
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


class OpenAIProvider(AIProvider):
    name = "OpenAI Provider"
    API_URL = "https://api.openai.com/v1/chat/completions"

    @property
    def api_key(self) -> str:
        return getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY", "")

    @property
    def model_name(self) -> str:
        return getattr(settings, "OPENAI_MODEL", None) or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-"))

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.is_configured():
            return AIResponse(
                provider="openai",
                model_name=self.model_name,
                text="",
                status="unconfigured",
                error="OPENAI_API_KEY not configured",
            )

        t0 = time.perf_counter()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_instruction},
        ]

        user_content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]

        # Multimodal image attachment if image paths provided
        for img_path in request.image_paths[:2]:
            if os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    ext = os.path.splitext(img_path)[1].lower()
                    mime = "image/png" if ext == ".png" else "image/jpeg"
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}
                    })
                except Exception as ie:
                    logger.warning("Failed to encode image for OpenAI: %s", ie)

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.API_URL,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "SatQuery-AI/2.0 (OpenAI Provider)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    latency = int((time.perf_counter() - t0) * 1000)
                    return AIResponse(
                        provider="openai",
                        model_name=self.model_name,
                        text=content,
                        confidence=0.92,
                        latency_ms=latency,
                        status="ok",
                    )
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)
            return AIResponse(
                provider="openai",
                model_name=self.model_name,
                text="",
                status="failed",
                error=str(e),
            )

        return AIResponse(provider="openai", model_name=self.model_name, text="", status="failed")

    def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "name": self.name,
                "status": "not_configured",
                "message": "OPENAI_API_KEY is not set in server environment.",
                "healthy": False,
            }
        return {
            "name": self.name,
            "status": "configured",
            "model": self.model_name,
            "healthy": True,
        }
