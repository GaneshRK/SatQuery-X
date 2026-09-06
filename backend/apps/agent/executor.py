"""
SatQuery-X Agent Executor
=========================

Master execution engine for the SatQuery-X agentic pipeline.

Responsibilities
----------------
- Resolve actual uploaded imagery.
- Resolve explicit query input assets and image pairs.
- Preserve actual map/session context.
- Execute planner-generated steps.
- Dispatch specialist models through the model registry.
- Dispatch GIS/tools through ToolRegistry.
- Preserve execution provenance.
- Detect identical bi-temporal observations.
- Prevent invalid area calculations.
- Build structured evidence.
- Maintain session memory.
- Publish best-effort progress events.

Scientific integrity
--------------------
This executor never fabricates:

- imagery
- coordinates
- AOIs
- dates
- sensors
- CRS
- measurements
- confidence
- cloud percentages
- raster values
- geographic areas

Missing evidence remains missing.

A non-georeferenced image is never assigned fabricated geographic
coordinates.

A single image cannot silently become a bi-temporal comparison.

The executor does not expose chain-of-thought.
Only concise execution metadata is persisted.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from django.conf import settings
from django.utils import timezone

from apps.agent.contracts import ModelInput, ModelOutput
from apps.agent.evidence_engine import EvidenceEngine
from apps.agent.registry import get_model_wrapper
from apps.agent.tool_registry import ToolRegistry
from apps.queries.models import ExecutionStep, Query


logger = logging.getLogger(__name__)


# ============================================================================
# Tool groups
# ============================================================================

MODEL_TOOL_NAMES = {
    "RS_VQA",
    "RS_CAPTION",
    "RS_GROUNDING",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "OPTICAL_SAR_FUSION",
}

SPECIAL_INTERNAL_TOOLS = {
    "CONTEXT_RESOLUTION",
    "IMAGE_PREPROCESSING",
    "AREA_QUANTIFIER",
    "EVIDENCE_VALIDATOR",
    "ANSWER_COMPOSER",
}

CHANGE_TOOLS = {
    "detect_change",
    "change_detection",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "change_vqa",
}

CROSS_MODAL_TOOLS = {
    "optical_sar_fusion",
    "OPTICAL_SAR_FUSION",
}

WEB_TOOLS = {
    "search_web",
}

SATELLITE_SEARCH_TOOLS = {
    "search_satellite_imagery",
}


# ============================================================================
# Redis
# ============================================================================

def _get_redis_client() -> Any:
    """
    Create a best-effort Redis client.

    Redis failure must never prevent scientific execution.
    """

    try:
        import redis

        redis_url = getattr(
            settings,
            "CELERY_BROKER_URL",
            os.getenv(
                "CELERY_BROKER_URL",
                "redis://localhost:6379/0",
            ),
        )

        return redis.from_url(
            redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )

    except Exception:
        return None


def publish_query_event(
    redis_client: Any,
    query_id: str,
    event_data: dict[str, Any],
) -> None:
    """
    Publish a concise execution event.

    Redis failure is intentionally ignored.
    """

    if redis_client is None:
        return

    try:
        redis_client.publish(
            f"query:{query_id}:events",
            json.dumps(
                _json_safe(event_data),
                ensure_ascii=False,
            ),
        )

    except Exception:
        logger.debug(
            "Unable to publish query event.",
            exc_info=True,
        )


# ============================================================================
# JSON serialization
# ============================================================================

def _json_safe(value: Any) -> Any:
    """
    Convert arbitrary runtime values into JSON-safe values.

    Binary data is represented by size and SHA-256 rather than persisted
    directly into query JSON.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not np.isfinite(value):
            return None
        return value

    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)

        return {
            "type": "binary",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    if isinstance(value, np.ndarray):
        return {
            "type": "numpy_array",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }

    if isinstance(value, np.generic):
        return _json_safe(value.item())

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass

    return str(value)


# ============================================================================
# File helpers
# ============================================================================

def _asset_file_path(asset: Any) -> str | None:
    """
    Resolve a local filesystem path when the configured storage backend
    exposes one.

    Remote storage is handled separately through file.read().
    """

    if asset is None:
        return None

    file_obj = getattr(
        asset,
        "file",
        None,
    )

    if file_obj is None:
        return None

    try:
        path = getattr(
            file_obj,
            "path",
            None,
        )

        if path:
            return str(path)

    except Exception:
        pass

    return None


def _read_asset_bytes(asset: Any) -> bytes | None:
    """
    Read actual stored asset bytes.

    This works with both local and storage-backed Django FileField objects.
    """

    if asset is None:
        return None

    file_obj = getattr(
        asset,
        "file",
        None,
    )

    if file_obj is None:
        return None

    try:
        if hasattr(file_obj, "open"):
            file_obj.open("rb")

        raw = file_obj.read()

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        if raw:
            return bytes(raw)

    except Exception:
        logger.debug(
            "Unable to read image bytes.",
            exc_info=True,
        )

    return None


# ============================================================================
# Raster loading
# ============================================================================

def _load_raster(
    asset: Any,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """
    Load an actual raster from the stored asset.

    GeoTIFF/raster data is loaded through rasterio when available.
    Ordinary images are loaded through PIL.

    No synthetic raster is ever created.
    """

    path = _asset_file_path(asset)

    if not path:
        return None, {}

    # ------------------------------------------------------------------
    # Rasterio / GeoTIFF / scientific raster
    # ------------------------------------------------------------------

    try:
        import rasterio

        with rasterio.open(path) as src:
            array = src.read()

            transform = src.transform

            metadata = {
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "dtype": (
                    str(src.dtypes[0])
                    if src.dtypes
                    else ""
                ),
                "crs": (
                    src.crs.to_string()
                    if src.crs
                    else None
                ),
                "affine_transform": (
                    list(transform)
                    if transform is not None
                    else None
                ),
                "bounds": (
                    list(src.bounds)
                    if src.bounds is not None
                    else None
                ),
                "is_georeferenced": bool(
                    src.crs is not None
                    and transform is not None
                    and not transform.is_identity
                ),
                "nodata": src.nodata,
                "driver": src.driver,
            }

            if array.ndim == 3:
                array = np.transpose(
                    array,
                    (1, 2, 0),
                )

            return array, metadata

    except Exception:
        logger.debug(
            "Rasterio loading failed for %s.",
            path,
            exc_info=True,
        )

    # ------------------------------------------------------------------
    # Ordinary image
    # ------------------------------------------------------------------

    try:
        with Image.open(path) as image:
            array = np.array(image)

            if array.ndim == 2:
                array = array[..., np.newaxis]

            return array, {
                "width": array.shape[1],
                "height": array.shape[0],
                "count": (
                    array.shape[2]
                    if array.ndim == 3
                    else 1
                ),
                "dtype": str(array.dtype),
                "crs": None,
                "affine_transform": None,
                "bounds": None,
                "is_georeferenced": False,
            }

    except Exception:
        logger.debug(
            "PIL loading failed for %s.",
            path,
            exc_info=True,
        )

    return None, {}


# ============================================================================
# Asset metadata
# ============================================================================

def _asset_metadata(
    asset: Any,
    raster_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:

    raster_metadata = (
        raster_metadata
        if isinstance(raster_metadata, dict)
        else {}
    )

    file_path = _asset_file_path(asset)

    file_crs = raster_metadata.get("crs")

    db_crs = getattr(
        asset,
        "crs",
        None,
    )

    file_bounds = raster_metadata.get("bounds")

    db_bounds = getattr(
        asset,
        "bounds_wgs84",
        None,
    )

    file_transform = raster_metadata.get(
        "affine_transform"
    )

    db_transform = getattr(
        asset,
        "affine_transform",
        None,
    )

    georeferenced_from_file = bool(
        raster_metadata.get(
            "is_georeferenced"
        )
    )

    georeferenced_from_db = bool(
        db_crs
        and (
            file_bounds
            or db_bounds
            or db_transform
        )
    )

    asset_id = getattr(
        asset,
        "id",
        None,
    )

    original_filename = getattr(
        asset,
        "original_filename",
        None,
    )

    filename = getattr(
        asset,
        "filename",
        None,
    )

    if not filename:
        file_obj = getattr(
            asset,
            "file",
            None,
        )

        try:
            filename = getattr(
                file_obj,
                "name",
                None,
            )
        except Exception:
            filename = None

    return {
        "asset_id": (
            str(asset_id)
            if asset_id
            else None
        ),

        "name": getattr(
            asset,
            "name",
            None,
        ),

        "filename": (
            filename
            or original_filename
        ),

        "original_filename": original_filename,

        "file_path": file_path,

        "sensor": getattr(
            asset,
            "sensor",
            None,
        ),

        "satellite": getattr(
            asset,
            "satellite",
            None,
        ),

        "platform": getattr(
            asset,
            "platform",
            None,
        ),

        "modality": getattr(
            asset,
            "modality",
            None,
        ),

        "acquisition_date": _json_safe(
            getattr(
                asset,
                "acquisition_date",
                None,
            )
        ),

        "resolution_m": getattr(
            asset,
            "resolution_m",
            None,
        ),

        "cloud_cover_pct": getattr(
            asset,
            "cloud_cover_pct",
            None,
        ),

        "crs": (
            file_crs
            or db_crs
        ),

        "affine_transform": (
            file_transform
            or db_transform
        ),

        "bounds_wgs84": (
            db_bounds
            or file_bounds
        ),

        "is_georeferenced": (
            georeferenced_from_file
            or georeferenced_from_db
        ),

        "width": (
            raster_metadata.get("width")
            or getattr(
                asset,
                "width",
                None,
            )
        ),

        "height": (
            raster_metadata.get("height")
            or getattr(
                asset,
                "height",
                None,
            )
        ),

        "band_count": (
            raster_metadata.get("count")
            or getattr(
                asset,
                "band_count",
                None,
            )
        ),

        "dtype": (
            raster_metadata.get("dtype")
            or getattr(
                asset,
                "dtype",
                None,
            )
        ),

        "nodata": raster_metadata.get(
            "nodata"
        ),

        "driver": raster_metadata.get(
            "driver"
        ),

        "provenance": (
            getattr(
                asset,
                "provenance",
                {},
            )
            or {}
        ),
    }


# ============================================================================
# Asset resolution
# ============================================================================

def _query_input_assets(query: Query) -> list[Any]:
    """
    Resolve Query.input_assets when the field exists.

    The method is intentionally defensive so the executor remains compatible
    with older query objects during migration.
    """

    try:
        manager = getattr(
            query,
            "input_assets",
            None,
        )

        if manager is None:
            return []

        return list(
            manager.all()
        )

    except Exception:
        logger.debug(
            "Unable to resolve Query.input_assets.",
            exc_info=True,
        )

        return []


def _resolve_image_pair_assets(
    image_pair: Any,
) -> list[Any]:

    if image_pair is None:
        return []

    result = []

    image_a = getattr(
        image_pair,
        "image_a",
        None,
    )

    image_b = getattr(
        image_pair,
        "image_b",
        None,
    )

    if image_a is not None:
        result.append(image_a)

    if image_b is not None:
        result.append(image_b)

    return result


def _deduplicate_assets(
    assets: list[Any],
) -> list[Any]:

    result = []
    seen = set()

    for asset in assets:

        asset_id = getattr(
            asset,
            "id",
            None,
        )

        key = (
            str(asset_id)
            if asset_id is not None
            else id(asset)
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(asset)

    return result


def _resolve_assets(
    query: Query,
    image_assets: list[Any] | None = None,
    image_pair: Any | None = None,
) -> list[Any]:
    """
    Resolve actual query inputs.

    Priority:

    1. Explicit ImagePair.
    2. Explicit image_assets passed by executor compatibility API.
    3. Query.input_assets M2M.
    4. Legacy Query.image.
    5. Legacy Query.image_pair.
    6. Session imagery only when no explicit query inputs exist.

    This prevents unrelated session imagery from silently entering analysis.
    """

    # --------------------------------------------------------------
    # Explicit pair.
    # --------------------------------------------------------------

    if image_pair is not None:
        return _deduplicate_assets(
            _resolve_image_pair_assets(
                image_pair
            )
        )

    # --------------------------------------------------------------
    # Explicit asset list.
    # --------------------------------------------------------------

    if image_assets:
        return _deduplicate_assets(
            list(image_assets)
        )

    # --------------------------------------------------------------
    # Query M2M assets.
    # --------------------------------------------------------------

    query_assets = _query_input_assets(
        query
    )

    if query_assets:
        return _deduplicate_assets(
            query_assets
        )

    # --------------------------------------------------------------
    # Legacy single image.
    # --------------------------------------------------------------

    query_image = getattr(
        query,
        "image",
        None,
    )

    if query_image is not None:
        return [query_image]

    # --------------------------------------------------------------
    # Legacy pair.
    # --------------------------------------------------------------

    query_pair = getattr(
        query,
        "image_pair",
        None,
    )

    if query_pair is not None:
        pair_assets = _resolve_image_pair_assets(
            query_pair
        )

        if pair_assets:
            return _deduplicate_assets(
                pair_assets
            )

    # --------------------------------------------------------------
    # Session assets.
    #
    # This is only a fallback. The executor must not automatically use
    # unrelated session imagery when explicit query inputs exist.
    # --------------------------------------------------------------

    session = getattr(
        query,
        "session",
        None,
    )

    if session is not None:

        for manager_name in (
            "imagery_assets",
            "images",
        ):

            try:
                manager = getattr(
                    session,
                    manager_name,
                    None,
                )

                if manager is not None:
                    assets = list(
                        manager.all()
                    )

                    if assets:
                        return _deduplicate_assets(
                            assets
                        )

            except Exception:
                logger.debug(
                    "Unable to resolve session imagery.",
                    exc_info=True,
                )

    return []


# ============================================================================
# Imagery context
# ============================================================================

def _build_imagery_context(
    assets: list[Any],
) -> dict[str, Any]:

    records = []
    paths = []
    byte_values = []
    arrays = []

    load_reports = []

    for index, asset in enumerate(assets):

        path = _asset_file_path(asset)

        raw_bytes = _read_asset_bytes(asset)

        raster = None
        raster_metadata = {}

        if path:
            raster, raster_metadata = _load_raster(
                asset
            )
        else:
            # ----------------------------------------------------------
            # Remote storage may not expose .path.
            #
            # We can still pass the actual bytes to models. We do not
            # invent filesystem paths.
            # ----------------------------------------------------------

            if raw_bytes is not None:
                try:
                    with Image.open(
                        io.BytesIO(raw_bytes)
                    ) as image:

                        array = np.array(image)

                        if array.ndim == 2:
                            array = array[
                                ...,
                                np.newaxis,
                            ]

                        raster = array

                        raster_metadata = {
                            "width": array.shape[1],
                            "height": array.shape[0],
                            "count": (
                                array.shape[2]
                                if array.ndim == 3
                                else 1
                            ),
                            "dtype": str(
                                array.dtype
                            ),
                            "crs": None,
                            "affine_transform": None,
                            "bounds": None,
                            "is_georeferenced": False,
                        }

                except Exception:
                    logger.debug(
                        "Unable to decode remote image bytes.",
                        exc_info=True,
                    )

        if path:
            paths.append(path)

        if raw_bytes is not None:
            byte_values.append(raw_bytes)

        if raster is not None:
            arrays.append(raster)

        records.append(
            _asset_metadata(
                asset,
                raster_metadata,
            )
        )

        load_reports.append(
            {
                "asset_index": index,
                "asset_id": str(
                    getattr(
                        asset,
                        "id",
                        "",
                    )
                ),
                "path_available": bool(path),
                "bytes_available": raw_bytes is not None,
                "raster_available": raster is not None,
                "georeferenced": bool(
                    raster_metadata.get(
                        "is_georeferenced"
                    )
                ),
            }
        )

    return {
        "assets": records,
        "paths": paths,
        "bytes": byte_values,
        "arrays": arrays,
        "load_reports": load_reports,
    }


# ============================================================================
# Map/session context
# ============================================================================

def _get_session_context(
    query: Query,
) -> dict[str, Any]:

    session = getattr(
        query,
        "session",
        None,
    )

    if session is None:
        return {}

    context = getattr(
        session,
        "conversation_context",
        {},
    )

    return (
        dict(context)
        if isinstance(
            context,
            dict,
        )
        else {}
    )


def _extract_map_context(
    session_context: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(
        session_context,
        dict,
    ):
        return {}

    result = {}

    aliases = {
        "active_map_pin": "map_pin",
        "active_pin": "map_pin",
        "selected_pin": "map_pin",
        "viewport": "current_viewport",
    }

    for key in (
        "map_pin",
        "active_map_pin",
        "active_pin",
        "selected_pin",
        "active_aoi",
        "selected_aoi",
        "current_viewport",
        "viewport",
        "location",
        "spatial_context",
        "active_map_context",
    ):

        value = session_context.get(key)

        if value is None:
            continue

        if (
            isinstance(value, str)
            and not value.strip()
        ):
            continue

        target_key = aliases.get(
            key,
            key,
        )

        if target_key not in result:
            result[target_key] = value

    return result


# ============================================================================
# Preprocessing
# ============================================================================

def _preprocess_imagery(
    imagery_context: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:

    arrays = imagery_context.get(
        "arrays",
        [],
    )

    if not arrays:
        return (
            imagery_context,
            {
                "status": "skipped",
                "reason": "no_loadable_raster",
            },
        )

    try:
        from apps.geospatial.preprocessing import (
            clean_satellite_imagery,
        )

    except Exception:
        return (
            imagery_context,
            {
                "status": "skipped",
                "reason": (
                    "preprocessing_module_unavailable"
                ),
            },
        )

    cleaned_arrays = []
    reports = []

    assets = imagery_context.get(
        "assets",
        [],
    )

    for index, array in enumerate(arrays):

        metadata = (
            assets[index]
            if index < len(assets)
            else {}
        )

        sensor = metadata.get(
            "sensor"
        )

        modality = metadata.get(
            "modality"
        )

        kwargs = {}

        if sensor:
            kwargs["sensor"] = sensor

        if modality:
            kwargs["modality"] = modality

        try:
            cleaned, quality_report = (
                clean_satellite_imagery(
                    array,
                    **kwargs,
                )
            )

            cleaned_arrays.append(
                cleaned
            )

            reports.append(
                _json_safe(
                    quality_report
                )
            )

        except TypeError:

            if sensor or modality:

                try:
                    cleaned, quality_report = (
                        clean_satellite_imagery(
                            array,
                            sensor,
                            modality,
                        )
                    )

                    cleaned_arrays.append(
                        cleaned
                    )

                    reports.append(
                        _json_safe(
                            quality_report
                        )
                    )

                    continue

                except Exception:
                    logger.warning(
                        "Preprocessing failed for asset %s.",
                        index,
                        exc_info=True,
                    )

            cleaned_arrays.append(
                array
            )

            reports.append(
                {
                    "status": "skipped",
                    "reason": (
                        "preprocessing_signature_incompatible"
                    ),
                }
            )

        except Exception:
            logger.warning(
                "Preprocessing failed for asset %s.",
                index,
                exc_info=True,
            )

            cleaned_arrays.append(
                array
            )

            reports.append(
                {
                    "status": "failed",
                    "reason": (
                        "preprocessing_failed"
                    ),
                }
            )

    imagery_context["arrays"] = cleaned_arrays

    return (
        imagery_context,
        {
            "status": "completed",
            "reports": reports,
        },
    )


# ============================================================================
# Duplicate detection
# ============================================================================

def _observations_identical(
    assets: list[Any],
    imagery_context: dict[str, Any],
) -> bool:
    """
    Detect exact identical observations.

    This deliberately detects exact equality rather than claiming that
    visually similar images have no change.
    """

    if len(assets) < 2:
        return False

    records = imagery_context.get(
        "assets",
        [],
    )

    if len(records) < 2:
        return False

    raw_values = imagery_context.get(
        "bytes",
        [],
    )

    if len(raw_values) >= 2:

        digests = [
            hashlib.sha256(
                bytes(raw)
            ).hexdigest()
            for raw in raw_values
        ]

        if digests[0] == digests[1]:
            return True

    arrays = imagery_context.get(
        "arrays",
        [],
    )

    if len(arrays) >= 2:

        try:
            first = np.asarray(
                arrays[0]
            )

            second = np.asarray(
                arrays[1]
            )

            if (
                first.shape == second.shape
                and np.array_equal(
                    first,
                    second,
                )
            ):
                return True

        except Exception:
            pass

    return False


# ============================================================================
# ExecutionStep persistence
# ============================================================================

def _infer_agent_type(
    tool_name: str,
) -> str:

    if tool_name in MODEL_TOOL_NAMES:
        return "MODEL"

    if tool_name in SPECIAL_INTERNAL_TOOLS:
        return "INTERNAL"

    if tool_name in CROSS_MODAL_TOOLS:
        return "CROSS_MODAL"

    if tool_name in WEB_TOOLS:
        return "WEB"

    if tool_name in SATELLITE_SEARCH_TOOLS:
        return "SATELLITE"

    return "TOOL"


def _create_step(
    query: Query,
    step_number: int,
    tool_name: str,
    params: dict[str, Any],
    model_version: str = "1.0",
    input_refs: list[Any] | None = None,
) -> ExecutionStep:

    kwargs = {
        "query": query,
        "step_number": step_number,
        "tool_name": tool_name,
        "model_version": model_version,
        "parameters": _json_safe(params),
        "status": "RUNNING",
        "started_at": timezone.now(),
    }

    # New execution provenance fields are used when available.
    field_names = {
        field.name
        for field in ExecutionStep._meta.fields
    }

    if "agent_type" in field_names:
        kwargs["agent_type"] = _infer_agent_type(
            tool_name
        )

    if "input_refs" in field_names:
        kwargs["input_refs"] = _json_safe(
            input_refs or []
        )

    if "evidence_refs" in field_names:
        kwargs["evidence_refs"] = []

    if "retry_count" in field_names:
        kwargs["retry_count"] = 0

    return ExecutionStep.objects.create(
        **kwargs
    )


def _complete_step(
    step: ExecutionStep,
    result: dict[str, Any],
    latency_ms: int,
    status: str = "DONE",
    evidence_refs: list[Any] | None = None,
) -> None:

    step.status = status

    step.completed_at = timezone.now()

    step.latency_ms = latency_ms

    step.output_ref = _json_safe(
        result
    )

    update_fields = [
        "status",
        "completed_at",
        "latency_ms",
        "output_ref",
    ]

    field_names = {
        field.name
        for field in ExecutionStep._meta.fields
    }

    if "evidence_refs" in field_names:
        step.evidence_refs = _json_safe(
            evidence_refs or []
        )
        update_fields.append(
            "evidence_refs"
        )

    step.save(
        update_fields=update_fields
    )


def _fail_step(
    step: ExecutionStep,
    error: str,
    latency_ms: int,
) -> None:

    step.status = "FAILED"

    step.completed_at = timezone.now()

    step.latency_ms = latency_ms

    step.error = str(error)

    step.save(
        update_fields=[
            "status",
            "completed_at",
            "latency_ms",
            "error",
        ]
    )


def _skip_step(
    query: Query,
    step_number: int,
    tool_name: str,
    reason: str,
) -> ExecutionStep:

    now = timezone.now()

    kwargs = {
        "query": query,
        "step_number": step_number,
        "tool_name": tool_name,
        "model_version": "1.0",
        "parameters": {
            "skip_reason": reason,
        },
        "status": "SKIPPED",
        "started_at": now,
        "completed_at": now,
        "output_ref": {
            "status": "skipped",
            "reason": reason,
        },
    }

    field_names = {
        field.name
        for field in ExecutionStep._meta.fields
    }

    if "agent_type" in field_names:
        kwargs["agent_type"] = _infer_agent_type(
            tool_name
        )

    if "input_refs" in field_names:
        kwargs["input_refs"] = []

    if "evidence_refs" in field_names:
        kwargs["evidence_refs"] = []

    if "retry_count" in field_names:
        kwargs["retry_count"] = 0

    return ExecutionStep.objects.create(
        **kwargs
    )


# ============================================================================
# Plan helpers
# ============================================================================

def _plan_steps(
    query: Query,
) -> list[dict[str, Any]]:

    plan = (
        getattr(
            query,
            "structured_plan",
            None,
        )
        or getattr(
            query,
            "plan",
            None,
        )
        or {}
    )

    if not isinstance(
        plan,
        dict,
    ):
        return []

    steps = plan.get("steps")

    if not isinstance(
        steps,
        list,
    ):
        steps = plan.get(
            "execution_plan",
            {},
        )

    if isinstance(
        steps,
        dict,
    ):
        steps = steps.get(
            "steps",
            [],
        )

    if not isinstance(
        steps,
        list,
    ):
        return []

    return [
        item
        for item in steps
        if isinstance(
            item,
            dict,
        )
    ]


def _step_is_optional(
    item: dict[str, Any],
) -> bool:

    return bool(
        item.get(
            "optional",
            False,
        )
    )


def _required_step_failures(
    steps: list[dict[str, Any]],
    step_outputs: dict[str, Any],
) -> list[dict[str, Any]]:

    failures = []

    for item in steps:

        if _step_is_optional(item):
            continue

        step_number = item.get(
            "step"
        )

        output = step_outputs.get(
            f"step_{step_number}"
        )

        if not isinstance(
            output,
            dict,
        ):
            failures.append(
                {
                    "step": step_number,
                    "tool": item.get("tool"),
                    "reason": (
                        "No execution output was produced."
                    ),
                }
            )

            continue

        status = str(
            output.get(
                "status",
                "",
            )
        ).lower()

        if status in {
            "error",
            "failed",
        }:
            failures.append(
                {
                    "step": step_number,
                    "tool": item.get("tool"),
                    "reason": output.get(
                        "error",
                        "Execution failed.",
                    ),
                }
            )

    return failures


# ============================================================================
# Model execution
# ============================================================================

def _execute_model(
    model_id: str,
    query: Query,
    imagery_context: dict[str, Any],
    params: dict[str, Any],
    last_change_mask: Any = None,
) -> dict[str, Any]:

    wrapper = get_model_wrapper(
        model_id
    )

    if wrapper is None:
        raise ValueError(
            f"Model '{model_id}' is not registered."
        )

    model_input = ModelInput(
        model_id=model_id,
        image_paths=list(
            imagery_context.get(
                "paths",
                [],
            )
        ),
        image_bytes=list(
            imagery_context.get(
                "bytes",
                [],
            )
        ),
        question=query.text,
        text_prompt=params.get(
            "prompt",
            query.text,
        ),
        change_mask=last_change_mask,
        params=params,
        context={
            "query_id": str(query.id),
            "image_metadata": (
                imagery_context.get(
                    "assets",
                    [],
                )
            ),
        },
    )

    model_output = wrapper.predict(
        model_input
    )

    if isinstance(
        model_output,
        ModelOutput,
    ):
        output = model_output

    elif isinstance(
        model_output,
        dict,
    ):
        output = ModelOutput(
            model_id=model_id,
            version=str(
                model_output.get(
                    "version",
                    "unknown",
                )
            ),
            task=str(
                model_output.get(
                    "task",
                    "",
                )
            ),
            answer=model_output.get(
                "answer"
            ),
            caption=model_output.get(
                "caption"
            ),
            confidence=model_output.get(
                "confidence"
            ),
            boxes=model_output.get(
                "boxes"
            ),
            change_mask=model_output.get(
                "change_mask"
            ),
            overlay=model_output.get(
                "overlay"
            ),
            raw=model_output.get(
                "raw"
            ),
            latency_ms=model_output.get(
                "latency_ms"
            ),
            status=str(
                model_output.get(
                    "status",
                    "ok",
                )
            ),
            error=model_output.get(
                "error"
            ),
        )

    else:
        raise TypeError(
            f"Model '{model_id}' returned unsupported output type."
        )

    result = {
        "status": output.status,
        "model_id": output.model_id,
        "version": output.version,
        "task": output.task,
        "answer": output.answer,
        "caption": output.caption,
        "confidence": output.confidence,
        "boxes": output.boxes,
        "change_mask": output.change_mask,
        "overlay": output.overlay,
        "raw": output.raw,
        "latency_ms": output.latency_ms,
        "error": output.error,
    }

    # Preserve additional structured evidence returned by a model if
    # ModelOutput.raw contains it. No values are invented here.
    if isinstance(
        output.raw,
        dict,
    ):
        for key in (
            "features",
            "measurements",
            "observations",
            "evidence",
            "regions",
            "geojson",
            "crs",
            "transform",
            "change_percentage",
            "changed_area_m2",
            "changed_area_hectares",
            "changed_area_km2",
            "verification_status",
        ):
            if key in output.raw:
                result[key] = output.raw[key]

    return _json_safe(
        result
    )


# ============================================================================
# Tool argument construction
# ============================================================================

def _primary_metadata(
    imagery_context: dict[str, Any],
) -> dict[str, Any]:

    assets = imagery_context.get(
        "assets",
        [],
    )

    if (
        isinstance(assets, list)
        and assets
        and isinstance(
            assets[0],
            dict,
        )
    ):
        return assets[0]

    return {}


def _build_tool_kwargs(
    tool_name: str,
    params: dict[str, Any],
    query: Query,
    imagery_context: dict[str, Any],
    map_context: dict[str, Any],
    step_outputs: dict[str, Any],
    last_change_mask: Any,
) -> dict[str, Any]:

    arrays = imagery_context.get(
        "arrays",
        [],
    )

    primary_array = (
        arrays[0]
        if arrays
        else None
    )

    metadata = _primary_metadata(
        imagery_context
    )

    kwargs = dict(params)

    kwargs.setdefault(
        "raster_array",
        primary_array,
    )

    kwargs.setdefault(
        "raster_arrays",
        arrays,
    )

    kwargs.setdefault(
        "image_paths",
        imagery_context.get(
            "paths",
            [],
        ),
    )

    kwargs.setdefault(
        "image_bytes",
        imagery_context.get(
            "bytes",
            [],
        ),
    )

    kwargs.setdefault(
        "image_metadata",
        imagery_context.get(
            "assets",
            [],
        ),
    )

    kwargs.setdefault(
        "bounds_wgs84",
        metadata.get(
            "bounds_wgs84"
        ),
    )

    kwargs.setdefault(
        "affine_transform",
        metadata.get(
            "affine_transform"
        ),
    )

    kwargs.setdefault(
        "crs",
        metadata.get(
            "crs"
        ),
    )

    kwargs.setdefault(
        "aoi_geometry",
        (
            map_context.get(
                "aoi_geometry"
            )
            or map_context.get(
                "geometry"
            )
        ),
    )

    kwargs.setdefault(
        "map_context",
        map_context,
    )

    kwargs.setdefault(
        "session_context",
        _get_session_context(
            query
        ),
    )

    kwargs.setdefault(
        "step_outputs",
        step_outputs,
    )

    kwargs.setdefault(
        "change_mask",
        last_change_mask,
    )

    kwargs.setdefault(
        "query_id",
        str(query.id),
    )

    return kwargs


# ============================================================================
# Area quantification
# ============================================================================

def _execute_area_quantifier(
    change_mask: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:

    if change_mask is None:
        return {
            "status": "insufficient_evidence",
            "error": (
                "No change mask is available for area quantification."
            ),
        }

    crs = metadata.get(
        "crs"
    )

    transform = metadata.get(
        "affine_transform"
    )

    bounds = metadata.get(
        "bounds_wgs84"
    )

    if not crs:
        return {
            "status": "insufficient_evidence",
            "error": (
                "Area quantification requires a valid CRS."
            ),
        }

    if not transform:
        return {
            "status": "insufficient_evidence",
            "error": (
                "Area quantification requires a valid affine transform."
            ),
        }

    try:
        from apps.geospatial.math import (
            polygonize_mask_to_geojson,
            quantify_mask_area,
        )

    except Exception as exc:
        return {
            "status": "error",
            "error": (
                "Geospatial quantification module unavailable: "
                f"{exc}"
            ),
        }

    # ------------------------------------------------------------------
    # Convert mask.
    # ------------------------------------------------------------------

    try:

        if isinstance(
            change_mask,
            (bytes, bytearray),
        ):
            mask_array = np.array(
                Image.open(
                    io.BytesIO(
                        bytes(change_mask)
                    )
                ).convert("L")
            )

        elif isinstance(
            change_mask,
            np.ndarray,
        ):
            mask_array = np.asarray(
                change_mask
            )

        elif isinstance(
            change_mask,
            list,
        ):
            mask_array = np.asarray(
                change_mask
            )

        else:
            return {
                "status": "insufficient_evidence",
                "error": (
                    "Unsupported change-mask representation."
                ),
            }

    except Exception as exc:
        return {
            "status": "error",
            "error": (
                "Unable to decode change mask: "
                f"{exc}"
            ),
        }

    if mask_array.ndim > 2:
        mask_array = np.squeeze(
            mask_array
        )

    if mask_array.ndim != 2:
        return {
            "status": "insufficient_evidence",
            "error": (
                "Change mask must resolve to a two-dimensional raster."
            ),
        }

    mask_array = (
        mask_array > 0
    ).astype(
        np.uint8
    )

    if mask_array.size == 0:
        return {
            "status": "insufficient_evidence",
            "error": (
                "Change mask is empty."
            ),
        }

    if not np.any(mask_array):
        return {
            "status": "completed",
            "changed_pixel_count": 0,
            "value": 0,
            "features": [],
        }

    try:
        result = quantify_mask_area(
            mask_array,
            transform,
            crs,
            bounds,
        )

        result = (
            result
            if isinstance(
                result,
                dict,
            )
            else {
                "value": result
            }
        )

    except Exception as exc:
        return {
            "status": "error",
            "error": (
                "Area quantification failed: "
                f"{exc}"
            ),
        }

    # ------------------------------------------------------------------
    # Polygonization.
    # ------------------------------------------------------------------

    try:
        features = polygonize_mask_to_geojson(
            mask_array,
            transform,
            crs,
            bounds,
            class_label="detected_change",
        )

        if isinstance(
            features,
            list,
        ):
            result["features"] = _json_safe(
                features
            )

    except TypeError:

        try:
            features = polygonize_mask_to_geojson(
                mask_array,
                transform,
                crs,
                bounds,
                class_label="detected_change",
                confidence=None,
            )

            if isinstance(
                features,
                list,
            ):
                result["features"] = _json_safe(
                    features
                )

        except Exception:
            logger.debug(
                "Polygonization unavailable.",
                exc_info=True,
            )

    except Exception:
        logger.debug(
            "Polygonization failed.",
            exc_info=True,
        )

    result["status"] = result.get(
        "status",
        "completed",
    )

    return _json_safe(
        result
    )


# ============================================================================
# Model registration
# ============================================================================

def _is_registered_model(
    tool_name: str,
) -> bool:

    try:
        wrapper = get_model_wrapper(
            tool_name
        )

        return wrapper is not None

    except Exception:
        return False


# ============================================================================
# Result normalization
# ============================================================================

def _normalize_tool_result(
    result: Any,
) -> dict[str, Any]:

    if isinstance(
        result,
        ModelOutput,
    ):
        return _json_safe(
            {
                "status": result.status,
                "model_id": result.model_id,
                "version": result.version,
                "task": result.task,
                "answer": result.answer,
                "caption": result.caption,
                "confidence": result.confidence,
                "boxes": result.boxes,
                "change_mask": result.change_mask,
                "overlay": result.overlay,
                "raw": result.raw,
                "latency_ms": result.latency_ms,
                "error": result.error,
            }
        )

    if isinstance(
        result,
        dict,
    ):
        return _json_safe(
            result
        )

    if hasattr(
        result,
        "to_dict",
    ):
        try:
            converted = result.to_dict()

            if isinstance(
                converted,
                dict,
            ):
                return _json_safe(
                    converted
                )

        except Exception:
            pass

    return {
        "status": "completed",
        "value": _json_safe(
            result
        ),
    }


# ============================================================================
# Evidence validation
# ============================================================================

def _validate_step_evidence(
    step_outputs: dict[str, Any],
) -> dict[str, Any]:

    execution_results = {
        key: value
        for key, value in step_outputs.items()
        if not key.startswith("_")
    }

    try:
        report = EvidenceEngine.build_report(
            execution_results=execution_results
        )

    except Exception as exc:
        logger.warning(
            "Evidence validation failed.",
            exc_info=True,
        )

        return {
            "status": "error",
            "valid": False,
            "evidence_count": 0,
            "observation_count": 0,
            "measurement_count": 0,
            "limitations": [
                "Evidence engine failed to validate execution output."
            ],
            "validation": {
                "valid": False,
                "error": str(exc),
            },
        }

    validation = (
        report.validation
        if isinstance(
            report.validation,
            dict,
        )
        else {}
    )

    return {
        "status": report.status,
        "valid": validation.get(
            "valid",
            False,
        ),
        "evidence_count": len(
            report.evidence_items
        ),
        "observation_count": len(
            report.observations
        ),
        "measurement_count": len(
            report.measurements
        ),
        "limitations": list(
            report.limitations
        ),
        "validation": validation,
    }


# ============================================================================
# Grounded answer
# ============================================================================

def _compose_grounded_answer(
    query: Query,
    step_outputs: dict[str, Any],
    imagery_context: dict[str, Any],
    identical_observations: bool,
) -> str:

    if identical_observations:
        return (
            "The two supplied observations are identical at the "
            "available image-data level, so no meaningful difference "
            "can be established from this pair."
        )

    answers = []

    for key, result in step_outputs.items():

        if key.startswith("_"):
            continue

        if not isinstance(
            result,
            dict,
        ):
            continue

        answer = result.get(
            "answer"
        )

        caption = result.get(
            "caption"
        )

        if answer:
            answers.append(
                str(answer).strip()
            )

        elif caption:
            answers.append(
                str(caption).strip()
            )

        message = result.get(
            "message"
        )

        if (
            message
            and not answer
            and not caption
        ):
            answers.append(
                str(message).strip()
            )

    unique_answers = []

    for answer in answers:

        if (
            answer
            and answer not in unique_answers
        ):
            unique_answers.append(
                answer
            )

    if unique_answers:
        return "\n\n".join(
            unique_answers
        )

    evidence = EvidenceEngine.build_report(
        execution_results={
            key: value
            for key, value in step_outputs.items()
            if not key.startswith("_")
        }
    )

    if evidence.has_core_evidence():
        return (
            "The analysis produced evidence, but no textual answer "
            "was returned by the executed analysis component."
        )

    return (
        "I could not establish a grounded answer from the available "
        "inputs and executed analysis. No directly usable observation "
        "or quantitative measurement was returned."
    )


# ============================================================================
# Evidence graph
# ============================================================================

def _build_evidence_graph(
    query: Query,
    imagery_context: dict[str, Any],
    step_outputs: dict[str, Any],
    step_rows: list[ExecutionStep],
    map_context: dict[str, Any],
) -> dict[str, Any]:

    nodes = []
    edges = []

    # ------------------------------------------------------------------
    # Input nodes.
    # ------------------------------------------------------------------

    input_node_ids = []

    for index, asset in enumerate(
        imagery_context.get(
            "assets",
            [],
        )
    ):

        asset_id = (
            asset.get(
                "asset_id"
            )
            or f"asset_{index + 1}"
        )

        node_id = f"input_{asset_id}"

        input_node_ids.append(
            node_id
        )

        metadata = {}

        for key in (
            "asset_id",
            "sensor",
            "satellite",
            "platform",
            "modality",
            "acquisition_date",
            "crs",
            "bounds_wgs84",
            "is_georeferenced",
            "width",
            "height",
            "band_count",
            "dtype",
        ):

            value = asset.get(key)

            if value is not None:
                metadata[key] = value

        nodes.append(
            {
                "id": node_id,
                "type": "input",
                "label": (
                    asset.get("name")
                    or asset.get("filename")
                    or f"Imagery {index + 1}"
                ),
                "metadata": _json_safe(
                    metadata
                ),
            }
        )

    # ------------------------------------------------------------------
    # Step nodes.
    # ------------------------------------------------------------------

    for row in step_rows:

        step_id = f"step_{row.step_number}"

        step_metadata = {
            "status": row.status,
            "latency_ms": row.latency_ms,
            "model_version": row.model_version,
        }

        if hasattr(
            row,
            "agent_type",
        ):
            step_metadata["agent_type"] = (
                row.agent_type
            )

        nodes.append(
            {
                "id": step_id,
                "type": "execution",
                "label": row.tool_name,
                "metadata": _json_safe(
                    step_metadata
                ),
            }
        )

        for input_node_id in input_node_ids:
            edges.append(
                {
                    "from": input_node_id,
                    "to": step_id,
                    "relation": "input_to_execution",
                }
            )

    # ------------------------------------------------------------------
    # Output/evidence nodes.
    # ------------------------------------------------------------------

    for key, result in step_outputs.items():

        if key.startswith("_"):
            continue

        if not isinstance(
            result,
            dict,
        ):
            continue

        step_number = key.replace(
            "step_",
            "",
        )

        step_id = f"step_{step_number}"
        output_id = f"output_{step_number}"

        metadata = {
            "status": result.get("status"),
            "confidence": result.get("confidence"),
            "has_answer": bool(
                result.get("answer")
            ),
            "has_change_mask": (
                result.get("change_mask")
                is not None
            ),
            "has_features": isinstance(
                result.get("features"),
                list,
            ),
            "has_measurements": isinstance(
                result.get("measurements"),
                (list, dict),
            ),
            "has_observations": isinstance(
                result.get("observations"),
                (list, dict),
            ),
        }

        nodes.append(
            {
                "id": output_id,
                "type": "evidence",
                "label": (
                    result.get("task")
                    or result.get("status")
                    or "Analysis output"
                ),
                "metadata": _json_safe(
                    metadata
                ),
            }
        )

        edges.append(
            {
                "from": step_id,
                "to": output_id,
                "relation": "produced",
            }
        )

    graph = {
        "query_id": str(query.id),
        "nodes": nodes,
        "edges": edges,
    }

    if map_context:
        graph["spatial_context"] = _json_safe(
            map_context
        )

    return graph


# ============================================================================
# Session memory
# ============================================================================

def _update_session_memory(
    query: Query,
    answer: str | None,
    confidence: float | None,
    evidence_graph: dict[str, Any],
) -> None:

    session = getattr(
        query,
        "session",
        None,
    )

    if session is None:
        return

    try:

        history = list(
            getattr(
                session,
                "conversation_history",
                [],
            )
            or []
        )

        history.append(
            {
                "query_id": str(
                    query.id
                ),
                "text": query.text,
                "answer": answer,
                "task": getattr(
                    query,
                    "detected_task",
                    None,
                ),
                "confidence": confidence,
                "timestamp": timezone.now().isoformat(),
            }
        )

        session.conversation_history = (
            history[-20:]
        )

        context = dict(
            getattr(
                session,
                "conversation_context",
                {},
            )
            or {}
        )

        context["last_query_id"] = str(
            query.id
        )

        context["last_intent"] = getattr(
            query,
            "detected_task",
            None,
        )

        context["last_answer"] = answer

        if confidence is not None:
            context["last_confidence"] = (
                confidence
            )

        context["last_evidence_summary"] = {
            "node_count": len(
                evidence_graph.get(
                    "nodes",
                    [],
                )
            ),
            "edge_count": len(
                evidence_graph.get(
                    "edges",
                    [],
                )
            ),
        }

        # Preserve existing map context.
        # The executor does not invent or modify pin coordinates.
        context.setdefault(
            "map_context",
            _extract_map_context(
                context
            ),
        )

        session.conversation_context = context

        update_fields = [
            "conversation_history",
            "conversation_context",
        ]

        if any(
            field.name == "updated_at"
            for field in session._meta.fields
        ):
            update_fields.append(
                "updated_at"
            )

        session.save(
            update_fields=update_fields
        )

    except Exception:
        logger.warning(
            "Unable to update session memory.",
            exc_info=True,
        )


# ============================================================================
# Event summary
# ============================================================================

def _event_summary(
    result: dict[str, Any],
) -> dict[str, Any]:

    summary = {}

    for key in (
        "status",
        "answer",
        "caption",
        "confidence",
        "candidate_count",
        "water_features_count",
        "vegetation_features_count",
        "change_percentage",
        "changed_area_hectares",
        "changed_area_km2",
        "changed_area_m2",
        "provider",
        "evidence_count",
        "verification_status",
        "geographic_quantification",
        "error",
    ):

        if key in result:
            summary[key] = _json_safe(
                result[key]
            )

    features = result.get(
        "features"
    )

    if isinstance(
        features,
        list,
    ):
        summary["feature_count"] = len(
            features
        )

    evidence_regions = result.get(
        "persisted_evidence_regions"
    )

    if isinstance(
        evidence_regions,
        list,
    ):
        summary[
            "persisted_evidence_region_count"
        ] = len(
            evidence_regions
        )

    if result.get(
        "change_mask"
    ) is not None:
        summary["change_mask_available"] = True

    return summary


# ============================================================================
# Evidence bundle extraction
# ============================================================================

def _build_evidence_bundle(
    evidence_validation: dict[str, Any],
    evidence_graph: dict[str, Any],
    step_outputs: dict[str, Any],
) -> dict[str, Any]:

    execution_results = {
        key: value
        for key, value in step_outputs.items()
        if not key.startswith("_")
    }

    bundle = {
        "validation": evidence_validation,
        "graph": evidence_graph,
        "execution_results": execution_results,
    }

    # If the EvidenceEngine exposes structured report information,
    # retain it without inventing fields.
    try:
        report = EvidenceEngine.build_report(
            execution_results=execution_results
        )

        if hasattr(
            report,
            "evidence_items",
        ):
            bundle["evidence_items"] = _json_safe(
                report.evidence_items
            )

        if hasattr(
            report,
            "observations",
        ):
            bundle["observations"] = _json_safe(
                report.observations
            )

        if hasattr(
            report,
            "measurements",
        ):
            bundle["measurements"] = _json_safe(
                report.measurements
            )

        if hasattr(
            report,
            "limitations",
        ):
            bundle["limitations"] = _json_safe(
                report.limitations
            )

    except Exception:
        logger.debug(
            "Unable to enrich evidence bundle.",
            exc_info=True,
        )

    return _json_safe(
        bundle
    )


# ============================================================================
# Main executor
# ============================================================================

class AgentExecutor:
    """
    Master execution engine.

    Preferred entrypoint:
        execute_safe(query_id)

    Compatibility entrypoint:
        execute_plan(...)
    """

    # ========================================================================
    # Public safe entrypoint
    # ========================================================================

    def execute_safe(
        self,
        query_id: str,
    ) -> dict[str, Any]:

        query = (
            Query.objects
            .select_related(
                "session",
                "image",
                "image_pair",
            )
            .get(
                id=query_id
            )
        )

        return self.execute_query(
            query
        )

    # ========================================================================
    # Main execution
    # ========================================================================

    def execute_query(
        self,
        query: Query,
    ) -> dict[str, Any]:

        redis_client = _get_redis_client()

        query.status = "RUNNING"
        query.error = None

        query.save(
            update_fields=[
                "status",
                "error",
            ]
        )

        publish_query_event(
            redis_client,
            str(query.id),
            {
                "event": "QUERY_STARTED",
                "query_id": str(query.id),
                "status": "RUNNING",
            },
        )

        try:

            image_pair = getattr(
                query,
                "image_pair",
                None,
            )

            assets = _resolve_assets(
                query=query,
                image_assets=None,
                image_pair=image_pair,
            )

            return self._execute_core(
                query=query,
                assets=assets,
                image_pair=image_pair,
                redis_client=redis_client,
            )

        except Exception as exc:

            logger.exception(
                "Agent execution failed.",
                extra={
                    "query_id": str(
                        query.id
                    )
                },
            )

            query.status = "FAILED"
            query.error = str(exc)
            query.completed_at = timezone.now()

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                ]
            )

            publish_query_event(
                redis_client,
                str(query.id),
                {
                    "event": "QUERY_FAILED",
                    "query_id": str(query.id),
                    "status": "FAILED",
                    "error": str(exc),
                },
            )

            return {
                "status": "FAILED",
                "error": str(exc),
                "answer": None,
                "confidence": None,
            }

    # ========================================================================
    # Compatibility entrypoint
    # ========================================================================

    def execute_plan(
        self,
        query: Query,
        plan: dict[str, Any],
        image_assets: list[Any],
        image_pair: Any | None = None,
    ) -> dict[str, Any]:

        query.plan = _json_safe(
            plan
        )

        query.structured_plan = _json_safe(
            plan
        )

        query.save(
            update_fields=[
                "plan",
                "structured_plan",
            ]
        )

        return self._execute_with_inputs(
            query=query,
            image_assets=image_assets,
            image_pair=image_pair,
        )

    def _execute_with_inputs(
        self,
        query: Query,
        image_assets: list[Any] | None,
        image_pair: Any | None,
    ) -> dict[str, Any]:

        redis_client = _get_redis_client()

        try:

            assets = _resolve_assets(
                query=query,
                image_assets=image_assets,
                image_pair=image_pair,
            )

            return self._execute_core(
                query=query,
                assets=assets,
                image_pair=image_pair,
                redis_client=redis_client,
            )

        except Exception as exc:

            logger.exception(
                "Explicit-input execution failed.",
                extra={
                    "query_id": str(
                        query.id
                    )
                },
            )

            query.status = "FAILED"
            query.error = str(exc)
            query.completed_at = timezone.now()

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                ]
            )

            return {
                "status": "FAILED",
                "error": str(exc),
                "answer": None,
                "confidence": None,
            }

    # ========================================================================
    # Core execution
    # ========================================================================

    def _execute_core(
        self,
        query: Query,
        assets: list[Any],
        image_pair: Any | None,
        redis_client: Any,
    ) -> dict[str, Any]:

        # ------------------------------------------------------------------
        # Resolve actual imagery.
        # ------------------------------------------------------------------

        imagery_context = _build_imagery_context(
            assets
        )

        session_context = _get_session_context(
            query
        )

        map_context = _extract_map_context(
            session_context
        )

        plan = (
            getattr(
                query,
                "structured_plan",
                None,
            )
            or getattr(
                query,
                "plan",
                None,
            )
            or {}
        )

        if not isinstance(
            plan,
            dict,
        ):
            plan = {}

        steps = _plan_steps(
            query
        )

        # ------------------------------------------------------------------
        # No actual imagery.
        # ------------------------------------------------------------------

        if not assets:

            logger.info(
                "Query %s has no resolved imagery inputs.",
                query.id,
            )

        # ------------------------------------------------------------------
        # Preprocessing.
        # ------------------------------------------------------------------

        if assets:

            (
                imagery_context,
                preprocessing_result,
            ) = _preprocess_imagery(
                imagery_context
            )

        else:

            preprocessing_result = {
                "status": "skipped",
                "reason": "no_uploaded_imagery",
            }

        publish_query_event(
            redis_client,
            str(query.id),
            {
                "event": "PREPROCESSING_COMPLETED",
                "query_id": str(query.id),
                "result": preprocessing_result,
            },
        )

        # ------------------------------------------------------------------
        # Duplicate observations.
        # ------------------------------------------------------------------

        identical_observations = False

        pair_type = getattr(
            image_pair,
            "pair_type",
            None,
        )

        if (
            len(assets) >= 2
            and pair_type == "BI_TEMPORAL"
        ):
            identical_observations = (
                _observations_identical(
                    assets,
                    imagery_context,
                )
            )

        if identical_observations:

            publish_query_event(
                redis_client,
                str(query.id),
                {
                    "event": (
                        "IDENTICAL_OBSERVATIONS_DETECTED"
                    ),
                    "query_id": str(query.id),
                },
            )

        # ------------------------------------------------------------------
        # Step execution.
        # ------------------------------------------------------------------

        step_outputs: dict[str, Any] = {}
        step_rows: list[ExecutionStep] = []

        confidence_values: list[float] = []

        last_change_mask = None

        for item in steps:

            try:
                step_number = int(
                    item.get(
                        "step",
                        len(step_rows) + 1,
                    )
                )

            except Exception:
                step_number = (
                    len(step_rows) + 1
                )

            tool_name = str(
                item.get(
                    "tool",
                    "",
                )
            ).strip()

            if not tool_name:
                continue

            params = item.get(
                "parameters",
                {},
            )

            if not isinstance(
                params,
                dict,
            ):
                params = {}

            optional = _step_is_optional(
                item
            )

            # --------------------------------------------------------------
            # Identical bi-temporal observations.
            # --------------------------------------------------------------

            if (
                identical_observations
                and tool_name
                in (
                    CHANGE_TOOLS
                    | {
                        "AREA_QUANTIFIER",
                    }
                )
            ):

                skipped = _skip_step(
                    query,
                    step_number,
                    tool_name,
                    (
                        "The two supplied observations are identical; "
                        "there is no meaningful difference to analyze."
                    ),
                )

                step_rows.append(
                    skipped
                )

                step_outputs[
                    f"step_{step_number}"
                ] = {
                    "status": "skipped",
                    "identical_observations": True,
                }

                continue

            # --------------------------------------------------------------
            # Create execution row.
            # --------------------------------------------------------------

            model_version = str(
                item.get(
                    "model_version",
                    "1.0",
                )
            )

            input_refs = [
                asset.get(
                    "asset_id"
                )
                for asset in imagery_context.get(
                    "assets",
                    [],
                )
                if asset.get(
                    "asset_id"
                )
            ]

            step_row = _create_step(
                query=query,
                step_number=step_number,
                tool_name=tool_name,
                params=params,
                model_version=model_version,
                input_refs=input_refs,
            )

            step_rows.append(
                step_row
            )

            publish_query_event(
                redis_client,
                str(query.id),
                {
                    "event": "STEP_STARTED",
                    "query_id": str(query.id),
                    "step_number": step_number,
                    "tool": tool_name,
                    "optional": optional,
                    "status": "RUNNING",
                },
            )

            started = time.perf_counter()

            try:

                # ----------------------------------------------------------
                # Context resolution.
                # ----------------------------------------------------------

                if tool_name == "CONTEXT_RESOLUTION":

                    result = {
                        "status": "completed",
                        "context": _json_safe(
                            map_context
                        ),
                    }

                # ----------------------------------------------------------
                # Preprocessing.
                # ----------------------------------------------------------

                elif tool_name == "IMAGE_PREPROCESSING":

                    result = {
                        "status": preprocessing_result.get(
                            "status",
                            "completed",
                        ),
                        "quality": preprocessing_result,
                    }

                # ----------------------------------------------------------
                # Area quantification.
                # ----------------------------------------------------------

                elif tool_name == "AREA_QUANTIFIER":

                    result = _execute_area_quantifier(
                        last_change_mask,
                        _primary_metadata(
                            imagery_context
                        ),
                    )

                # ----------------------------------------------------------
                # Evidence validation.
                # -------------------------------------------------------
                elif tool_name == "EVIDENCE_VALIDATOR":

                    result = _validate_step_evidence(
                        step_outputs
                    )
                elif tool_name == "ANSWER_COMPOSER":

                    result = {
                        "status": "completed",
                        "answer": _compose_grounded_answer(
                            query=query,
                            step_outputs=step_outputs,
                            imagery_context=imagery_context,
                            identical_observations=identical_observations,
                        ),
                    }
                # ----------------------------------------------------------
                # Specialist model.
                # ----------------------------------------------------------

                elif (
                    tool_name in MODEL_TOOL_NAMES
                    or self._is_registered_model(
                        tool_name
                    )
                ):

                    result = _execute_model(
                        model_id=tool_name,
                        query=query,
                        imagery_context=imagery_context,
                        params=params,
                        last_change_mask=last_change_mask,
                    )

                # ----------------------------------------------------------
                # Tool registry.
                # ----------------------------------------------------------

                else:

                    registry = (
                        ToolRegistry.get_instance()
                    )

                    tool_definition = (
                        registry.get_tool(
                            tool_name
                        )
                    )

                    if tool_definition is None:

                        raise ValueError(
                            f"Execution tool '{tool_name}' is not "
                            "registered in ToolRegistry or the "
                            "specialist model registry."
                        )

                    kwargs = _build_tool_kwargs(
                        tool_name=tool_name,
                        params=params,
                        query=query,
                        imagery_context=imagery_context,
                        map_context=map_context,
                        step_outputs=step_outputs,
                        last_change_mask=last_change_mask,
                    )

                    result = registry.execute(
                        tool_name,
                        **kwargs,
                    )

                # ----------------------------------------------------------
                # Normalize output.
                # ----------------------------------------------------------

                result = _normalize_tool_result(
                    result
                )

                # ----------------------------------------------------------
                # Capture change mask.
                # ----------------------------------------------------------

                if result.get(
                    "change_mask"
                ) is not None:

                    last_change_mask = result.get(
                        "change_mask"
                    )

                # ----------------------------------------------------------
                # Capture supplied confidence only.
                # ----------------------------------------------------------

                confidence = result.get(
                    "confidence"
                )

                if confidence is not None:

                    try:

                        confidence_float = float(
                            confidence
                        )

                        if (
                            np.isfinite(
                                confidence_float
                            )
                            and 0.0
                            <= confidence_float
                            <= 1.0
                        ):
                            confidence_values.append(
                                confidence_float
                            )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

                # ----------------------------------------------------------
                # Store result.
                # ----------------------------------------------------------

                latency_ms = int(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000
                )

                step_outputs[
                    f"step_{step_number}"
                ] = result

                result_status = str(
                    result.get(
                        "status",
                        "ok",
                    )
                ).lower()

                step_status = (
                    "DONE"
                    if result_status
                    not in {
                        "error",
                        "failed",
                    }
                    else "FAILED"
                )

                evidence_refs = []

                if result.get(
                    "features"
                ) is not None:
                    evidence_refs.append(
                        f"step_{step_number}:features"
                    )

                if result.get(
                    "measurements"
                ) is not None:
                    evidence_refs.append(
                        f"step_{step_number}:measurements"
                    )

                if result.get(
                    "observations"
                ) is not None:
                    evidence_refs.append(
                        f"step_{step_number}:observations"
                    )

                if result.get(
                    "change_mask"
                ) is not None:
                    evidence_refs.append(
                        f"step_{step_number}:change_mask"
                    )

                _complete_step(
                    step_row,
                    result,
                    latency_ms,
                    step_status,
                    evidence_refs=evidence_refs,
                )

                publish_query_event(
                    redis_client,
                    str(query.id),
                    {
                        "event": "STEP_COMPLETED",
                        "query_id": str(query.id),
                        "step_number": step_number,
                        "tool": tool_name,
                        "status": step_status,
                        "latency_ms": latency_ms,
                        "output_summary": (
                            self._event_summary(
                                result
                            )
                        ),
                    },
                )

            except Exception as exc:

                latency_ms = int(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000
                )

                _fail_step(
                    step_row,
                    str(exc),
                    latency_ms,
                )

                step_outputs[
                    f"step_{step_number}"
                ] = {
                    "status": "error",
                    "error": str(exc),
                }

                publish_query_event(
                    redis_client,
                    str(query.id),
                    {
                        "event": "STEP_FAILED",
                        "query_id": str(query.id),
                        "step_number": step_number,
                        "tool": tool_name,
                        "status": "FAILED",
                        "optional": optional,
                        "error": str(exc),
                        "latency_ms": latency_ms,
                    },
                )

                continue

        # ------------------------------------------------------------------
        # Validate evidence.
        # ------------------------------------------------------------------

        evidence_validation = (
            _validate_step_evidence(
                step_outputs
            )
        )

        step_outputs[
            "_evidence_validation"
        ] = evidence_validation

        # ------------------------------------------------------------------
        # Required-step failures.
        # ------------------------------------------------------------------

        required_failures = (
            _required_step_failures(
                steps,
                step_outputs,
            )
        )

        if required_failures:

            evidence_validation[
                "required_step_failures"
            ] = required_failures

        # ------------------------------------------------------------------
        # Grounded answer.
        # ------------------------------------------------------------------

        final_answer = _compose_grounded_answer(
            query=query,
            step_outputs=step_outputs,
            imagery_context=imagery_context,
            identical_observations=identical_observations,
        )

        if required_failures:

            limitations = "\n".join(
                (
                    f"- {failure.get('tool')}: "
                    f"{failure.get('reason')}"
                )
                for failure in required_failures
            )

            final_answer += (
                "\n\nExecution limitations:\n"
                + limitations
            )

        # ------------------------------------------------------------------
        # Evidence graph.
        # ------------------------------------------------------------------

        evidence_graph = _build_evidence_graph(
            query=query,
            imagery_context=imagery_context,
            step_outputs=step_outputs,
            step_rows=step_rows,
            map_context=map_context,
        )

        evidence_graph[
            "preprocessing"
        ] = _json_safe(
            preprocessing_result
        )

        evidence_graph[
            "validation"
        ] = _json_safe(
            evidence_validation
        )

        evidence_graph[
            "identical_observations"
        ] = identical_observations

        evidence_graph[
            "input_load_reports"
        ] = _json_safe(
            imagery_context.get(
                "load_reports",
                [],
            )
        )

        # ------------------------------------------------------------------
        # Confidence.
        #
        # This is an aggregate of explicitly returned model/tool confidence
        # values. If no component supplies confidence, it remains None.
        # ------------------------------------------------------------------

        confidence = (
            float(
                np.mean(
                    confidence_values
                )
            )
            if confidence_values
            else None
        )

        # ------------------------------------------------------------------
        # Execution trace.
        # ------------------------------------------------------------------

        execution_trace = []

        for row in step_rows:

            trace_item = {
                "step": row.step_number,
                "tool": row.tool_name,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "model_version": row.model_version,
            }

            if hasattr(
                row,
                "agent_type",
            ):
                trace_item["agent_type"] = (
                    row.agent_type
                )

            execution_trace.append(
                trace_item
            )

        # ------------------------------------------------------------------
        # Structured plan.
        # ------------------------------------------------------------------

        structured_plan = dict(
            plan
        )

        structured_plan[
            "execution_trace"
        ] = execution_trace

        structured_plan[
            "preprocessing"
        ] = _json_safe(
            preprocessing_result
        )

        structured_plan[
            "input_assets"
        ] = [
            _json_safe(asset)
            for asset in imagery_context.get(
                "assets",
                [],
            )
        ]

        structured_plan[
            "evidence_validation"
        ] = _json_safe(
            evidence_validation
        )

        structured_plan[
            "map_context"
        ] = _json_safe(
            map_context
        )

        # ------------------------------------------------------------------
        # Evidence bundle.
        # ------------------------------------------------------------------

        evidence_bundle = _build_evidence_bundle(
            evidence_validation=evidence_validation,
            evidence_graph=evidence_graph,
            step_outputs=step_outputs,
        )

        # ------------------------------------------------------------------
        # Answer trace.
        #
        # This is intentionally concise. It contains execution facts only,
        # never hidden reasoning or chain-of-thought.
        # ------------------------------------------------------------------

        answer_trace = {
            "status": "grounded",
            "source_steps": [
                row.step_number
                for row in step_rows
                if row.status == "DONE"
            ],
            "evidence_validation": {
                "valid": evidence_validation.get(
                    "valid"
                ),
                "evidence_count": evidence_validation.get(
                    "evidence_count",
                    0,
                ),
                "measurement_count": evidence_validation.get(
                    "measurement_count",
                    0,
                ),
            },
            "identical_observations": (
                identical_observations
            ),
        }

        # ------------------------------------------------------------------
        # Persist query.
        # ------------------------------------------------------------------

        query.structured_plan = (
            structured_plan
        )

        query.answer = final_answer

        query.confidence = confidence

        query.evidence_graph = _json_safe(
            evidence_graph
        )

        # New structured evidence fields.
        field_names = {
            field.name
            for field in Query._meta.fields
        }

        if "evidence_bundle" in field_names:
            query.evidence_bundle = _json_safe(
                evidence_bundle
            )

        if "answer_trace" in field_names:
            query.answer_trace = _json_safe(
                answer_trace
            )

        query.status = "COMPLETED"

        query.error = None

        query.completed_at = timezone.now()

        update_fields = [
            "structured_plan",
            "answer",
            "confidence",
            "evidence_graph",
            "status",
            "error",
            "completed_at",
        ]

        if "evidence_bundle" in field_names:
            update_fields.append(
                "evidence_bundle"
            )

        if "answer_trace" in field_names:
            update_fields.append(
                "answer_trace"
            )

        query.save(
            update_fields=update_fields
        )

        # ------------------------------------------------------------------
        # Session memory.
        # ------------------------------------------------------------------

        _update_session_memory(
            query=query,
            answer=final_answer,
            confidence=confidence,
            evidence_graph=evidence_graph,
        )

        # ------------------------------------------------------------------
        # Completion event.
        # ------------------------------------------------------------------

        publish_query_event(
            redis_client,
            str(query.id),
            {
                "event": "QUERY_COMPLETED",
                "query_id": str(query.id),
                "status": "COMPLETED",
                "answer": final_answer,
                "confidence": confidence,
                "evidence_graph": evidence_graph,
                "execution_trace": execution_trace,
            },
        )

        return {
            "status": "COMPLETED",
            "answer": final_answer,
            "confidence": confidence,
            "follow_up_questions": (
                getattr(
                    query,
                    "follow_up_questions",
                    None,
                )
                or []
            ),
            "evidence_graph": evidence_graph,
            "evidence_bundle": evidence_bundle,
            "execution_trace": execution_trace,
        }

    # ========================================================================
    # Class helpers
    # ========================================================================

    @staticmethod
    def _is_registered_model(
        tool_name: str,
    ) -> bool:
        return _is_registered_model(
            tool_name
        )

    @staticmethod
    def _event_summary(
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return _event_summary(
            result
        )


# ============================================================================
# Module-level compatibility API
# ============================================================================

def execute_plan(
    query: Query,
    plan: dict[str, Any],
    image_assets: list[Any],
    image_pair: Any | None = None,
) -> dict[str, Any]:

    executor = AgentExecutor()

    return executor.execute_plan(
        query=query,
        plan=plan,
        image_assets=image_assets,
        image_pair=image_pair,
    )