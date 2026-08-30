"""Health check and liveness/readiness probes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.api.schemas import HealthCheckResponse
from backend.config import get_settings
from backend.registry.loader import ModelRegistry

router = APIRouter(tags=["System"])


@router.get("/v1/health", response_model=HealthCheckResponse)
@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    settings = get_settings()
    registry = ModelRegistry()

    # Check key models health
    models_healthy = True
    try:
        models_healthy = any(registry.health(m.id) for m in registry.list_all())
    except Exception:
        models_healthy = False

    return HealthCheckResponse(
        status="healthy",
        version="0.1.0",
        environment=settings.satquery_env,
        timestamp=datetime.now(timezone.utc),
        components={
            "api_gateway": True,
            "model_registry": models_healthy,
            "geospatial_engine": True,
            "evidence_engine": True,
        },
    )
