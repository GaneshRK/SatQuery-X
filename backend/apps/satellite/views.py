"""
Authenticated REST API views for SatQuery-X satellite intelligence.

This module exposes:
- User-owned Areas of Interest
- Satellite catalogue metadata
- Historical catalogue search
- Acquisition requests and candidates
- Temporal observations
- Persisted change events
- AOI monitoring configuration
- Catalogue synchronization
- Scene evidence

Scientific integrity rules:
- No fabricated satellite observations.
- No synthetic raster generation.
- No hardcoded AOIs, dates, CRS, resolution, cloud cover,
  confidence, NDVI, or change percentages.
- Catalogue results originate from configured providers.
- Acquisition is tied to the authenticated user's session.
- Persisted change events are returned as stored evidence only.
- Monitoring uses AOIMonitoring; no fabricated alert records are created.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from apps.system.throttles import SatelliteSearchRateThrottle
from rest_framework.views import APIView

from apps.satellite.indexer import HistoricalCatalogueIndexer
from apps.satellite.models import (
    AcquisitionCandidate,
    AcquisitionRequest,
    AOIMonitoring,
    AreaOfInterest,
    ChangeEvent,
    SatelliteCollection,
    SatelliteScene,
    TemporalObservation,
)
from apps.satellite.serializers import (
    AcquisitionCandidateSerializer,
    AcquisitionRequestCreateSerializer,
    AcquisitionRequestSerializer,
    AOIMonitoringSerializer,
    AreaOfInterestSerializer,
    ChangeEventSerializer,
    SatelliteCollectionSerializer,
    SatelliteSceneSerializer,
    TemporalObservationSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# COMMON HELPERS
# =============================================================================


def _session_for_user(user, session_id):
    """
    Resolve a session owned by the authenticated user.
    """
    from apps.sessions.models import Session

    return get_object_or_404(
        Session,
        id=session_id,
        user=user,
    )


def _parse_json_object(value):
    """
    Parse a JSON object while preserving explicit absence.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None

        return parsed if isinstance(parsed, dict) else None

    return None


def _serialize_provider_error(exc: Exception) -> dict[str, Any]:
    """
    Return a safe provider error response.

    Provider internals, credentials, stack traces and filesystem paths
    are not exposed.
    """
    return {
        "error": "satellite_provider_error",
        "detail": str(exc),
    }


def _candidate_response(candidate):
    return AcquisitionCandidateSerializer(candidate).data


# =============================================================================
# AREA OF INTEREST
# =============================================================================


