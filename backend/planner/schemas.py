"""Execution trace and plan schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step: int
    tool: str
    version: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvidenceOutput(BaseModel):
    change_mask_url: str | None = None
    overlay_url: str | None = None
    bboxes: list[dict[str, Any]] = Field(default_factory=list)
    geojson: list[dict[str, Any]] = Field(default_factory=list)
    before_after_thumbnails: list[str] = Field(default_factory=list)
    quantified_area_km2: float | None = None
    quantified_area_hectares: float | None = None
    change_percentage: float | None = None


class ExecutionTrace(BaseModel):
    query: str
    detected_mode: str
    task_classification: str
    plan: list[PlanStep]
    outputs: dict[str, Any]
    answer: str
    confidence: float
    evidence: EvidenceOutput
    timings_ms: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
