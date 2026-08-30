"""Pydantic v2 schemas for SatQuery-X API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sessions & Images
# ---------------------------------------------------------------------------


class SessionCreateResponse(BaseModel):
    session_id: uuid.UUID
    created_at: datetime
    message: str = "Session initialized successfully."


class RasterMetadataResponse(BaseModel):
    image_id: uuid.UUID
    filename: str
    content_type: str
    width: int
    height: int
    band_count: int
    geo_referenced: bool = False
    crs: str | None = None
    bounds_wgs84: dict[str, float] | None = None
    affine: list[float] | None = None
    nodata: float | None = None
    sensor_type: str | None = None
    preview_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ImageUploadResponse(BaseModel):
    session_id: uuid.UUID
    images: list[RasterMetadataResponse]
    detected_mode: str
    co_registration_valid: bool = True
    validation_message: str = "Ingestion successful."


class SessionDetailResponse(BaseModel):
    session_id: uuid.UUID
    created_at: datetime
    images: list[RasterMetadataResponse]
    queries_count: int


# ---------------------------------------------------------------------------
# Queries & Execution Trace (§5 Contract)
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    text: str = Field(..., description="Natural language question or instruction")
    image_ids: list[uuid.UUID] = Field(default_factory=list, description="IDs of images in session")
    sync: bool = Field(default=True, description="Execute synchronously (True) or dispatch to background queue (False)")


class PlanStepSchema(BaseModel):
    step: int
    tool: str
    version: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvidenceBoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "detected_region"
    confidence: float = 0.5


class EvidenceOutputSchema(BaseModel):
    change_mask_url: str | None = None
    overlay_url: str | None = None
    bboxes: list[dict[str, Any]] = Field(default_factory=list)
    geojson: list[dict[str, Any]] = Field(default_factory=list)
    quantified_area_km2: float | None = None
    quantified_area_hectares: float | None = None
    change_percentage: float | None = None


class ExecutionTraceResponse(BaseModel):
    query_id: uuid.UUID
    session_id: uuid.UUID
    query: str
    detected_mode: str
    task_classification: str
    status: str
    plan: list[PlanStepSchema]
    outputs: dict[str, Any]
    answer: str
    confidence: float
    evidence: EvidenceOutputSchema
    timings_ms: dict[str, float]
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Models Registry Schema (§4)
# ---------------------------------------------------------------------------


class ModelRegistryEntryResponse(BaseModel):
    id: str
    version: str
    task: str
    input_modes: list[str]
    status: str
    base_arch: str
    training_data: list[str] = Field(default_factory=list)
    hardware: str = "cpu"
    healthy: bool = True
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ModelListResponse(BaseModel):
    models: list[ModelRegistryEntryResponse]
    count: int


# ---------------------------------------------------------------------------
# Reports Schema (§8, §11)
# ---------------------------------------------------------------------------


class ReportGenerateRequest(BaseModel):
    query_id: uuid.UUID
    title: str = "SatQuery-X Geospatial Intelligence Report"
    format: str = Field(default="html", description="'html' or 'pdf'")
    include_map: bool = True
    analyst_notes: str | None = None


class ReportResponse(BaseModel):
    report_id: uuid.UUID
    query_id: uuid.UUID
    format: str
    download_url: str
    html_preview_url: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Auth & System
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "analyst"
    expires_in: int = 86400


class HealthCheckResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    environment: str
    timestamp: datetime
    components: dict[str, bool]
