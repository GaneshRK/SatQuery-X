"""Image upload, validation, CRS extraction, and preview endpoints."""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from backend.api.schemas import ImageUploadResponse, RasterMetadataResponse
from backend.config import get_settings
from backend.db.store import get_datastore
from backend.geospatial.ingestion import (
    ALLOWED_CONTENT_TYPES,
    detect_input_mode,
    generate_storage_key,
    parse_raster,
    raster_to_preview_png,
    validate_pair,
)
from backend.storage.s3 import ObjectStorage

router = APIRouter(prefix="/v1/sessions/{session_id}/images", tags=["Images"])


@router.post("", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_images(
    session_id: uuid.UUID,
    files: List[UploadFile] = File(...),
) -> ImageUploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")
    if len(files) > 2:
        raise HTTPException(status_code=400, detail="Maximum 2 images supported per session (single, cross-modal, or bi-temporal).")

    settings = get_settings()
    store = get_datastore()
    session = store.get_session(session_id)
    if not session:
        session = store.create_session(session_id)

    storage = ObjectStorage()
    uploaded_metas = []
    meta_objects = []

    for upload_file in files:
        data = await upload_file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File {upload_file.filename} exceeds maximum size limit of {settings.max_upload_size_mb}MB.",
            )
        if len(data) == 0:
            raise HTTPException(status_code=400, detail=f"File {upload_file.filename} is empty.")

        content_type = upload_file.content_type or "application/octet-stream"

        try:
            parsed_meta = parse_raster(data, upload_file.filename or "image.tif", content_type)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Corrupt or invalid image raster: {upload_file.filename}. Error: {str(exc)}",
            )

        storage_key = generate_storage_key(session_id, upload_file.filename or "image.tif")
        storage.upload_bytes(storage_key, data, content_type)

        try:
            preview_bytes = raster_to_preview_png(data, upload_file.filename or "image.tif")
        except Exception:
            preview_bytes = None

        image_id = uuid.uuid4()
        stored = store.add_image(
            session_id=session_id,
            filename=upload_file.filename or "image.tif",
            content_type=content_type,
            storage_key=storage_key,
            metadata=parsed_meta,
            raw_bytes=data,
            preview_bytes=preview_bytes,
            image_id=image_id,
        )

        meta_objects.append(parsed_meta)
        uploaded_metas.append(
            RasterMetadataResponse(
                image_id=stored.id,
                filename=stored.filename,
                content_type=stored.content_type,
                width=parsed_meta.width,
                height=parsed_meta.height,
                band_count=parsed_meta.band_count,
                geo_referenced=parsed_meta.geo_referenced,
                crs=parsed_meta.crs,
                bounds_wgs84=parsed_meta.bounds_wgs84,
                affine=parsed_meta.affine,
                nodata=parsed_meta.nodata,
                sensor_type=parsed_meta.sensor_type,
                preview_url=f"/api/v1/sessions/{session_id}/images/{stored.id}/preview",
                extra=parsed_meta.extra,
            )
        )

    # Detect modality mode and validate co-registration for paired images
    detected_mode = detect_input_mode(meta_objects)
    co_reg_valid = True
    validation_msg = f"Successfully ingested {len(uploaded_metas)} image(s). Mode: {detected_mode}."

    if len(meta_objects) == 2:
        pair_val = validate_pair(meta_objects[0], meta_objects[1])
        co_reg_valid = pair_val.valid
        validation_msg = pair_val.message

    return ImageUploadResponse(
        session_id=session_id,
        images=uploaded_metas,
        detected_mode=detected_mode,
        co_registration_valid=co_reg_valid,
        validation_message=validation_msg,
    )


@router.get("/{image_id}/preview")
async def get_image_preview(session_id: uuid.UUID, image_id: uuid.UUID) -> Response:
    store = get_datastore()
    img = store.get_image(image_id)
    if not img or img.session_id != session_id:
        raise HTTPException(status_code=404, detail="Image not found in this session.")

    if img.preview_bytes:
        return Response(content=img.preview_bytes, media_type="image/png")

    try:
        preview = raster_to_preview_png(img.raw_bytes, img.filename)
        return Response(content=preview, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {exc}")


@router.get("/{image_id}", response_model=RasterMetadataResponse)
async def get_image_metadata(session_id: uuid.UUID, image_id: uuid.UUID) -> RasterMetadataResponse:
    store = get_datastore()
    img = store.get_image(image_id)
    if not img or img.session_id != session_id:
        raise HTTPException(status_code=404, detail="Image not found in this session.")

    return RasterMetadataResponse(
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
