from __future__ import annotations

import logging
from typing import Any

from .base import AIRequest, AIResponse
from .hf_provider import HuggingFaceProvider
from .local_provider import LocalProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    SatQuery-X AI provider router.

    The router decides which external/general AI provider should execute
    a request.

    Important distinction:

        AI provider router
                !=
        scientific remote-sensing model registry

    Specialized remote-sensing models such as:
        RS_VQA
        RS_CAPTION
        RS_GROUNDING
        CHANGE_DETECTION
        CHANGE_VQA
        OPTICAL_SAR_FUSION

    should be executed by the application's model layer when available.

    This router handles general provider execution and explanation.
    """

    def __init__(self) -> None:
        self.local_provider = LocalProvider()
        self.openai_provider = OpenAIProvider()
        self.hf_provider = HuggingFaceProvider()

        self.providers = {
            "local": self.local_provider,
            "openai": self.openai_provider,
            "huggingface": self.hf_provider,
        }

    # ------------------------------------------------------------------
    # Provider ordering
    # ------------------------------------------------------------------

    @staticmethod
    def _provider_order(
        request: AIRequest,
    ) -> list[str]:
        task = request.normalized_task()

        # User/planner can explicitly request a provider.
        preferred = request.extra_params.get(
            "provider"
        )

        if preferred:
            preferred = str(preferred).strip().lower()

            if preferred in {
                "local",
                "openai",
                "huggingface",
                "hf",
            }:
                normalized = (
                    "huggingface"
                    if preferred == "hf"
                    else preferred
                )

                remaining = [
                    name
                    for name in (
                        "openai",
                        "huggingface",
                        "local",
                    )
                    if name != normalized
                ]

                return [normalized, *remaining]

        # Complex reasoning should prefer OpenAI.
        if task in {
            "REASONING",
            "PLANNING",
            "EXPLANATION",
            "CHANGE_VQA",
            "GROUNDING",
        }:
            return [
                "openai",
                "local",
            ]

        # VQA/caption can use HF where configured.
        if task in {
            "VQA",
            "CAPTION",
        }:
            if request.image_paths:
                return [
                    "openai",
                    "huggingface",
                    "local",
                ]

            return [
                "openai",
                "huggingface",
                "local",
            ]

        # Scientific specialist outputs should normally be generated
        # upstream by the model registry. If the request reaches here,
        # do not pretend the generic provider performed the analysis.
        if task in {
            "CHANGE_DETECTION",
            "OPTICAL_SAR_FUSION",
            "SEGMENTATION",
        }:
            return [
                "local",
            ]

        return [
            "openai",
            "local",
        ]

    # ------------------------------------------------------------------
    # Evidence requirements
    # ------------------------------------------------------------------

    @staticmethod
    def _requires_verified_evidence(
        task: str,
    ) -> bool:
        return task in {
            "CHANGE_DETECTION",
            "OPTICAL_SAR_FUSION",
            "SEGMENTATION",
        }

    @staticmethod
    def _has_verified_evidence(
        request: AIRequest,
    ) -> bool:
        return bool(
            request.evidence
            and isinstance(
                request.evidence,
                dict,
            )
        )

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(
        self,
        request: AIRequest,
    ) -> AIResponse:
        errors = request.validate()

        if errors:
            return AIResponse.failed(
                provider="router",
                model_name="none",
                error="; ".join(errors),
                trace=[
                    {
                        "step": "router_validation",
                        "status": "failed",
                    }
                ],
            )

        task = request.normalized_task()

        # --------------------------------------------------------------
        # Scientific analysis tasks
        # --------------------------------------------------------------
        #
        # Generic LLMs must not be allowed to pretend that they performed
        # actual change detection/fusion/segmentation.
        # --------------------------------------------------------------

        if self._requires_verified_evidence(task):
            if not self._has_verified_evidence(request):
                return AIResponse.insufficient_evidence(
                    provider="router",
                    model_name="none",
                    reason=(
                        f"Task '{task}' requires verified analysis "
                        "evidence from the scientific analysis pipeline."
                    ),
                    trace=[
                        {
                            "step": "router",
                            "task": task,
                            "decision": "blocked_without_evidence",
                        }
                    ],
                )

        provider_order = self._provider_order(request)

        attempts: list[dict[str, Any]] = []

        for provider_name in provider_order:
            provider = self.providers.get(provider_name)

            if provider is None:
                continue

            if not provider.is_configured():
                attempts.append(
                    {
                        "provider": provider_name,
                        "status": "not_configured",
                    }
                )
                continue

            if not provider.supports_task(task):
                attempts.append(
                    {
                        "provider": provider_name,
                        "status": "unsupported_task",
                    }
                )
                continue

            try:
                response = provider.generate(request)

            except Exception as exc:
                logger.exception(
                    "Provider %s failed unexpectedly.",
                    provider_name,
                )

                attempts.append(
                    {
                        "provider": provider_name,
                        "status": "exception",
                        "error": str(exc),
                    }
                )

                continue

            attempts.append(
                {
                    "provider": provider_name,
                    "status": response.status,
                }
            )

            if response.status == "ok":
                response.trace = [
                    *attempts,
                    *response.trace,
                ]

                return response

            # Insufficient evidence is not a provider crash.
            if response.status == "insufficient_evidence":
                response.trace = [
                    *attempts,
                    *response.trace,
                ]

                return response

        return AIResponse.failed(
            provider="router",
            model_name="none",
            error=(
                "No configured AI provider could execute "
                f"task '{task}'."
            ),
            trace=attempts,
        )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:
        return self.route(request)

    def get_provider(
        self,
        name: str,
    ):
        normalized = name.strip().lower()

        if normalized == "hf":
            normalized = "huggingface"

        return self.providers.get(normalized)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for name, provider in self.providers.items():
            try:
                result[name] = provider.health_check()
            except Exception as exc:
                logger.exception(
                    "Health check failed for %s",
                    name,
                )

                result[name] = {
                    "name": provider.name,
                    "provider": name,
                    "status": "error",
                    "healthy": False,
                    "error": str(exc),
                }

        active_reasoning_provider = "local"

        if self.openai_provider.is_configured():
            active_reasoning_provider = "openai"

        elif self.hf_provider.is_configured():
            active_reasoning_provider = "huggingface"

        result["active_reasoning_provider"] = (
            active_reasoning_provider
        )

        result["router"] = {
            "status": "healthy",
            "healthy": True,
        }

        return result