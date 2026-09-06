from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Supported provider tasks
# ---------------------------------------------------------------------------

AI_TASKS = {
    "REASONING",
    "PLANNING",
    "EXPLANATION",
    "VQA",
    "CAPTION",
    "GROUNDING",
    "SEGMENTATION",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "OPTICAL_SAR_FUSION",
}


# ---------------------------------------------------------------------------
# AI Request
# ---------------------------------------------------------------------------

@dataclass
class AIRequest:
    """
    Provider-independent request passed from the SatQuery-X agent layer.

    Important:
    - Providers receive evidence/context explicitly.
    - Providers must not invent measurements or geographic facts.
    - image_paths contain local files that the provider is allowed to read.
    """

    task: str
    prompt: str

    image_paths: list[str] = field(default_factory=list)

    system_instruction: str = (
        "You are SatQuery-X, an evidence-grounded Earth observation "
        "and remote sensing intelligence assistant. "
        "Only make claims supported by the supplied inputs and evidence. "
        "Never invent coordinates, measurements, dates, sensor names, "
        "change values, or scientific observations."
    )

    temperature: float = 0.2
    max_tokens: int = 1024

    # Structured information supplied by the planner/orchestrator.
    context: dict[str, Any] = field(default_factory=dict)

    # Actual outputs from specialized analysis models/tools.
    evidence: dict[str, Any] = field(default_factory=dict)

    # Optional provider-specific configuration.
    extra_params: dict[str, Any] = field(default_factory=dict)

    def normalized_task(self) -> str:
        return str(self.task or "").strip().upper()

    def has_images(self) -> bool:
        return bool(self.image_paths)

    def has_evidence(self) -> bool:
        return bool(self.evidence)

    def validate(self) -> list[str]:
        """
        Return validation errors instead of raising immediately.

        This allows the orchestrator/router to produce an auditable
        insufficient-evidence result.
        """

        errors: list[str] = []

        if not self.normalized_task():
            errors.append("AI task is required.")

        if not self.prompt or not self.prompt.strip():
            errors.append("AI prompt is required.")

        if self.temperature < 0:
            errors.append("temperature cannot be negative.")

        if self.max_tokens <= 0:
            errors.append("max_tokens must be greater than zero.")

        for path in self.image_paths:
            if not isinstance(path, str) or not path.strip():
                errors.append("image_paths contains an invalid path.")

        return errors


# ---------------------------------------------------------------------------
# AI Response
# ---------------------------------------------------------------------------

@dataclass
class AIResponse:
    """
    Provider-independent response.

    Confidence is optional because an LLM/provider response by itself does
    not automatically justify a scientific confidence score.
    """

    provider: str
    model_name: str

    text: str = ""

    # Machine-readable provider output.
    structured_data: dict[str, Any] = field(default_factory=dict)

    # None means that the provider did not provide a defensible confidence.
    confidence: float | None = None

    latency_ms: int = 0

    status: str = "ok"

    error: str | None = None

    # Evidence identifiers/references supplied by the provider.
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    # Explicit limitations reported by the provider.
    limitations: list[str] = field(default_factory=list)

    # Short auditable trace. This must never contain hidden chain-of-thought.
    trace: list[dict[str, Any]] = field(default_factory=list)

    # Provider/model metadata.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def successful(self) -> bool:
        return self.status == "ok"

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence_refs or self.structured_data)

    @classmethod
    def insufficient_evidence(
        cls,
        *,
        provider: str,
        model_name: str,
        reason: str,
        latency_ms: int = 0,
        trace: list[dict[str, Any]] | None = None,
    ) -> "AIResponse":
        return cls(
            provider=provider,
            model_name=model_name,
            text="",
            structured_data={},
            confidence=None,
            latency_ms=latency_ms,
            status="insufficient_evidence",
            error=reason,
            limitations=[reason],
            trace=trace or [],
        )

    @classmethod
    def failed(
        cls,
        *,
        provider: str,
        model_name: str,
        error: str,
        latency_ms: int = 0,
        trace: list[dict[str, Any]] | None = None,
    ) -> "AIResponse":
        return cls(
            provider=provider,
            model_name=model_name,
            text="",
            confidence=None,
            latency_ms=latency_ms,
            status="failed",
            error=error,
            trace=trace or [],
        )


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class AIProvider(ABC):
    """
    Base interface for every SatQuery-X AI provider.
    """

    name: str = "unknown"

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Return True when the provider can actually execute requests.
        """
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """
        Execute an AI request.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return provider health information.
        """
        raise NotImplementedError

    def supports_task(self, task: str) -> bool:
        """
        Providers may override this when their capabilities are more specific.
        """
        return task.upper() in AI_TASKS

    def capabilities(self) -> list[str]:
        """
        Human-readable provider capabilities.
        """
        return sorted(AI_TASKS)