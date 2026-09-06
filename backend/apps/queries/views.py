"""
REST API views for SatQuery-X conversational analysis.

Responsibilities:
- Create queries inside an owned session
- Resolve active imagery and image-pair context
- Preserve map/pin/AOI context
- Support multiple imagery inputs
- Dispatch asynchronous query execution
- Expose query details and execution trace
- Provide authenticated SSE streaming
- Provide authenticated exports

The views do not perform scientific analysis. All analysis is delegated to
the master orchestrator and specialist agents.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from typing import Any

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import (
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sessions.models import Session
from apps.imagery.models import ImageAsset, ImagePair

from .models import Query
from .serializers import (
    QueryCreateSerializer,
    QueryDetailSerializer,
)
from .tasks import run_query_task


logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================

def _owned_session(user, session_id):
    """
    Resolve a session belonging to the authenticated user.

    Never expose whether a session exists when it belongs to another user.
    """

    return get_object_or_404(
        Session,
        id=session_id,
        user=user,
    )


def _owned_image(user, image_id):
    """
    Resolve an imagery asset owned through the user's session.
    """

    return get_object_or_404(
        ImageAsset,
        id=image_id,
        session__user=user,
    )


def _owned_pair(user, pair_id):
    """
    Resolve an image pair belonging to the authenticated user's session.
    """

    return get_object_or_404(
        ImagePair,
        id=pair_id,
        session__user=user,
    )


def _json_body(request) -> dict:
    """
    Safely normalize JSON request bodies.
    """

    if isinstance(request.data, dict):
        return dict(request.data)

    return {}


def _get_first_validated_asset(session):
    """
    Return the first validated image in a session.

    This is only a context fallback. It is not used to fabricate an input when
    no imagery exists.
    """

    return (
        session.imagery_assets
        .filter(status="VALIDATED")
        .order_by("created_at")
        .first()
    )


def _get_first_pair(session):
    return (
        ImagePair.objects
        .filter(session=session)
        .order_by("created_at")
        .first()
    )


def _normalize_asset_ids(
    session,
    requested_ids: Any,
) -> list[str]:
    """
    Validate and normalize multiple image IDs.

    Only assets belonging to the selected session are accepted.
    """

    if requested_ids is None:
        return []

    if isinstance(requested_ids, str):
        requested_ids = [
            value.strip()
            for value in requested_ids.split(",")
            if value.strip()
        ]

    if not isinstance(requested_ids, (list, tuple)):
        return []

    normalized = []

    for value in requested_ids:
        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        normalized.append(value)

    if not normalized:
        return []

    existing_ids = set(
        str(value)
        for value in (
            session.imagery_assets
            .filter(id__in=normalized)
            .values_list("id", flat=True)
        )
    )

    invalid_ids = [
        value
        for value in normalized
        if value not in existing_ids
    ]

    if invalid_ids:
        raise ValueError(
            "One or more imagery assets do not belong to this session."
        )

    # Preserve client ordering while removing duplicates.
    result = []
    seen = set()

    for value in normalized:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def _merge_context(
    session,
    *,
    visual_context: Any = None,
    aoi_geometry: Any = None,
    active_pin: Any = None,
    viewport: Any = None,
    active_region: Any = None,
) -> dict:
    """
    Merge client-provided visual/map state into the session context.

    Existing context is preserved unless the client explicitly supplies a new
    value.
    """

    current = (
        dict(session.conversation_context)
        if isinstance(
            session.conversation_context,
            dict,
        )
        else {}
    )

    if visual_context is not None:
        current["current_visual_state"] = visual_context

    if aoi_geometry is not None:
        current["aoi_geometry"] = aoi_geometry

    if active_pin is not None:
        current["active_pin"] = active_pin

    if viewport is not None:
        current["current_viewport"] = viewport

    if active_region is not None:
        current["active_region"] = active_region

    return current


def _persist_session_context(session, context: dict) -> None:
    session.conversation_context = context

    session.save(
        update_fields=[
            "conversation_context",
        ]
    )


def _query_queryset_for_user(user):
    """
    Base query queryset constrained to the authenticated user.
    """

    return (
        Query.objects
        .filter(
            user=user,
            session__user=user,
        )
        .select_related(
            "session",
            "image",
            "image_pair",
        )
        .prefetch_related(
            "input_assets",
            "execution_steps",
        )
    )


def _serialize_query(query, request=None):
    serializer = QueryDetailSerializer(
        query,
        context={
            "request": request,
        },
    )

    return serializer.data


def _dispatch_query(query) -> dict:
    """
    Dispatch asynchronous execution.

    Returns dispatch metadata. Scientific execution is performed by the
    Celery task.
    """

    try:
        async_result = run_query_task.delay(
            str(query.id)
        )

        return {
            "queued": True,
            "task_id": str(
                getattr(async_result, "id", "")
            ) or None,
        }

    except Exception as exc:
        logger.warning(
            "Celery dispatch failed for query %s: %s",
            query.id,
            exc,
        )

        # Development environments may not have a worker running.
        # Run synchronously as a compatibility fallback.
        try:
            result = run_query_task.apply(
                args=[str(query.id)]
            ).get()

            return {
                "queued": False,
                "synchronous": True,
                "task_id": None,
                "result": result,
            }

        except Exception as sync_exc:
            logger.exception(
                "Synchronous fallback failed for query %s.",
                query.id,
            )

            query.mark_failed(
                str(sync_exc)
            )

            return {
                "queued": False,
                "synchronous": True,
                "task_id": None,
                "error": str(sync_exc),
            }


def _safe_filename(value: str, default: str = "satquery-export") -> str:
    """
    Keep generated export filenames safe.
    """

    value = (
        value
        .replace("/", "_")
        .replace("\\", "_")
        .replace("..", "_")
        .replace(" ", "_")
    )

    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "-_."
    )

    value = "".join(
        char
        for char in value
        if char in allowed
    )

    return value[:100] or default


def _get_query_evidence(query) -> dict:
    """
    Return the validated evidence bundle when available, otherwise the
    execution evidence graph.

    No calculations are performed here.
    """

    if isinstance(query.evidence_bundle, dict):
        if query.evidence_bundle:
            return query.evidence_bundle

    if isinstance(query.evidence_graph, dict):
        return query.evidence_graph

    return {}


def _geojson_from_evidence(evidence: dict) -> dict | None:
    """
    Extract an existing GeoJSON object from evidence.

    This function never creates geographic coordinates.
    """

    candidates = [
        evidence.get("geojson"),
        evidence.get("geojson_feature_collection"),
    ]

    geospatial = evidence.get("geospatial")

    if isinstance(geospatial, dict):
        candidates.extend(
            [
                geospatial.get("geojson"),
                geospatial.get("geometry"),
            ]
        )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        candidate_type = candidate.get("type")

        if candidate_type in {
            "Feature",
            "FeatureCollection",
            "Point",
            "Polygon",
            "MultiPolygon",
            "LineString",
            "MultiLineString",
        }:
            return candidate

    return None


def _csv_rows_from_evidence(evidence: dict) -> list[dict]:
    """
    Convert already-existing structured measurements/regions to CSV rows.

    No new measurements are calculated.
    """

    rows = []

    measurements = evidence.get(
        "measurements"
    )

    if isinstance(measurements, dict):
        for name, value in measurements.items():
            if isinstance(value, dict):
                row = {
                    "type": "measurement",
                    "name": name,
                    "value": value.get(
                        "value",
                        value.get("measurement"),
                    ),
                    "unit": value.get("unit"),
                }
            else:
                row = {
                    "type": "measurement",
                    "name": name,
                    "value": value,
                    "unit": "",
                }

            rows.append(row)

    regions = evidence.get(
        "regions"
    )

    if isinstance(regions, list):
        for index, region in enumerate(regions):
            if not isinstance(region, dict):
                continue

            rows.append(
                {
                    "type": "region",
                    "name": region.get(
                        "label",
                        f"region-{index + 1}",
                    ),
                    "value": region.get(
                        "area"
                    ),
                    "unit": region.get(
                        "area_unit",
                        "",
                    ),
                }
            )

    return rows


# ============================================================================
# Query creation
# ============================================================================

class SessionQueryListCreateView(APIView):
    """
    GET:
        List the authenticated user's queries for a session.

    POST:
        Create a query and dispatch it to the master orchestrator.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, session_id):
        session = _owned_session(
            request.user,
            session_id,
        )

        queryset = (
            _query_queryset_for_user(
                request.user
            )
            .filter(session=session)
            .order_by("-created_at")
        )

        # Keep list responses lightweight.
        data = []

        for query in queryset:
            data.append(
                {
                    "id": str(query.id),
                    "text": query.text,
                    "detected_mode": query.detected_mode,
                    "detected_task": query.detected_task,
                    "status": query.status,
                    "confidence": query.confidence,
                    "clarification_required": (
                        query.clarification_required
                    ),
                    "created_at": query.created_at,
                    "completed_at": query.completed_at,
                }
            )

        return Response(
            {
                "session_id": str(session.id),
                "count": len(data),
                "results": data,
            }
        )

    def post(self, request, session_id):
        session = _owned_session(
            request.user,
            session_id,
        )

        payload = _json_body(request)

        text = str(
            payload.get(
                "text",
                ""
            )
        ).strip()

        if not text:
            return Response(
                {
                    "detail": "Query text is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --------------------------------------------------------------
        # Resolve optional single image
        # --------------------------------------------------------------

        image_id = payload.get(
            "image_id"
        )

        image = None

        if image_id:
            image = _owned_image(
                request.user,
                image_id,
            )

            if image.session_id != session.id:
                return Response(
                    {
                        "detail": (
                            "Image does not belong to this session."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # --------------------------------------------------------------
        # Resolve optional image pair
        # --------------------------------------------------------------

        image_pair_id = payload.get(
            "image_pair_id"
        )

        image_pair = None

        if image_pair_id:
            image_pair = _owned_pair(
                request.user,
                image_pair_id,
            )

            if image_pair.session_id != session.id:
                return Response(
                    {
                        "detail": (
                            "Image pair does not belong to this session."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # --------------------------------------------------------------
        # Resolve multiple imagery inputs
        # --------------------------------------------------------------

        requested_asset_ids = payload.get(
            "input_asset_ids"
        )

        # Accept `image_ids` as an additional API spelling.
        if requested_asset_ids is None:
            requested_asset_ids = payload.get(
                "image_ids"
            )

        try:
            input_asset_ids = _normalize_asset_ids(
                session,
                requested_asset_ids,
            )
        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The primary image is also an explicit input.
        if image is not None:
            image_id_string = str(image.id)

            if image_id_string not in input_asset_ids:
                input_asset_ids.insert(
                    0,
                    image_id_string,
                )

        # --------------------------------------------------------------
        # Optional context
        # --------------------------------------------------------------

        visual_context = payload.get(
            "visual_context"
        )

        aoi_geometry = payload.get(
            "aoi_geometry"
        )

        active_pin = payload.get(
            "active_pin"
        )

        viewport = payload.get(
            "viewport",
            payload.get("current_viewport"),
        )

        active_region = payload.get(
            "active_region"
        )

        context = _merge_context(
            session,
            visual_context=visual_context,
            aoi_geometry=aoi_geometry,
            active_pin=active_pin,
            viewport=viewport,
            active_region=active_region,
        )

        # Persist map state so subsequent conversational requests can
        # resolve words such as "here", "this place", and "this area".
        if (
            visual_context is not None
            or aoi_geometry is not None
            or active_pin is not None
            or viewport is not None
            or active_region is not None
        ):
            _persist_session_context(
                session,
                context,
            )

        # --------------------------------------------------------------
        # Determine initial mode only from available inputs.
        #
        # The master planner remains authoritative and may refine the task.
        # --------------------------------------------------------------

        detected_mode = "SINGLE_IMAGE"

        if image_pair is not None:
            detected_mode = "BI_TEMPORAL"

        elif len(input_asset_ids) >= 2:
            detected_mode = "BI_TEMPORAL"

        # Cross-modal requests are allowed to be identified by the planner.
        # We do not guess modality from filenames here.
        requested_mode = payload.get(
            "detected_mode"
        )

        if requested_mode in {
            "SINGLE_IMAGE",
            "BI_TEMPORAL",
            "CROSS_MODAL",
        }:
            detected_mode = requested_mode

        # --------------------------------------------------------------
        # Create query
        # --------------------------------------------------------------

        query = Query.objects.create(
            session=session,
            user=request.user,
            text=text,
            image=image,
            image_pair=image_pair,
            detected_mode=detected_mode,
            status="PENDING",
            context_snapshot=context,
        )

        # Attach multiple inputs.
        if input_asset_ids:
            assets = ImageAsset.objects.filter(
                session=session,
                id__in=input_asset_ids,
            )

            query.input_assets.set(
                assets
            )

        # --------------------------------------------------------------
        # Dispatch
        # --------------------------------------------------------------

        dispatch_info = _dispatch_query(
            query
        )

        query_data = _serialize_query(
            query,
            request,
        )

        return Response(
            {
                "query": query_data,
                "dispatch": dispatch_info,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ============================================================================
# Query detail
# ============================================================================

class QueryDetailView(APIView):
    """
    Return a complete query including evidence and execution trace.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, session_id, query_id):
        query = get_object_or_404(
            _query_queryset_for_user(
                request.user
            ),
            id=query_id,
            session_id=session_id,
        )

        return Response(
            _serialize_query(
                query,
                request,
            )
        )


# ============================================================================
# Query stream
# ============================================================================

class QueryStreamView(APIView):
    """
    Authenticated Server-Sent Events endpoint.

    The stream exposes state changes and concise execution information.
    It does not expose internal chain-of-thought.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, session_id, query_id):
        query = get_object_or_404(
            _query_queryset_for_user(
                request.user
            ),
            id=query_id,
            session_id=session_id,
        )

        def event_stream():
            last_signature = None
            started = time.monotonic()

            # Maximum connection lifetime.
            max_seconds = 120

            while True:
                if time.monotonic() - started > max_seconds:
                    yield self._sse(
                        "timeout",
                        {
                            "query_id": str(
                                query.id
                            ),
                            "status": query.status,
                        },
                    )
                    break

                # Refresh from database.
                try:
                    query.refresh_from_db()
                except Exception:
                    yield self._sse(
                        "error",
                        {
                            "query_id": str(
                                query.id
                            ),
                            "detail": (
                                "Unable to refresh query state."
                            ),
                        },
                    )
                    break

                execution_steps = list(
                    query.execution_steps.all()
                )

                step_state = [
                    {
                        "id": str(step.id),
                        "step_number": step.step_number,
                        "tool_name": step.tool_name,
                        "agent_type": step.agent_type,
                        "model_version": step.model_version,
                        "status": step.status,
                        "latency_ms": step.latency_ms,
                        "retry_count": step.retry_count,
                    }
                    for step in execution_steps
                ]

                payload = {
                    "query_id": str(
                        query.id
                    ),
                    "status": query.status,
                    "detected_mode": query.detected_mode,
                    "detected_task": query.detected_task,
                    "confidence": query.confidence,
                    "clarification_required": (
                        query.clarification_required
                    ),
                    "steps": step_state,
                    "answer_available": (
                        bool(
                            query.answer
                            and query.answer.strip()
                        )
                    ),
                }

                signature = json.dumps(
                    payload,
                    sort_keys=True,
                    default=str,
                )

                if signature != last_signature:
                    yield self._sse(
                        "query",
                        payload,
                    )

                    last_signature = signature

                if query.status in {
                    "COMPLETED",
                    "FAILED",
                }:
                    # Send final serialized response.
                    yield self._sse(
                        "complete",
                        _serialize_query(
                            query,
                            request,
                        ),
                    )
                    break

                time.sleep(1)

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )

        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"

        return response

    @staticmethod
    def _sse(event: str, data: Any) -> str:
        return (
            f"event: {event}\n"
            f"data: {json.dumps(data, default=str)}\n\n"
        )


# ============================================================================
# Query export
# ============================================================================

class QueryExportView(APIView):
    """
    Export validated query evidence.

    Supported formats:
    - json
    - csv
    - geojson

    Raster artifacts should be downloaded through their registered artifact
    URLs rather than reconstructed by this endpoint.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    ALLOWED_FORMATS = {
        "json",
        "csv",
        "geojson",
    }

    def get(self, request, session_id, query_id):
        query = get_object_or_404(
            _query_queryset_for_user(
                request.user
            ),
            id=query_id,
            session_id=session_id,
        )

        if query.status != "COMPLETED":
            return Response(
                {
                    "detail": (
                        "Export is available only after "
                        "query execution completes."
                    ),
                    "status": query.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        export_format = str(
            request.query_params.get(
                "format",
                "json",
            )
        ).lower()

        if export_format not in self.ALLOWED_FORMATS:
            return Response(
                {
                    "detail": (
                        "Unsupported export format."
                    ),
                    "supported_formats": sorted(
                        self.ALLOWED_FORMATS
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        evidence = _get_query_evidence(
            query
        )

        if export_format == "json":
            return self._json_export(
                query,
                evidence,
            )

        if export_format == "geojson":
            return self._geojson_export(
                query,
                evidence,
            )

        return self._csv_export(
            query,
            evidence,
        )

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _json_export(
        self,
        query: Query,
        evidence: dict,
    ):
        payload = {
            "query_id": str(
                query.id
            ),
            "session_id": str(
                query.session_id
            ),
            "task": query.detected_task,
            "mode": query.detected_mode,
            "question": query.text,
            "answer": query.answer,
            "confidence": query.confidence,
            "evidence": evidence,
            "answer_trace": query.answer_trace,
            "created_at": query.created_at,
            "completed_at": query.completed_at,
        }

        response = HttpResponse(
            json.dumps(
                payload,
                indent=2,
                default=str,
            ),
            content_type="application/json",
        )

        filename = _safe_filename(
            f"satquery-{query.id}"
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="{filename}.json"'
        )

        return response

    # ------------------------------------------------------------------
    # GeoJSON
    # ------------------------------------------------------------------

    def _geojson_export(
        self,
        query: Query,
        evidence: dict,
    ):
        geojson = _geojson_from_evidence(
            evidence
        )

        if geojson is None:
            return Response(
                {
                    "detail": (
                        "No GeoJSON geometry was produced "
                        "by the analysis."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # If the upstream object is a raw geometry, wrap it in a Feature.
        if geojson.get("type") not in {
            "Feature",
            "FeatureCollection",
        }:
            geojson = {
                "type": "Feature",
                "geometry": geojson,
                "properties": {
                    "query_id": str(
                        query.id
                    ),
                    "task": query.detected_task,
                },
            }

        response = HttpResponse(
            json.dumps(
                geojson,
                indent=2,
                default=str,
            ),
            content_type="application/geo+json",
        )

        filename = _safe_filename(
            f"satquery-{query.id}"
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="{filename}.geojson"'
        )

        return response

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def _csv_export(
        self,
        query: Query,
        evidence: dict,
    ):
        rows = _csv_rows_from_evidence(
            evidence
        )

        if not rows:
            return Response(
                {
                    "detail": (
                        "No tabular measurements or regions "
                        "were produced by the analysis."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        buffer = io.StringIO()

        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "type",
                "name",
                "value",
                "unit",
            ],
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "type": row.get(
                        "type",
                        "",
                    ),
                    "name": row.get(
                        "name",
                        "",
                    ),
                    "value": row.get(
                        "value",
                        "",
                    ),
                    "unit": row.get(
                        "unit",
                        "",
                    ),
                }
            )

        response = HttpResponse(
            buffer.getvalue(),
            content_type="text/csv",
        )

        filename = _safe_filename(
            f"satquery-{query.id}"
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="{filename}.csv"'
        )

        return response


# ============================================================================
# Session context
# ============================================================================

class SessionContextView(APIView):
    """
    Return the current conversational/map context for an owned session.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, session_id):
        session = _owned_session(
            request.user,
            session_id,
        )

        context = (
            session.conversation_context
            if isinstance(
                session.conversation_context,
                dict,
            )
            else {}
        )

        return Response(
            {
                "session_id": str(
                    session.id
                ),
                "context": context,
            }
        )

    def patch(self, request, session_id):
        session = _owned_session(
            request.user,
            session_id,
        )

        payload = _json_body(request)

        existing = (
            dict(
                session.conversation_context
            )
            if isinstance(
                session.conversation_context,
                dict,
            )
            else {}
        )

        allowed_context_keys = {
            "current_visual_state",
            "active_region",
            "current_viewport",
            "aoi_geometry",
            "active_pin",
            "map_center",
            "map_zoom",
            "selected_asset_ids",
            "selected_pair_id",
        }

        for key in allowed_context_keys:
            if key in payload:
                existing[key] = payload[key]

        _persist_session_context(
            session,
            existing,
        )

        return Response(
            {
                "session_id": str(
                    session.id
                ),
                "context": existing,
            }
        )


class SessionContextResetView(APIView):
    """
    Clear conversational/map context for an owned session.
    """

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def post(self, request, session_id):
        session = _owned_session(
            request.user,
            session_id,
        )

        session.conversation_context = {}

        session.save(
            update_fields=[
                "conversation_context",
            ]
        )

        return Response(
            {
                "session_id": str(
                    session.id
                ),
                "context": {},
                "reset": True,
            }
        )