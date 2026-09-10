"""
Celery execution entrypoint for SatQuery-X queries.

The task is intentionally thin.

Responsibilities:
1. Load the authenticated query.
2. Reconstruct the complete execution context.
3. Resolve all imagery inputs belonging to the query.
4. Pass the context to the master orchestrator.
5. Keep Celery retries/error handling separate from scientific reasoning.

The orchestrator is responsible for planning, routing, specialist execution,
evidence validation and answer composition.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.agent.agent import Agent
from apps.queries.models import Query


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------

def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _asset_summary(asset) -> dict:
    """
    Return metadata needed by the orchestrator without loading the raster
    itself into the task payload.
    """

    return {
        "id": str(asset.id),
        "filename": getattr(asset, "filename", None)
        or getattr(asset, "name", None),
        "sensor": getattr(asset, "sensor", None),
        "modality": getattr(asset, "modality", None),
        "acquisition_date": (
            asset.acquisition_date.isoformat()
            if getattr(asset, "acquisition_date", None)
            else None
        ),
        "width": getattr(asset, "width", None),
        "height": getattr(asset, "height", None),
        "band_count": getattr(asset, "band_count", None),
        "dtype": getattr(asset, "dtype", None),
        "crs": getattr(asset, "crs", None),
        "resolution_m": getattr(asset, "resolution_m", None),
        "cloud_cover": getattr(asset, "cloud_cover", None),
        "has_geospatial_reference": (
            asset.has_geospatial_reference
            if hasattr(asset, "has_geospatial_reference")
            else None
        ),
        "has_wgs84_bounds": (
            asset.has_wgs84_bounds
            if hasattr(asset, "has_wgs84_bounds")
            else None
        ),
    }


def _pair_summary(pair) -> dict:
    """
    Return image-pair metadata without duplicating raster data.
    """

    return {
        "id": str(pair.id),
        "pair_type": getattr(pair, "pair_type", None),
        "session_id": (
            str(pair.session_id)
            if getattr(pair, "session_id", None)
            else None
        ),
        "image_before_id": (
            str(pair.image_before_id)
            if getattr(pair, "image_before_id", None)
            else None
        ),
        "image_after_id": (
            str(pair.image_after_id)
            if getattr(pair, "image_after_id", None)
            else None
        ),
    }


def build_query_context(query: Query) -> dict:
    """
    Build the complete context passed to the master orchestrator.

    The context contains references and metadata, not hidden reasoning.
    """

    context = _safe_dict(query.context_snapshot)

    # ------------------------------------------------------------------
    # Session context
    # ------------------------------------------------------------------

    session = query.session

    session_context = _safe_dict(
        getattr(session, "conversation_context", {})
    )

    # Query-specific context wins over older session values.
    merged_context = {
        **session_context,
        **context,
    }

    # ------------------------------------------------------------------
    # Imagery inputs
    # ------------------------------------------------------------------

    assets = []

    try:
        queryset = query.input_assets.all()
        assets.extend(list(queryset))
    except Exception:
        pass

    # Preserve backwards compatibility with the legacy primary image.
    if query.image_id:
        if not any(
            str(asset.id) == str(query.image_id)
            for asset in assets
        ):
            assets.insert(0, query.image)

    # Remove accidental duplicates while preserving order.
    unique_assets = []

    seen_asset_ids: set[str] = set()

    for asset in assets:
        asset_id = str(asset.id)

        if asset_id in seen_asset_ids:
            continue

        seen_asset_ids.add(asset_id)
        unique_assets.append(asset)

    # ------------------------------------------------------------------
    # Image pair
    # ------------------------------------------------------------------

    pair = query.image_pair

    # ------------------------------------------------------------------
    # Active map/location context
    # ------------------------------------------------------------------

    map_context = {
        "current_visual_state": merged_context.get(
            "current_visual_state"
        ),
        "active_region": merged_context.get(
            "active_region"
        ),
        "current_viewport": merged_context.get(
            "current_viewport"
        ),
        "aoi_geometry": merged_context.get(
            "aoi_geometry"
        ),
        "active_pin": merged_context.get(
            "active_pin"
        ),
        "map_center": merged_context.get(
            "map_center"
        ),
        "map_zoom": merged_context.get(
            "map_zoom"
        ),
    }

    # Remove empty values so downstream agents can distinguish "missing"
    # from an explicitly supplied null value.
    map_context = {
        key: value
        for key, value in map_context.items()
        if value is not None
    }

    # ------------------------------------------------------------------
    # Full orchestrator context
    # ------------------------------------------------------------------

    merged_context.update(
        {
            "query_id": str(query.id),
            "session_id": str(session.id),
            "user_id": str(query.user_id),

            "request": {
                "text": query.text,
                "detected_mode": query.detected_mode,
                "detected_task": query.detected_task,
            },

            "imagery": {
                "count": len(unique_assets),
                "assets": [
                    _asset_summary(asset)
                    for asset in unique_assets
                ],
            },

            "image_ids": [
                str(asset.id)
                for asset in unique_assets
            ],

            "has_images": bool(unique_assets),

            "image_pair": (
                _pair_summary(pair)
                if pair is not None
                else None
            ),

            "pair_type": (
                getattr(pair, "pair_type", None)
                if pair is not None
                else None
            ),

            "map_context": map_context,

            "planner_context": {
                "existing_plan": _safe_dict(
                    query.plan
                ),
                "structured_plan": _safe_dict(
                    query.structured_plan
                ),
            },

            "execution_context": {
                "query_status": query.status,
                "previous_evidence": _safe_dict(
                    query.evidence_graph
                ),
                "validated_evidence": _safe_dict(
                    query.evidence_bundle
                ),
            },
        }
    )

    return merged_context


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="apps.queries.tasks.run_query_task",
    autoretry_for=(),
    max_retries=0,
)
def run_query_task(
    self,
    ingestion_results=None,
    query_id: str | None = None,
) -> dict:
    """
    Execute one query through the master SatQuery-X orchestrator.

    The task does not perform scientific analysis itself.
    """

    # Celery chord callbacks pass the header results as the first argument.
    # Direct calls may pass only query_id. Support both forms.
    if query_id is None and isinstance(ingestion_results, str):
        query_id = ingestion_results
        ingestion_results = None
    if not query_id:
        raise ValueError("query_id is required")

    query = None

    try:
        # --------------------------------------------------------------
        # Load query
        # --------------------------------------------------------------

        query = (
            Query.objects
            .select_related(
                "session",
                "user",
                "image",
                "image_pair",
            )
            .prefetch_related(
                "input_assets",
                "execution_steps",
            )
            .get(id=query_id)
        )

        logger.info(
            "Starting SatQuery-X query %s",
            query.id,
        )

        # --------------------------------------------------------------
        # Prevent duplicate execution
        # --------------------------------------------------------------

        if query.status == "COMPLETED":
            logger.info(
                "Query %s is already completed.",
                query.id,
            )

            return {
                "query_id": str(query.id),
                "status": query.status,
                "skipped": True,
            }

        # --------------------------------------------------------------
        # Mark execution as running
        # --------------------------------------------------------------

        with transaction.atomic():
            query.status = "RUNNING"
            query.error = None
            query.save(
                update_fields=[
                    "status",
                    "error",
                ]
            )

        # --------------------------------------------------------------
        # Build complete context
        # --------------------------------------------------------------

        session_context = build_query_context(
            query
        )

        # --------------------------------------------------------------
        # Execute master orchestrator
        # --------------------------------------------------------------

        result = Agent.run(
            query,
            session_context,
        )

        # --------------------------------------------------------------
        # Normalize orchestrator result
        # --------------------------------------------------------------

        if isinstance(result, dict):
            result_status = result.get(
                "status",
                query.status,
            )

            return {
                "query_id": str(query.id),
                "status": result_status,
                "result": result,
            }

        return {
            "query_id": str(query.id),
            "status": query.status,
            "result": result,
        }

    except Query.DoesNotExist:
        logger.exception(
            "Query %s does not exist.",
            query_id,
        )

        raise

    except Exception as exc:
        logger.exception(
            "SatQuery-X query execution failed: %s",
            query_id,
        )

        # --------------------------------------------------------------
        # Persist failure state
        # --------------------------------------------------------------

        if query is not None:
            try:
                query.mark_failed(
                    str(exc)
                )
            except Exception:
                logger.exception(
                    "Unable to persist failure state for query %s.",
                    query_id,
                )

        # Do not fabricate a result when execution fails.
        raise


# ---------------------------------------------------------------------------
# Compatibility alias
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="apps.queries.tasks.execute_query_task",
)
def execute_query_task(
    self,
    query_id: str,
) -> dict:
    """
    Compatibility alias for code that still imports execute_query_task.

    The canonical entrypoint is run_query_task.
    """

    return run_query_task.run(
        query_id
    )


__all__ = [
    "build_query_context",
    "run_query_task",
    "execute_query_task",
]