class AreaOfInterestListCreateView(generics.ListCreateAPIView):
    """
    List and create user-owned Areas of Interest.

    No default location is created.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AreaOfInterestSerializer

    def get_queryset(self):
        return (
            AreaOfInterest.objects
            .filter(
                session__user=self.request.user
            )
            .select_related("session")
            .order_by("name")
        )

    def perform_create(self, serializer):
        session_id = self.request.data.get("session")

        if not session_id:
            raise ValueError("session is required.")

        session = _session_for_user(
            self.request.user,
            session_id,
        )

        serializer.save(session=session)


class AreaOfInterestDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AreaOfInterestSerializer

    def get_queryset(self):
        return (
            AreaOfInterest.objects
            .filter(
                session__user=self.request.user
            )
            .select_related("session")
        )


# =============================================================================
# SATELLITE COLLECTIONS
# =============================================================================


class SatelliteCollectionListView(
    generics.ListAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = SatelliteCollectionSerializer

    def get_queryset(self):
        queryset = SatelliteCollection.objects.all()

        sensor = self.request.query_params.get("sensor")

        if sensor:
            queryset = queryset.filter(
                sensor_type__iexact=sensor
            )

        return queryset.order_by(
            "provider",
            "name",
        )


# =============================================================================
# SATELLITE SCENES
# =============================================================================


class SatelliteSceneListView(
    generics.ListAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = SatelliteSceneSerializer

    def get_queryset(self):
        queryset = (
            SatelliteScene.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "collection",
                "aoi",
            )
        )

        aoi_id = self.request.query_params.get("aoi")

        if aoi_id:
            queryset = queryset.filter(
                aoi_id=aoi_id
            )

        collection_id = (
            self.request.query_params.get("collection")
        )

        if collection_id:
            queryset = queryset.filter(
                collection_id=collection_id
            )

        sensor = self.request.query_params.get("sensor")

        if sensor:
            queryset = queryset.filter(
                sensor__iexact=sensor
            )

        return queryset.order_by(
            "-acquisition_datetime",
            "-created_at",
        )


class SatelliteSceneDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = SatelliteSceneSerializer

    def get_queryset(self):
        return (
            SatelliteScene.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "collection",
                "aoi",
            )
        )


# =============================================================================
# HISTORICAL CATALOGUE SEARCH
# =============================================================================


class HistoricalCatalogueSearchView(APIView):
    """
    Search the configured satellite provider for real catalogue scenes.

    Required:
        session_id
        aoi_id
        start_date
        end_date

    Optional:
        sensor
        max_cloud_cover
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]
    throttle_classes = [SatelliteSearchRateThrottle]

    def post(self, request, *args, **kwargs):
        session_id = request.data.get("session_id")
        aoi_id = request.data.get("aoi_id")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        if not all(
            [
                session_id,
                aoi_id,
                start_date,
                end_date,
            ]
        ):
            return Response(
                {
                    "error": (
                        "session_id, aoi_id, start_date "
                        "and end_date are required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = _session_for_user(
            request.user,
            session_id,
        )

        aoi = get_object_or_404(
            AreaOfInterest,
            id=aoi_id,
            session=session,
        )

        sensor = request.data.get("sensor")

        max_cloud_cover = request.data.get(
            "max_cloud_cover"
        )

        if (
            max_cloud_cover is not None
            and max_cloud_cover != ""
        ):
            try:
                max_cloud_cover = float(
                    max_cloud_cover
                )
            except (
                TypeError,
                ValueError,
            ):
                return Response(
                    {
                        "error": (
                            "max_cloud_cover must be numeric."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            indexer = HistoricalCatalogueIndexer()

            result = indexer.index_aoi_history(
                aoi=aoi,
                start_date=start_date,
                end_date=end_date,
                sensor=sensor,
                max_cloud_cover=max_cloud_cover,
            )

        except Exception as exc:
            logger.exception(
                "Historical satellite catalogue search failed."
            )

            return Response(
                _serialize_provider_error(exc),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # The current indexer may return either:
        # - a list of candidates
        # - a structured result dictionary
        #
        # Preserve whichever form the indexer actually returns.

        if isinstance(result, dict):
            candidates = result.get(
                "candidates",
                result.get("results", []),
            )

            if not isinstance(candidates, list):
                candidates = []

            response_payload = dict(result)

            response_payload.update(
                {
                    "session_id": str(session.id),
                    "aoi_id": str(aoi.id),
                    "start_date": start_date,
                    "end_date": end_date,
                    "sensor": sensor,
                    "max_cloud_cover": max_cloud_cover,
                    "count": len(candidates),
                }
            )

            if candidates:
                response_payload["candidates"] = [
                    _candidate_response(candidate)
                    if hasattr(candidate, "_meta")
                    else candidate
                    for candidate in candidates
                ]

            return Response(response_payload)

        if isinstance(result, list):
            return Response(
                {
                    "session_id": str(session.id),
                    "aoi_id": str(aoi.id),
                    "start_date": start_date,
                    "end_date": end_date,
                    "sensor": sensor,
                    "max_cloud_cover": max_cloud_cover,
                    "count": len(result),
                    "candidates": [
                        _candidate_response(candidate)
                        for candidate in result
                    ],
                }
            )

        return Response(
            {
                "session_id": str(session.id),
                "aoi_id": str(aoi.id),
                "start_date": start_date,
                "end_date": end_date,
                "sensor": sensor,
                "max_cloud_cover": max_cloud_cover,
                "count": 0,
                "candidates": [],
                "result": result,
            }
        )


# =============================================================================
# ACQUISITION REQUESTS
# =============================================================================


class AcquisitionRequestListCreateView(
    generics.ListCreateAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AcquisitionRequestCreateSerializer

        return AcquisitionRequestSerializer

    def get_queryset(self):
        return (
            AcquisitionRequest.objects
            .filter(
                session__user=self.request.user
            )
            .select_related(
                "session",
            )
            .prefetch_related(
                "candidates",
            )
        )

    def create(self, request, *args, **kwargs):
        serializer = (
            AcquisitionRequestCreateSerializer(
                data=request.data,
                context={
                    "request": request,
                },
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        acquisition_request = serializer.save()

        return Response(
            AcquisitionRequestSerializer(
                acquisition_request
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AcquisitionRequestDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AcquisitionRequestSerializer

    def get_queryset(self):
        return (
            AcquisitionRequest.objects
            .filter(
                session__user=self.request.user
            )
            .select_related(
                "session",
            )
            .prefetch_related(
                "candidates",
            )
        )


# =============================================================================
# ACQUISITION CANDIDATES
# =============================================================================


class AcquisitionCandidateListView(
    generics.ListAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AcquisitionCandidateSerializer

    def get_queryset(self):
        queryset = (
            AcquisitionCandidate.objects
            .filter(
                request__session__user=self.request.user
            )
            .select_related(
                "request",
                "request__session",
                "retrieved_image",
            )
        )

        request_id = self.request.query_params.get(
            "request"
        )

        if request_id:
            queryset = queryset.filter(
                request_id=request_id
            )

        return queryset.order_by(
            "-acquisition_date",
            "cloud_cover_pct",
        )


class AcquisitionCandidateDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AcquisitionCandidateSerializer

    def get_queryset(self):
        return (
            AcquisitionCandidate.objects
            .filter(
                request__session__user=self.request.user
            )
            .select_related(
                "request",
                "request__session",
                "retrieved_image",
            )
        )


class AcquireSatelliteCandidateView(APIView):
    """
    Queue retrieval of an actual provider asset.

    The candidate must belong to the authenticated user's session.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def post(
        self,
        request,
        candidate_id,
        *args,
        **kwargs,
    ):
        candidate = get_object_or_404(
            AcquisitionCandidate.objects.select_related(
                "request",
                "request__session",
            ),
            id=candidate_id,
            request__session__user=request.user,
        )

        if candidate.retrieved_image_id:
            return Response(
                {
                    "status": "DONE",
                    "candidate": (
                        AcquisitionCandidateSerializer(
                            candidate
                        ).data
                    ),
                    "detail": (
                        "This candidate has already "
                        "been retrieved."
                    ),
                }
            )

        from apps.satellite.tasks import (
            ingest_satellite_candidate_task,
        )

        task = (
            ingest_satellite_candidate_task.delay(
                str(candidate.id),
                str(request.user.id),
            )
        )

        return Response(
            {
                "status": "QUEUED",
                "candidate_id": str(
                    candidate.id
                ),
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# =============================================================================
# TEMPORAL OBSERVATIONS
# =============================================================================


class TemporalObservationListView(
    generics.ListAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = TemporalObservationSerializer

    def get_queryset(self):
        queryset = (
            TemporalObservation.objects
            .filter(
                scene__aoi__session__user=self.request.user
            )
            .select_related(
                "scene",
                "scene__aoi",
            )
        )

        scene_id = self.request.query_params.get(
            "scene"
        )

        if scene_id:
            queryset = queryset.filter(
                scene_id=scene_id
            )

        aoi_id = self.request.query_params.get(
            "aoi"
        )

        if aoi_id:
            queryset = queryset.filter(
                aoi_id=aoi_id
            )

        return queryset.order_by(
            "-observation_date"
        )


class TemporalObservationDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = TemporalObservationSerializer

    def get_queryset(self):
        return (
            TemporalObservation.objects
            .filter(
                scene__aoi__session__user=self.request.user
            )
            .select_related(
                "scene",
                "scene__aoi",
            )
        )


# =============================================================================
# CHANGE EVENTS
# =============================================================================


class ChangeEventListView(
    generics.ListAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = ChangeEventSerializer

    def get_queryset(self):
        queryset = (
            ChangeEvent.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "aoi",
                "scene_before",
                "scene_after",
            )
        )

        aoi_id = self.request.query_params.get(
            "aoi"
        )

        if aoi_id:
            queryset = queryset.filter(
                aoi_id=aoi_id
            )

        return queryset.order_by(
            "-created_at"
        )


class ChangeEventDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = ChangeEventSerializer

    def get_queryset(self):
        return (
            ChangeEvent.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "aoi",
                "scene_before",
                "scene_after",
            )
        )


# =============================================================================
# AOI MONITORING
# =============================================================================


class AOIMonitoringListCreateView(
    generics.ListCreateAPIView
):
    """
    Configure monitoring for a user-owned AOI.

    This only stores monitoring configuration.
    It does not fabricate alerts or change measurements.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AOIMonitoringSerializer

    def get_queryset(self):
        return (
            AOIMonitoring.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "aoi",
                "aoi__session",
            )
        )

    def perform_create(self, serializer):
        aoi_id = self.request.data.get("aoi")

        if not aoi_id:
            raise ValueError("aoi is required.")

        aoi = get_object_or_404(
            AreaOfInterest,
            id=aoi_id,
            session__user=self.request.user,
        )

        serializer.save(aoi=aoi)


class AOIMonitoringDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    serializer_class = AOIMonitoringSerializer

    def get_queryset(self):
        return (
            AOIMonitoring.objects
            .filter(
                aoi__session__user=self.request.user
            )
            .select_related(
                "aoi",
                "aoi__session",
            )
        )


# =============================================================================
# CATALOGUE SYNCHRONIZATION
# =============================================================================


class SatelliteCatalogueSyncView(APIView):
    """
    Trigger latest-available catalogue synchronization.

    This is catalogue synchronization, not live satellite video.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def post(self, request, *args, **kwargs):
        session_id = request.data.get("session_id")

        if session_id:
            _session_for_user(
                request.user,
                session_id,
            )

        from apps.satellite.sync import (
            sync_latest_available_catalogue,
        )

        task = (
            sync_latest_available_catalogue.delay()
        )

        return Response(
            {
                "status": "QUEUED",
                "task_id": task.id,
                "message": (
                    "Latest available satellite "
                    "catalogue synchronization queued."
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# =============================================================================
# SCENE EVIDENCE
# =============================================================================


class SatelliteSceneEvidenceView(APIView):
    """
    Return persisted scene metadata and temporal observations.

    No analytical metrics are manufactured here.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        scene_id,
        *args,
        **kwargs,
    ):
        scene = get_object_or_404(
            SatelliteScene.objects.select_related(
                "collection",
                "aoi",
            ),
            id=scene_id,
            aoi__session__user=request.user,
        )

        observations = (
            TemporalObservation.objects
            .filter(scene=scene)
            .order_by("-observation_date")
        )

        return Response(
            {
                "scene": SatelliteSceneSerializer(
                    scene
                ).data,
                "observations": (
                    TemporalObservationSerializer(
                        observations,
                        many=True,
                    ).data
                ),
                "evidence_available": (
                    observations.exists()
                ),
            }
        )


# =============================================================================
# CHANGE DETECTION REQUEST
# =============================================================================


class ChangeDetectionRequestView(APIView):
    """
    Register a relationship between two actual satellite scenes.

    This endpoint does NOT calculate or fabricate:
    - change polygons
    - change percentages
    - area
    - confidence
    - classification

    Actual analysis belongs to the agent/CV pipeline.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def post(self, request, *args, **kwargs):
        aoi_id = request.data.get("aoi_id")
        before_scene_id = request.data.get(
            "before_scene_id"
        )
        after_scene_id = request.data.get(
            "after_scene_id"
        )

        if not all(
            [
                aoi_id,
                before_scene_id,
                after_scene_id,
            ]
        ):
            return Response(
                {
                    "error": (
                        "aoi_id, before_scene_id and "
                        "after_scene_id are required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        aoi = get_object_or_404(
            AreaOfInterest,
            id=aoi_id,
            session__user=request.user,
        )

        before_scene = get_object_or_404(
            SatelliteScene,
            id=before_scene_id,
            aoi__session=aoi.session,
        )

        after_scene = get_object_or_404(
            SatelliteScene,
            id=after_scene_id,
            aoi__session=aoi.session,
        )

        if before_scene.id == after_scene.id:
            return Response(
                {
                    "error": (
                        "before_scene_id and "
                        "after_scene_id must refer "
                        "to different scenes."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        event = ChangeEvent.objects.create(
            aoi=aoi,
            scene_before=before_scene,
            scene_after=after_scene,
            change_type="UNKNOWN",
        )

        return Response(
            ChangeEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# SATELLITE CAPABILITY
# =============================================================================


class SatelliteCapabilityView(APIView):
    """
    Report configured satellite-provider capabilities.

    Provider availability is determined from the actual provider factory.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(self, request, *args, **kwargs):
        from apps.satellite.providers import (
            get_satellite_provider,
        )

        providers = []

        for provider_name in (
            "sentinel",
            "sentinel-2",
            "sentinel-1",
            "copernicus",
        ):
            try:
                provider = get_satellite_provider(
                    provider_name
                )
            except Exception:
                provider = None

            if provider is None:
                continue

            capabilities = {}

            try:
                capabilities = (
                    provider.capabilities()
                    if hasattr(
                        provider,
                        "capabilities",
                    )
                    else {}
                )
            except Exception:
                capabilities = {}

            providers.append(
                {
                    "name": provider_name,
                    "available": True,
                    "capabilities": capabilities,
                }
            )

        return Response(
            {
                "catalogue_mode": (
                    "latest_available_catalogue"
                ),
                "live_video": False,
                "providers": providers,
                "scientific_values_policy": (
                    "Only provider metadata or "
                    "actual raster-derived values "
                    "are exposed."
                ),
            }
        )


# =============================================================================
# LEGACY COMPATIBILITY NAMES
# =============================================================================


SatelliteSearchView = HistoricalCatalogueSearchView

AcquireCandidateView = (
    AcquireSatelliteCandidateView
)

SyncSatelliteCatalogueView = (
    SatelliteCatalogueSyncView
)

MonitoringPlanListCreateView = (
    AOIMonitoringListCreateView
)

MonitoringPlanDetailView = (
    AOIMonitoringDetailView
)

CandidateListView = (
    AcquisitionCandidateListView
)

CandidateSelectView = (
    AcquireSatelliteCandidateView
)
# There is intentionally NO MonitoringAlert alias.
#
# The current model layer does not define MonitoringAlert.
# Alerts should be introduced only when there is an actual persisted
# alert model and corresponding evidence-generation workflow.


__all__ = [
    "AreaOfInterestListCreateView",
    "AreaOfInterestDetailView",
    "SatelliteCollectionListView",
    "SatelliteSceneListView",
    "SatelliteSceneDetailView",
    "HistoricalCatalogueSearchView",
    "AcquisitionRequestListCreateView",
    "AcquisitionRequestDetailView",
    "AcquisitionCandidateListView",
    "AcquisitionCandidateDetailView",
    "AcquireSatelliteCandidateView",
    "CandidateListView",
    "CandidateSelectView",
    "TemporalObservationListView",
    "TemporalObservationDetailView",
    "ChangeEventListView",
    "ChangeEventDetailView",
    "AOIMonitoringListCreateView",
    "AOIMonitoringDetailView",
    "MonitoringPlanListCreateView",
    "MonitoringPlanDetailView",
    "SatelliteCatalogueSyncView",
    "SatelliteSceneEvidenceView",
    "ChangeDetectionRequestView",
    "SatelliteCapabilityView",
    "SatelliteSearchView",
    "AcquireCandidateView",
    "SyncSatelliteCatalogueView",
]