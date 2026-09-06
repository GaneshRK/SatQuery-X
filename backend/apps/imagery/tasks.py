from __future__ import annotations

import logging
import os
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.geospatial.ingestion import (
    extract_metadata_from_bytes,
    validate_image_pair_compatibility,
)
from apps.imagery.models import ImageAsset, ImagePair

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    """
    Convert a value to float only when it is genuinely available and finite.
    """
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not result == result:  # NaN
        return None

    if result in (float("inf"), float("-inf")):
        return None

    return result


def _merge_provenance(
    existing: dict[str, Any] | None,
    update: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge provenance without destroying previously recorded information.
    """
    result: dict[str, Any] = {}

    if isinstance(existing, dict):
        result.update(existing)

    result.update(update)

    return result


def _apply_ingestion_metadata(
    asset: ImageAsset,
    metadata: Any,
) -> None:
    """
    Copy metadata extracted from the actual source file into ImageAsset.

    This function intentionally does NOT invent:
    - CRS
    - coordinates
    - bounds
    - resolution
    - sensor
    - acquisition date
    - cloud cover
    """

    asset.width = (
        int(metadata.width)
        if metadata.width is not None
        else None
    )

    asset.height = (
        int(metadata.height)
        if metadata.height is not None
        else None
    )

    asset.band_count = (
        int(metadata.band_count)
        if metadata.band_count is not None
        else None
    )

    asset.dtype = (
        str(metadata.dtype)
        if metadata.dtype
        else None
    )

    asset.crs = (
        str(metadata.crs)
        if metadata.crs
        else None
    )

    asset.affine_transform = metadata.affine_transform

    asset.bounds_native = metadata.bounds_native

    asset.bounds_wgs84 = metadata.bounds_wgs84

    asset.resolution_m = _safe_float(
        metadata.resolution_m
    )

    detected_sensor = (
        str(metadata.sensor).strip()
        if getattr(metadata, "sensor", None)
        else "UNKNOWN"
    )

    detected_modality = (
        str(metadata.modality).strip()
        if getattr(metadata, "modality", None)
        else "UNKNOWN"
    )

    # Only use values accepted by the database vocabulary.
    valid_sensors = {
        choice[0]
        for choice in ImageAsset.SENSOR_CHOICES
    }

    valid_modalities = {
        choice[0]
        for choice in ImageAsset.MODALITY_CHOICES
    }

    asset.sensor = (
        detected_sensor
        if detected_sensor in valid_sensors
        else "UNKNOWN"
    )

    asset.modality = (
        detected_modality
        if detected_modality in valid_modalities
        else "UNKNOWN"
    )

    asset.acquisition_date = getattr(
        metadata,
        "acquisition_date",
        None,
    )

    asset.cloud_cover_pct = _safe_float(
        getattr(metadata, "cloud_cover_pct", None)
    )

    # A raster is georeferenced only when the ingestion layer explicitly
    # establishes that fact.
    asset.is_georeferenced = bool(
        getattr(metadata, "is_georeferenced", False)
        and asset.crs
        and asset.affine_transform
    )

    validation_report = getattr(
        metadata,
        "validation_report",
        None,
    )

    if isinstance(validation_report, dict):
        asset.validation_report = validation_report
    else:
        asset.validation_report = {}

    asset.provenance = _merge_provenance(
        asset.provenance,
        {
            "ingestion": {
                "metadata_source": "actual_file_inspection",
                "georeferenced": asset.is_georeferenced,
                "sensor_detected": asset.sensor,
                "modality_detected": asset.modality,
            }
        },
    )


def _generate_preview_artifacts(
    asset: ImageAsset,
    raw_bytes: bytes,
) -> dict[str, Any]:
    """
    Generate browser-facing preview artifacts.

    Scientific ingestion remains successful even if preview generation fails.

    Returns:
        {
            "success": bool,
            "preview_url": str | None,
            "artifact_error": str | None,
        }
    """

    try:
        from django.conf import settings

        from apps.imagery.services.artifacts import (
            register_imagery_artifacts,
        )
        from apps.imagery.services.preview import (
            generate_rgb_preview,
        )

        media_root = getattr(
            settings,
            "MEDIA_ROOT",
            None,
        )

        if not media_root:
            return {
                "success": False,
                "preview_url": None,
                "artifact_error": (
                    "MEDIA_ROOT is not configured."
                ),
            }

        preview_dir = os.path.join(
            media_root,
            "previews",
        )

        thumbnail_dir = os.path.join(
            media_root,
            "thumbnails",
        )

        os.makedirs(
            preview_dir,
            exist_ok=True,
        )

        os.makedirs(
            thumbnail_dir,
            exist_ok=True,
        )

        preview_path = os.path.join(
            preview_dir,
            f"{asset.id}_rgb.webp",
        )

        thumbnail_path = os.path.join(
            thumbnail_dir,
            f"{asset.id}_thumb.webp",
        )

        # Prefer the actual stored file when available.
        raster_source: Any

        try:
            stored_path = asset.file.path

            if stored_path and os.path.exists(stored_path):
                raster_source = stored_path
            else:
                raster_source = raw_bytes

        except (AttributeError, ValueError, OSError):
            raster_source = raw_bytes

        generate_rgb_preview(
            raster_source,
            preview_path,
            thumbnail_path,
        )

        # Register only artifacts that actually exist.
        register_imagery_artifacts(
            asset,
            preview_path,
            thumbnail_path,
        )

        try:
            relative_preview = os.path.relpath(
                preview_path,
                media_root,
            ).replace(os.sep, "/")

            media_url = getattr(
                settings,
                "MEDIA_URL",
                "/media/",
            )

            if not media_url.endswith("/"):
                media_url += "/"

            preview_url = (
                f"{media_url}"
                f"{relative_preview}"
            )

        except (TypeError, ValueError):
            preview_url = None

        return {
            "success": True,
            "preview_url": preview_url,
            "artifact_error": None,
        }

    except Exception as exc:
        logger.warning(
            "Preview generation failed for imagery %s: %s",
            asset.id,
            exc,
            exc_info=True,
        )

        return {
            "success": False,
            "preview_url": None,
            "artifact_error": str(exc),
        }


@shared_task(
    bind=True,
    max_retries=2,
    autoretry_for=(),
)
def ingest_image_task(
    self,
    image_id: str,
):
    """
    Validate and ingest a single ImageAsset.

    Processing stages:

        UPLOADED
            ↓
        VALIDATING
            ↓
        actual raster inspection
            ↓
        metadata persistence
            ↓
        optional preview generation
            ↓
        VALIDATED

    Preview failure does not invalidate scientifically valid source imagery.

    Actual ingestion failure results in FAILED and is retried by Celery.
    """

    asset: ImageAsset | None = None

    try:
        asset = ImageAsset.objects.select_related(
            "session"
        ).get(
            id=image_id
        )

        asset.processing_status = "VALIDATING"

        asset.validation_report = _merge_provenance(
            asset.validation_report,
            {
                "processing": {
                    "stage": "VALIDATING",
                }
            },
        )

        asset.save(
            update_fields=[
                "processing_status",
                "validation_report",
            ]
        )

        # --------------------------------------------------------------
        # Read the actual uploaded file.
        # --------------------------------------------------------------

        with asset.file.open("rb") as file_handle:
            raw_bytes = file_handle.read()

        if not raw_bytes:
            raise ValueError(
                "The imagery file contains no data."
            )

        # --------------------------------------------------------------
        # Extract actual metadata.
        # --------------------------------------------------------------

        metadata = extract_metadata_from_bytes(
            raw_bytes,
            asset.original_filename,
        )

        if metadata is None:
            raise ValueError(
                "The imagery ingestion engine returned no metadata."
            )

        # --------------------------------------------------------------
        # Persist scientific metadata atomically.
        # --------------------------------------------------------------

        with transaction.atomic():
            asset = ImageAsset.objects.select_for_update().get(
                id=image_id
            )

            _apply_ingestion_metadata(
                asset,
                metadata,
            )

            asset.processing_status = "VALIDATED"

            asset.validation_report = _merge_provenance(
                asset.validation_report,
                {
                    "processing": {
                        "stage": "METADATA_VALIDATED",
                    }
                },
            )

            asset.save()

        # --------------------------------------------------------------
        # Generate browser-facing artifacts.
        #
        # This is deliberately outside the scientific metadata transaction.
        # A preview failure must not erase valid ingestion metadata.
        # --------------------------------------------------------------

        preview_result = _generate_preview_artifacts(
            asset,
            raw_bytes,
        )

        if preview_result["preview_url"]:
            asset.preview_url = (
                preview_result["preview_url"]
            )

        asset.provenance = _merge_provenance(
            asset.provenance,
            {
                "processing": {
                    "ingestion_status": "VALIDATED",
                    "preview_generated": bool(
                        preview_result["success"]
                    ),
                }
            },
        )

        if preview_result["artifact_error"]:
            asset.validation_report = _merge_provenance(
                asset.validation_report,
                {
                    "warnings": [
                        *(
                            asset.validation_report.get(
                                "warnings",
                                []
                            )
                            if isinstance(
                                asset.validation_report,
                                dict
                            )
                            else []
                        ),
                        (
                            "Preview generation failed: "
                            f"{preview_result['artifact_error']}"
                        ),
                    ]
                },
            )

        asset.save(
            update_fields=[
                "preview_url",
                "provenance",
                "validation_report",
            ]
        )

        logger.info(
            "Imagery ingestion completed: %s",
            image_id,
        )

        return {
            "status": "VALIDATED",
            "image_id": str(image_id),
            "preview_generated": bool(
                preview_result["success"]
            ),
            "georeferenced": bool(
                asset.is_georeferenced
            ),
        }

    except Exception as exc:
        logger.exception(
            "Imagery ingestion failed for %s",
            image_id,
        )

        # --------------------------------------------------------------
        # Persist failure state.
        # --------------------------------------------------------------

        try:
            asset = ImageAsset.objects.get(
                id=image_id
            )

            existing_report = (
                asset.validation_report
                if isinstance(
                    asset.validation_report,
                    dict,
                )
                else {}
            )

            asset.processing_status = "FAILED"

            asset.validation_report = {
                **existing_report,
                "processing": {
                    "stage": "FAILED",
                },
                "errors": [
                    *existing_report.get(
                        "errors",
                        [],
                    ),
                    str(exc),
                ],
            }

            asset.provenance = _merge_provenance(
                asset.provenance,
                {
                    "processing": {
                        "ingestion_status": "FAILED",
                    }
                },
            )

            asset.save(
                update_fields=[
                    "processing_status",
                    "validation_report",
                    "provenance",
                ]
            )

        except Exception:
            logger.exception(
                "Could not persist ingestion failure for %s",
                image_id,
            )

        # --------------------------------------------------------------
        # Celery retry.
        #
        # Retry transient infrastructure/file-system problems, while
        # eventually leaving the asset in FAILED state.
        # --------------------------------------------------------------

        raise self.retry(
            exc=exc,
            countdown=3,
        )


@shared_task(
    bind=True,
    max_retries=2,
)
def check_pair_compatibility_task(
    self,
    pair_id: str,
):
    """
    Validate two imagery assets for the requested pair operation.

    Compatibility is determined from actual metadata and the geospatial
    compatibility engine. This task never assumes that two images are
    compatible merely because they are in the same session.
    """

    try:
        pair = ImagePair.objects.select_related(
            "image_a",
            "image_b",
            "session",
        ).get(
            id=pair_id
        )

        pair.compatibility_status = "PENDING"
        pair.save(
            update_fields=[
                "compatibility_status",
            ]
        )

        # --------------------------------------------------------------
        # Validate the actual pair.
        # --------------------------------------------------------------

        report = validate_image_pair_compatibility(
            pair.image_a,
            pair.image_b,
            pair.pair_type,
        )

        if not isinstance(report, dict):
            raise ValueError(
                "Pair compatibility engine returned an invalid result."
            )

        status_value = report.get(
            "status",
            "INCOMPATIBLE",
        )

        if status_value not in {
            "PENDING",
            "COMPATIBLE",
            "INCOMPATIBLE",
        }:
            status_value = "INCOMPATIBLE"

        # --------------------------------------------------------------
        # Persist result.
        # --------------------------------------------------------------

        pair.compatibility_status = status_value
        pair.compatibility_report = report

        # Coregistration is only needed when the compatibility engine
        # determines that spatial alignment is required.
        #
        # We do not automatically claim that coregistration is complete.
        requires_coregistration = bool(
            report.get(
                "requires_coregistration",
                False,
            )
        )

        if status_value == "INCOMPATIBLE":
            pair.coregistration_status = "NOT_NEEDED"

        elif requires_coregistration:
            pair.coregistration_status = "PENDING"

        else:
            pair.coregistration_status = "NOT_NEEDED"

        pair.save(
            update_fields=[
                "compatibility_status",
                "compatibility_report",
                "coregistration_status",
            ]
        )

        logger.info(
            "Imagery pair compatibility completed: %s",
            pair_id,
        )

        return {
            "status": status_value,
            "pair_id": str(pair_id),
            "compatibility_report": report,
            "coregistration_status": (
                pair.coregistration_status
            ),
        }

    except Exception as exc:
        logger.exception(
            "Imagery pair compatibility failed for %s",
            pair_id,
        )

        try:
            pair = ImagePair.objects.get(
                id=pair_id
            )

            existing_report = (
                pair.compatibility_report
                if isinstance(
                    pair.compatibility_report,
                    dict,
                )
                else {}
            )

            pair.compatibility_status = "INCOMPATIBLE"

            pair.compatibility_report = {
                **existing_report,
                "status": "INCOMPATIBLE",
                "error": str(exc),
            }

            pair.coregistration_status = "FAILED"

            pair.save(
                update_fields=[
                    "compatibility_status",
                    "compatibility_report",
                    "coregistration_status",
                ]
            )

        except Exception:
            logger.exception(
                "Could not persist pair failure for %s",
                pair_id,
            )

        raise self.retry(
            exc=exc,
            countdown=3,
        )