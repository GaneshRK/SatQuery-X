"""
Temporal and monitoring API views for SatQuery-X.

Grounded satellite intelligence API.

Rules:
- Only authenticated user-owned data is exposed.
- No synthetic satellite observations.
- No fabricated AOIs or coordinates.
- No fabricated NDVI, change percentage, area, confidence, or causes.
- Satellite scenes are associated with an AOI.
- Change events use scene_before / scene_after.
- AOI monitoring uses AOIMonitoring.
- Temporal responses expose persisted/indexed evidence only.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AcquisitionRequest,
    AOIMonitoring,
    AreaOfInterest,
    ChangeEvent,
    DataSyncJob,
    SatelliteScene,
    TemporalObservation,
)

from .serializers import (
    AcquisitionRequestSerializer,
    AOIMonitoringSerializer,
    AreaOfInterestSerializer,
    ChangeEventSerializer,
    DataSyncJobSerializer,
    SatelliteSceneSerializer,
    TemporalObservationSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================


def _get_session_model():
    """
    Import the current SatQuery-X Session model lazily.
    """
    try:
        from apps.sessions.models import Session
    except ImportError as exc:
        raise RuntimeError(
            "SatQuery-X Session model could not be imported."
        ) from exc

    return Session


def _get_owned_session(request, session_id):
    """
    Return a session only when it belongs to the authenticated user.
    """
    Session = _get_session_model()

    try:
        return Session.objects.get(
            pk=session_id,
            user=request.user,
        )
    except Session.DoesNotExist:
        raise Http404("Session not found.")


def _get_owned_aoi(request, aoi_id):
    """
    Resolve an AOI through its owning session.
    """
    try:
        return (
            AreaOfInterest.objects
            .select_related("session")
            .get(
                pk=aoi_id,
                session__user=request.user,
            )
        )
    except AreaOfInterest.DoesNotExist:
        raise Http404("Area of interest not found.")


def _get_owned_scene(request, scene_id):
    """
    Resolve a satellite scene through its AOI/session ownership.
    """
    try:
        return (
            SatelliteScene.objects
            .select_related(
                "aoi",
                "aoi__session",
                "collection",
            )
            .get(
                pk=scene_id,
                aoi__session__user=request.user,
            )
        )
    except SatelliteScene.DoesNotExist:
        raise Http404("Satellite scene not found.")


def _get_owned_change_event(request, event_id):
    """
    Resolve a change event through its AOI/session ownership.
    """
    try:
        return (
            ChangeEvent.objects
            .select_related(
                "aoi",
                "aoi__session",
                "scene_before",
                "scene_after",
            )
            .get(
                pk=event_id,
                aoi__session__user=request.user,
            )
        )
    except ChangeEvent.DoesNotExist:
        raise Http404("Change event not found.")


def _parse_date(
    value: Any,
    *,
    field_name: str,
) -> date | None:
    """
    Parse an optional ISO date.
    """
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format."
        ) from exc


def _date_window_from_request(request):
    """
    Resolve optional start/end date query parameters.
    """
    start_date = _parse_date(
        request.query_params.get("start_date"),
        field_name="start_date",
    )

    end_date = _parse_date(
        request.query_params.get("end_date"),
        field_name="end_date",
    )

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise ValueError(
            "start_date cannot be later than end_date."
        )

    return start_date, end_date


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evidence_measurements(evidence: Any) -> dict[str, Any]:
    """
    Return only explicitly persisted measurements.

    Nothing is calculated or invented here.
    """
    bundle = _as_dict(evidence)

    measurements = bundle.get("measurements")

    if isinstance(measurements, dict):
        return measurements

    graph = _as_dict(
        bundle.get("evidence_graph")
    )

    measurements = graph.get("measurements")

    if isinstance(measurements, dict):
        return measurements

    return {}


def _change_evidence(event: ChangeEvent) -> dict[str, Any]:
    """
    Read explicitly persisted evidence from a change event.
    """
    evidence = getattr(
        event,
        "evidence",
        None,
    )

    if isinstance(evidence, dict):
        return evidence

    metadata = getattr(
        event,
        "metadata",
        None,
    )

    if isinstance(metadata, dict):
        return metadata

    return {}


def _scene_queryset(request):
    """
    User-owned satellite scenes.
    """
    return (
        SatelliteScene.objects
        .select_related(
            "aoi",
            "aoi__session",
            "collection",
        )
        .filter(
            aoi__session__user=request.user
        )
    )


def _aoi_queryset(request):
    """
    User-owned AOIs.
    """
    return (
        AreaOfInterest.objects
        .select_related("session")
        .filter(
            session__user=request.user
        )
    )


def _timeline_queryset(aoi):
    """
    Actual temporal observations associated with an AOI.
    """
    return (
        TemporalObservation.objects
        .filter(
            aoi=aoi
        )
        .select_related(
            "scene",
            "scene__collection",
        )
        .order_by(
            "observation_date",
            "scene__acquisition_datetime",
        )
    )


# =============================================================================
# SATELLITE SCENES
# =============================================================================


class SatelliteSceneListView(APIView):
    """
    List indexed satellite scenes belonging to the authenticated user.

    Optional filters:

        ?session_id=
        ?aoi_id=
        ?sensor=
        ?start_date=
        ?end_date=
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        queryset = _scene_queryset(request)

        session_id = request.query_params.get(
            "session_id"
        )

        if session_id:
            queryset = queryset.filter(
                aoi__session_id=session_id
            )

        aoi_id = request.query_params.get(
            "aoi_id"
        )

        if aoi_id:
            queryset = queryset.filter(
                aoi_id=aoi_id
            )

        sensor = request.query_params.get(
            "sensor"
        )

        if sensor:
            queryset = queryset.filter(
                Q(sensor__iexact=sensor)
                | Q(
                    collection__sensor_type__iexact=sensor
                )
            )

        try:
            start_date, end_date = (
                _date_window_from_request(request)
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date:
            queryset = queryset.filter(
                acquisition_datetime__date__gte=start_date
            )

        if end_date:
            queryset = queryset.filter(
                acquisition_datetime__date__lte=end_date
            )

        queryset = queryset.order_by(
            "-acquisition_datetime",
            "-created_at",
        )

        serializer = SatelliteSceneSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)


class SatelliteSceneDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        scene_id,
    ):
        scene = _get_owned_scene(
            request,
            scene_id,
        )

        serializer = SatelliteSceneSerializer(
            scene,
            context={"request": request},
        )

        return Response(serializer.data)


# =============================================================================
# AOI
# =============================================================================


class AOIListCreateView(APIView):
    """
    List or create authenticated-user AOIs.

    Creation requires explicit geometry.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        queryset = _aoi_queryset(request)

        session_id = request.query_params.get(
            "session_id"
        )

        if session_id:
            queryset = queryset.filter(
                session_id=session_id
            )

        serializer = AreaOfInterestSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        session_id = request.data.get(
            "session_id"
        )

        if not session_id:
            return Response(
                {
                    "detail": (
                        "session_id is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = _get_owned_session(
                request,
                session_id,
            )
        except Http404:
            return Response(
                {
                    "detail": "Session not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        geometry = request.data.get(
            "geometry"
        )

        if not geometry:
            return Response(
                {
                    "detail": (
                        "geometry is required. "
                        "SatQuery-X does not create "
                        "default geographic coordinates."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.data.copy()
        payload["session"] = session.pk

        serializer = AreaOfInterestSerializer(
            data=payload,
            context={"request": request},
        )

        serializer.is_valid(
            raise_exception=True
        )

        aoi = serializer.save(
            session=session
        )

        return Response(
            AreaOfInterestSerializer(
                aoi,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# AOI TIMELINE
# =============================================================================


class AOITimelineView(APIView):
    """
    Return actual indexed temporal observations for an AOI.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        aoi_id,
    ):
        aoi = _get_owned_aoi(
            request,
            aoi_id,
        )

        queryset = _timeline_queryset(
            aoi
        )

        try:
            start_date, end_date = (
                _date_window_from_request(request)
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date:
            queryset = queryset.filter(
                observation_date__gte=start_date
            )

        if end_date:
            queryset = queryset.filter(
                observation_date__lte=end_date
            )

        serializer = TemporalObservationSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        observations = serializer.data

        years = sorted(
            {
                int(
                    item["observation_date"][:4]
                )
                for item in observations
                if item.get("observation_date")
            }
        )

        return Response(
            {
                "aoi": AreaOfInterestSerializer(
                    aoi,
                    context={"request": request},
                ).data,
                "observation_count": len(
                    observations
                ),
                "years": years,
                "observations": observations,
                "data_status": (
                    "available"
                    if observations
                    else "no_indexed_observations"
                ),
            }
        )


# =============================================================================
# CHANGE ANALYSIS
# =============================================================================


class ChangeAnalysisView(APIView):
    """
    Return persisted evidence-backed change analysis.

    This view does not calculate scientific values.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        aoi_id = request.query_params.get(
            "aoi_id"
        )

        if not aoi_id:
            return Response(
                {
                    "detail": "aoi_id is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            aoi = _get_owned_aoi(
                request,
                aoi_id,
            )
        except Http404:
            return Response(
                {
                    "detail": (
                        "Area of interest not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = (
            ChangeEvent.objects
            .filter(
                aoi=aoi
            )
            .select_related(
                "aoi",
                "scene_before",
                "scene_after",
            )
            .order_by("-created_at")
        )

        before_scene_id = request.query_params.get(
            "before_scene_id"
        )

        after_scene_id = request.query_params.get(
            "after_scene_id"
        )

        if before_scene_id:
            queryset = queryset.filter(
                scene_before_id=before_scene_id
            )

        if after_scene_id:
            queryset = queryset.filter(
                scene_after_id=after_scene_id
            )

        event = queryset.first()

        if event is None:
            return Response(
                {
                    "status": "no_analysis",
                    "aoi_id": str(aoi.pk),
                    "detail": (
                        "No completed change analysis "
                        "is available for this AOI."
                    ),
                    "evidence_available": False,
                }
            )

        serializer = ChangeEventSerializer(
            event,
            context={"request": request},
        )

        payload = dict(
            serializer.data
        )

        evidence = _change_evidence(
            event
        )

        measurements = _evidence_measurements(
            evidence
        )

        payload["evidence_available"] = bool(
            evidence
        )

        payload["measurements"] = measurements

        payload["analysis_status"] = (
            "evidence_backed"
            if evidence
            else "metadata_only"
        )

        return Response(payload)

    def post(self, request):
        """
        Validate already-persisted change evidence.

        Actual analysis belongs to the agent/CV pipeline.
        """
        event_id = request.data.get(
            "change_event_id"
        )

        if not event_id:
            return Response(
                {
                    "detail": (
                        "change_event_id is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = _get_owned_change_event(
                request,
                event_id,
            )
        except Http404:
            return Response(
                {
                    "detail": (
                        "Change event not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        evidence = _change_evidence(
            event
        )

        measurements = _evidence_measurements(
            evidence
        )

        return Response(
            {
                "status": (
                    "validated"
                    if evidence
                    else "insufficient_evidence"
                ),
                "change_event": ChangeEventSerializer(
                    event,
                    context={"request": request},
                ).data,
                "measurements": measurements,
                "evidence_available": bool(
                    evidence
                ),
            }
        )


# =============================================================================
# CHANGE EVENTS
# =============================================================================


class ChangeEventListView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        queryset = (
            ChangeEvent.objects
            .select_related(
                "aoi",
                "aoi__session",
                "scene_before",
                "scene_after",
            )
            .filter(
                aoi__session__user=request.user
            )
            .order_by("-created_at")
        )

        aoi_id = request.query_params.get(
            "aoi_id"
        )

        if aoi_id:
            queryset = queryset.filter(
                aoi_id=aoi_id
            )

        session_id = request.query_params.get(
            "session_id"
        )

        if session_id:
            queryset = queryset.filter(
                aoi__session_id=session_id
            )

        serializer = ChangeEventSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)


class ChangeEventDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        event_id,
    ):
        event = _get_owned_change_event(
            request,
            event_id,
        )

        serializer = ChangeEventSerializer(
            event,
            context={"request": request},
        )

        return Response(serializer.data)


# =============================================================================
# DATA SYNCHRONIZATION
# =============================================================================


class SyncStatusView(APIView):
    """
    Show persisted satellite catalogue synchronization jobs.

    POST queues actual catalogue synchronization.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        queryset = (
            DataSyncJob.objects
            .select_related(
                "aoi",
                "aoi__session",
            )
            .filter(
                aoi__session__user=request.user
            )
            .order_by("-started_at")
        )

        session_id = request.query_params.get(
            "session_id"
        )

        if session_id:
            queryset = queryset.filter(
                aoi__session_id=session_id
            )

        serializer = DataSyncJobSerializer(
            queryset[:50],
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "jobs": serializer.data,
                "count": len(serializer.data),
            }
        )

    def post(self, request):
        session_id = request.data.get(
            "session_id"
        )

        if not session_id:
            return Response(
                {
                    "detail": (
                        "session_id is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = _get_owned_session(
                request,
                session_id,
            )
        except Http404:
            return Response(
                {
                    "detail": "Session not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        aoi_id = request.data.get(
            "aoi_id"
        )

        aoi = None

        if aoi_id:
            try:
                aoi = _get_owned_aoi(
                    request,
                    aoi_id,
                )
            except Http404:
                return Response(
                    {
                        "detail": (
                            "Area of interest not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if aoi.session_id != session.pk:
                return Response(
                    {
                        "detail": (
                            "AOI does not belong "
                            "to the selected session."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            from .tasks import (
                sync_latest_available_catalogue_task
            )
        except ImportError:
            logger.exception(
                "Satellite synchronization task unavailable."
            )

            return Response(
                {
                    "detail": (
                        "Satellite synchronization "
                        "service is unavailable."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        task = sync_latest_available_catalogue_task.delay(
            aoi_id=(
                str(aoi.pk)
                if aoi is not None
                else None
            )
        )

        return Response(
            {
                "status": "queued",
                "task_id": task.id,
                "session_id": str(session.pk),
                "aoi_id": (
                    str(aoi.pk)
                    if aoi is not None
                    else None
                ),
                "data_mode": (
                    "latest_available_catalogue"
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# =============================================================================
# AOI MONITORING
# =============================================================================


class AOIMonitoringView(APIView):
    """
    Read/update AOIMonitoring configuration.

    Monitoring configuration is separate from satellite observations.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        aoi_id,
    ):
        aoi = _get_owned_aoi(
            request,
            aoi_id,
        )

        monitoring = (
            AOIMonitoring.objects
            .filter(aoi=aoi)
            .first()
        )

        if monitoring is None:
            return Response(
                {
                    "aoi_id": str(aoi.pk),
                    "monitoring": None,
                    "status": "not_configured",
                }
            )

        return Response(
            {
                "aoi_id": str(aoi.pk),
                "monitoring": AOIMonitoringSerializer(
                    monitoring,
                    context={"request": request},
                ).data,
                "status": "configured",
            }
        )

    @transaction.atomic
    def post(
        self,
        request,
        aoi_id,
    ):
        """
        Create or update monitoring configuration.
        """
        aoi = _get_owned_aoi(
            request,
            aoi_id,
        )

        monitoring = (
            AOIMonitoring.objects
            .filter(aoi=aoi)
            .first()
        )

        if monitoring is None:
            serializer = AOIMonitoringSerializer(
                data={
                    **request.data,
                    "aoi": aoi.pk,
                },
                context={"request": request},
            )

            serializer.is_valid(
                raise_exception=True
            )

            monitoring = serializer.save(
                aoi=aoi
            )
        else:
            serializer = AOIMonitoringSerializer(
                monitoring,
                data=request.data,
                partial=True,
                context={"request": request},
            )

            serializer.is_valid(
                raise_exception=True
            )

            monitoring = serializer.save()

        return Response(
            {
                "status": "configured",
                "aoi_id": str(aoi.pk),
                "monitoring": AOIMonitoringSerializer(
                    monitoring,
                    context={"request": request},
                ).data,
            }
        )

    @transaction.atomic
    def patch(
        self,
        request,
        aoi_id,
    ):
        aoi = _get_owned_aoi(
            request,
            aoi_id,
        )

        monitoring = (
            AOIMonitoring.objects
            .filter(aoi=aoi)
            .first()
        )

        if monitoring is None:
            return Response(
                {
                    "detail": (
                        "Monitoring is not configured "
                        "for this AOI."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AOIMonitoringSerializer(
            monitoring,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        serializer.is_valid(
            raise_exception=True
        )

        monitoring = serializer.save()

        return Response(
            {
                "status": "updated",
                "aoi_id": str(aoi.pk),
                "monitoring": AOIMonitoringSerializer(
                    monitoring,
                    context={"request": request},
                ).data,
            }
        )

    @transaction.atomic
    def delete(
        self,
        request,
        aoi_id,
    ):
        aoi = _get_owned_aoi(
            request,
            aoi_id,
        )

        deleted, _ = (
            AOIMonitoring.objects
            .filter(aoi=aoi)
            .delete()
        )

        return Response(
            {
                "status": (
                    "deleted"
                    if deleted
                    else "not_configured"
                ),
                "aoi_id": str(aoi.pk),
            }
        )


# =============================================================================
# COMPATIBILITY ALIASES
# =============================================================================


SceneListView = SatelliteSceneListView

SceneDetailView = SatelliteSceneDetailView

TemporalTimelineView = AOITimelineView


__all__ = [
    "SatelliteSceneListView",
    "SatelliteSceneDetailView",
    "AOIListCreateView",
    "AOITimelineView",
    "ChangeAnalysisView",
    "ChangeEventListView",
    "ChangeEventDetailView",
    "SyncStatusView",
    "AOIMonitoringView",
    "SceneListView",
    "SceneDetailView",
    "TemporalTimelineView",
]