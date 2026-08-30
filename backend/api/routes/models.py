"""Model Registry inspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas import ModelListResponse, ModelRegistryEntryResponse
from backend.registry.loader import ModelRegistry

router = APIRouter(prefix="/v1/models", tags=["Model Registry"])


@router.get("", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    registry = ModelRegistry()
    entries = registry.list_all()

    model_responses: list[ModelRegistryEntryResponse] = []
    for m in entries:
        model_responses.append(
            ModelRegistryEntryResponse(
                id=m.id,
                version=m.version,
                task=m.task.value if hasattr(m.task, "value") else str(m.task),
                input_modes=[mode.value if hasattr(mode, "value") else str(mode) for mode in m.input_modes],
                status=m.status.value if hasattr(m.status, "value") else str(m.status),
                base_arch=m.base_arch,
                training_data=m.training_data,
                hardware=m.hardware,
                healthy=registry.health(m.id),
                output_schema=m.output,
            )
        )

    return ModelListResponse(models=model_responses, count=len(model_responses))


@router.get("/{model_id}", response_model=ModelRegistryEntryResponse)
async def get_model(model_id: str) -> ModelRegistryEntryResponse:
    registry = ModelRegistry()
    m = registry.get(model_id)

    return ModelRegistryEntryResponse(
        id=m.id,
        version=m.version,
        task=m.task.value if hasattr(m.task, "value") else str(m.task),
        input_modes=[mode.value if hasattr(mode, "value") else str(mode) for mode in m.input_modes],
        status=m.status.value if hasattr(m.status, "value") else str(m.status),
        base_arch=m.base_arch,
        training_data=m.training_data,
        hardware=m.hardware,
        healthy=registry.health(m.id),
        output_schema=m.output,
    )
