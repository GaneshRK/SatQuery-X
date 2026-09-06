from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from django.conf import settings

from .base import AIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)


class HuggingFaceProvider(AIProvider):
    """
    Hugging Face provider.

    Used for model-specific inference when an explicit HF model is
    configured for the requested task.

    The provider does not claim that a generic model is a scientific
    remote-sensing specialist.
    """

    name = "Hugging Face Provider"

    INFERENCE_BASE_URL = (
        "https://api-inference.huggingface.co/models/"
    )

    DEFAULT_MODEL_BY_TASK = {
        "VQA": "Salesforce/blip-vqa-base",
        "CAPTION": "Salesforce/blip-image-captioning-base",
    }

    TIMEOUT_SECONDS = 30.0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def hf_token(self) -> str:
        return (
            getattr(settings, "HF_TOKEN", None)
            or os.getenv("HF_TOKEN", "")
        )

    def is_configured(self) -> bool:
        return len(self.hf_token.strip()) > 10

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

    def model_for_request(
        self,
        request: AIRequest,
    ) -> str | None:
        explicit = request.extra_params.get(
            "hf_model_id"
        )

        if explicit:
            return str(explicit).strip()

        configured_models = getattr(
            settings,
            "HF_MODEL_BY_TASK",
            {},
        )

        if isinstance(configured_models, dict):
            configured = configured_models.get(
                request.normalized_task()
            )

            if configured:
                return str(configured).strip()

        return self.DEFAULT_MODEL_BY_TASK.get(
            request.normalized_task()
        )

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def supports_task(self, task: str) -> bool:
        return task.upper() in {
            "VQA",
            "CAPTION",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(path: str) -> str | None:
        file_path = Path(path)

        try:
            if not file_path.is_file():
                return None

            data = file_path.read_bytes()

        except (OSError, ValueError):
            return None

        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def _extract_text(data: Any) -> str:
        if isinstance(data, list):
            parts: list[str] = []

            for item in data:
                if isinstance(item, dict):
                    for key in (
                        "answer",
                        "generated_text",
                        "text",
                    ):
                        value = item.get(key)

                        if isinstance(value, str) and value.strip():
                            parts.append(value.strip())
                            break

                elif isinstance(item, str):
                    parts.append(item.strip())

            return "\n".join(parts).strip()

        if isinstance(data, dict):
            for key in (
                "answer",
                "generated_text",
                "text",
            ):
                value = data.get(key)

                if isinstance(value, str) and value.strip():
                    return value.strip()

        if isinstance(data, str):
            return data.strip()

        return ""

    @staticmethod
    def _build_payload(
        request: AIRequest,
        image_base64: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "inputs": request.prompt,
        }

        if image_base64:
            # HF Inference APIs differ by model. Keep this configurable.
            payload["parameters"] = request.extra_params.get(
                "parameters",
                {},
            )

            payload["image"] = image_base64

        return payload

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, request: AIRequest) -> AIResponse:
        started = time.perf_counter()

        if not self.is_configured():
            return AIResponse(
                provider="huggingface",
                model_name="unconfigured",
                status="unconfigured",
                error="HF_TOKEN is not configured.",
            )

        errors = request.validate()

        if errors:
            return AIResponse.failed(
                provider="huggingface",
                model_name="unknown",
                error="; ".join(errors),
            )

        task = request.normalized_task()

        if not self.supports_task(task):
            return AIResponse.failed(
                provider="huggingface",
                model_name="unsupported",
                error=f"Hugging Face provider does not support task '{task}'.",
            )

        model_id = self.model_for_request(request)

        if not model_id:
            return AIResponse.insufficient_evidence(
                provider="huggingface",
                model_name="unconfigured",
                reason=(
                    f"No Hugging Face model is configured for task '{task}'."
                ),
            )

        image_base64: str | None = None

        if request.image_paths:
            image_base64 = self._encode_image(
                request.image_paths[0]
            )

        payload = self._build_payload(
            request,
            image_base64,
        )

        url = (
            self.INFERENCE_BASE_URL
            + model_id
        )

        request_data = json.dumps(
            payload
        ).encode("utf-8")

        http_request = urllib.request.Request(
            url,
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.hf_token}",
                "User-Agent": "SatQuery-X/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self.TIMEOUT_SECONDS,
            ) as response:
                raw = response.read()

                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"Hugging Face returned HTTP {response.status}"
                    )

                data = json.loads(
                    raw.decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode(
                    "utf-8",
                    errors="replace",
                )
            except Exception:
                body = ""

            logger.warning(
                "Hugging Face HTTP error %s: %s",
                exc.code,
                body[:1000],
            )

            return AIResponse.failed(
                provider="huggingface",
                model_name=model_id,
                error=f"Hugging Face HTTP error {exc.code}.",
                latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
            )

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
            OSError,
        ) as exc:
            logger.warning(
                "Hugging Face request failed: %s",
                exc,
            )

            return AIResponse.failed(
                provider="huggingface",
                model_name=model_id,
                error=str(exc),
                latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
            )

        text = self._extract_text(data)

        latency = int(
            (time.perf_counter() - started) * 1000
        )

        if not text:
            return AIResponse.failed(
                provider="huggingface",
                model_name=model_id,
                error="Hugging Face returned no usable text.",
                latency_ms=latency,
            )

        return AIResponse(
            provider="huggingface",
            model_name=model_id,
            text=text,
            structured_data={
                "task": task,
                "model": model_id,
            },
            confidence=None,
            latency_ms=latency,
            status="ok",
            limitations=[
                "Model-generated interpretation is not itself a "
                "quantitative remote-sensing measurement."
            ],
            trace=[
                {
                    "step": "provider_execution",
                    "provider": "huggingface",
                    "task": task,
                    "model": model_id,
                }
            ],
            metadata={
                "image_supplied": bool(image_base64),
            },
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "name": self.name,
                "provider": "huggingface",
                "status": "not_configured",
                "healthy": False,
            }

        return {
            "name": self.name,
            "provider": "huggingface",
            "status": "configured",
            "healthy": True,
            "available_tasks": self.capabilities(),
        }