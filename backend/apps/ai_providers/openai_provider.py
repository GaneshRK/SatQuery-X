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


class OpenAIProvider(AIProvider):
    """
    OpenAI provider for language/multimodal reasoning.

    OpenAI is treated as an explanation/reasoning layer.

    It must not be treated as the source of quantitative remote-sensing
    measurements unless those measurements are supplied by the actual
    analysis pipeline.
    """

    name = "OpenAI Provider"

    API_URL = "https://api.openai.com/v1/chat/completions"

    DEFAULT_MODEL = "gpt-4o-mini"

    MAX_IMAGES = 4

    TIMEOUT_SECONDS = 30.0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def api_key(self) -> str:
        return (
            getattr(settings, "OPENAI_API_KEY", None)
            or os.getenv("OPENAI_API_KEY", "")
        )

    @property
    def model_name(self) -> str:
        return (
            getattr(settings, "OPENAI_MODEL", None)
            or os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)
        )

    def is_configured(self) -> bool:
        key = self.api_key.strip()

        return bool(
            key
            and (
                key.startswith("sk-")
                or key.startswith("sk-proj-")
            )
        )

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def supports_task(self, task: str) -> bool:
        return task.upper() in {
            "REASONING",
            "PLANNING",
            "EXPLANATION",
            "VQA",
            "CAPTION",
            "GROUNDING",
            "CHANGE_VQA",
        }

    # ------------------------------------------------------------------
    # Prompt safety
    # ------------------------------------------------------------------

    @staticmethod
    def _system_instruction(request: AIRequest) -> str:
        base = request.system_instruction.strip()

        evidence_rules = """
Evidence rules:
1. Use only information present in the supplied evidence, context, and
   attached images.
2. Never invent coordinates, areas, percentages, dates, sensors, bands,
   acquisition times, classifications, or measurements.
3. If the supplied evidence does not establish an answer, explicitly say
   that the available evidence is insufficient.
4. Do not treat visual plausibility as a quantitative measurement.
5. Do not claim that a change is statistically significant unless the
   supplied analysis establishes that.
6. Do not fabricate satellite catalog results.
7. Do not fabricate external sources.
8. Keep the response concise and auditable.
9. Do not reveal hidden chain-of-thought or private reasoning.
10. Separate observations from interpretations.
""".strip()

        return f"{base}\n\n{evidence_rules}"

    # ------------------------------------------------------------------
    # Image encoding
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(path: str) -> dict[str, Any] | None:
        file_path = Path(path)

        try:
            if not file_path.is_file():
                return None

            data = file_path.read_bytes()

        except (OSError, ValueError):
            return None

        mime_type, _ = mimetypes.guess_type(str(file_path))

        if mime_type not in {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
        }:
            mime_type = "image/jpeg"

        encoded = base64.b64encode(data).decode("ascii")

        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{encoded}",
                "detail": "high",
            },
        }

    # ------------------------------------------------------------------
    # Structured context
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json(value: Any) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except (TypeError, ValueError):
            return str(value)

    @classmethod
    def _build_context_block(
        cls,
        request: AIRequest,
    ) -> str:
        sections: list[str] = []

        if request.context:
            sections.append(
                "CONTEXT:\n"
                + cls._safe_json(request.context)
            )

        if request.evidence:
            sections.append(
                "VERIFIED ANALYSIS EVIDENCE:\n"
                + cls._safe_json(request.evidence)
            )

        if not sections:
            sections.append(
                "VERIFIED ANALYSIS EVIDENCE:\n"
                "No structured evidence was supplied."
            )

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Response extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            return ""

        choice = choices[0]

        if not isinstance(choice, dict):
            return ""

        message = choice.get("message")

        if not isinstance(message, dict):
            return ""

        content = message.get("content")

        if isinstance(content, str):
            return content.strip()

        # Some API formats can represent content as a list.
        if isinstance(content, list):
            parts: list[str] = []

            for item in content:
                if not isinstance(item, dict):
                    continue

                text = item.get("text")

                if isinstance(text, str):
                    parts.append(text)

            return "\n".join(parts).strip()

        return ""

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, request: AIRequest) -> AIResponse:
        started = time.perf_counter()

        if not self.is_configured():
            return AIResponse(
                provider="openai",
                model_name=self.model_name,
                status="unconfigured",
                error="OPENAI_API_KEY is not configured.",
            )

        errors = request.validate()

        if errors:
            return AIResponse.failed(
                provider="openai",
                model_name=self.model_name,
                error="; ".join(errors),
            )

        task = request.normalized_task()

        if not self.supports_task(task):
            return AIResponse.failed(
                provider="openai",
                model_name=self.model_name,
                error=f"OpenAI provider does not support task '{task}'.",
            )

        user_text = (
            f"TASK: {task}\n\n"
            f"USER REQUEST:\n{request.prompt.strip()}\n\n"
            f"{self._build_context_block(request)}"
        )

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": user_text,
            }
        ]

        image_count = 0

        for path in request.image_paths:
            if image_count >= self.MAX_IMAGES:
                break

            encoded = self._encode_image(path)

            if encoded is None:
                continue

            content.append(encoded)
            image_count += 1

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._system_instruction(request),
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": max(0.0, min(float(request.temperature), 1.0)),
            "max_tokens": int(request.max_tokens),
        }

        request_data = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        http_request = urllib.request.Request(
            self.API_URL,
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
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
                        f"OpenAI returned HTTP {response.status}"
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
                "OpenAI HTTP error %s: %s",
                exc.code,
                body[:1000],
            )

            return AIResponse.failed(
                provider="openai",
                model_name=self.model_name,
                error=f"OpenAI HTTP error {exc.code}.",
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
                "OpenAI request failed: %s",
                exc,
            )

            return AIResponse.failed(
                provider="openai",
                model_name=self.model_name,
                error=str(exc),
                latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
            )

        text = self._extract_content(data)

        latency = int(
            (time.perf_counter() - started) * 1000
        )

        if not text:
            return AIResponse.failed(
                provider="openai",
                model_name=self.model_name,
                error="OpenAI returned an empty response.",
                latency_ms=latency,
            )

        trace = [
            {
                "step": "provider_execution",
                "provider": "openai",
                "task": task,
            },
            {
                "step": "multimodal_input",
                "images_attached": image_count,
            },
            {
                "step": "evidence_context",
                "structured_evidence_supplied": bool(
                    request.evidence
                ),
            },
        ]

        limitations: list[str] = []

        if not request.evidence:
            limitations.append(
                "No structured analysis evidence was supplied; "
                "the response must not be interpreted as a quantitative "
                "remote-sensing measurement."
            )

        return AIResponse(
            provider="openai",
            model_name=self.model_name,
            text=text,
            structured_data={
                "task": task,
                "model": self.model_name,
            },
            confidence=None,
            latency_ms=latency,
            status="ok",
            limitations=limitations,
            trace=trace,
            metadata={
                "images_attached": image_count,
                "evidence_supplied": bool(request.evidence),
            },
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "name": self.name,
                "provider": "openai",
                "status": "not_configured",
                "healthy": False,
                "model": self.model_name,
            }

        return {
            "name": self.name,
            "provider": "openai",
            "status": "configured",
            "healthy": True,
            "model": self.model_name,
            "available_tasks": self.capabilities(),
        }