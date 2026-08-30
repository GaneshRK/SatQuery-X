"""Sessions API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.api.schemas import RasterMetadataResponse, SessionCreateResponse, SessionDetailResponse
from backend.db.store import get_datastore

router = APIRouter(prefix="/v1/sessions", tags=["Sessions"])


@router.post("", response_model=SessionCreateResponse, status_code=201)
async def create_session() -> SessionCreateResponse:
    store = get_datastore()
    session = store.create_session()
    return SessionCreateResponse(session_id=session.id, created_at=session.created_at)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_details(session_id: uuid.UUID) -> SessionDetailResponse:
    store = get_datastore()
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    image_responses = []
    for img in session.images:
        image_responses.append(
            RasterMetadataResponse(
                image_id=img.id,
                filename=img.filename,
                content_type=img.content_type,
                width=img.metadata.width,
                height=img.metadata.height,
                band_count=img.metadata.band_count,
                geo_referenced=img.metadata.geo_referenced,
                crs=img.metadata.crs,
                bounds_wgs84=img.metadata.bounds_wgs84,
                affine=img.metadata.affine,
                nodata=img.metadata.nodata,
                sensor_type=img.metadata.sensor_type,
                preview_url=f"/api/v1/sessions/{session_id}/images/{img.id}/preview",
                extra=img.metadata.extra,
            )
        )

    return SessionDetailResponse(
        session_id=session.id,
        created_at=session.created_at,
        images=image_responses,
        queries_count=len(session.queries),
    )
