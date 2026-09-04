from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIRequest:
    task: str  # "REASONING", "VQA", "GROUNDING", "CAPTION", "SEGMENTATION"
    prompt: str
    image_paths: list[str] = field(default_factory=list)
    system_instruction: str = "You are SatQuery AI, an expert Earth Observation and remote sensing intelligence system."
    temperature: float = 0.2
    max_tokens: int = 1024
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    provider: str
    model_name: str
    text: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.88
    latency_ms: int = 0
    status: str = "ok"
    error: str | None = None


class AIProvider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if required credentials or local models are present."""
        pass

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """Execute text or multimodal reasoning request."""
        pass

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return provider status, latency, and operational health."""
        pass
