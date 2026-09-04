"""Standard contracts for model inputs and outputs per §8.6."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelInput:
    model_id: str
    image_paths: list[str] = field(default_factory=list)
    image_bytes: list[bytes] = field(default_factory=list)
    question: str | None = None
    text_prompt: str | None = None
    change_mask: str | bytes | None = None
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelOutput:
    model_id: str
    version: str
    task: str
    answer: str | None = None
    caption: str | None = None
    confidence: float | None = None
    boxes: list[dict[str, Any]] | None = None
    change_mask: str | bytes | None = None
    overlay: str | bytes | None = None
    raw: dict[str, Any] | None = None
    latency_ms: int | None = None
    status: str = "ok"
    error: str | None = None
