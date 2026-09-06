"""
Satellite acquisition API views for SatQuery-X.

Responsibilities:
- Create authenticated acquisition requests.
- List requests belonging to the authenticated user.
- Inspect a single acquisition request.
- Inspect candidate scenes belonging to that request.
- Accept/reject candidates without bypassing ownership.
- Queue real satellite ingestion.

No synthetic satellite scenes, fake footprints, fake dates, fake cloud
percentages, or fabricated download results are produced here.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AcquisitionCandidate,
    AcquisitionRequest,
)
from .serializers import (
    AcquisitionCandidateSerializer,
    AcquisitionRequestSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session / ownership helpers
# ---------------------------------------------------------------------------


def _get_session_for_user(
    request,
    session_id,
):
    """
    Resolve a session owned by the authenticated user.
    """

    try:
        from apps.sessions.models import Session
    except ImportError:
        try:
            from apps.core.models import Session
        except ImportError as exc:
            raise RuntimeError(
                "SatQuery-X Session model could not be imported."
            ) from exc

    try:
        session = Session.objects.get(
            pk=session_id,
        )
    except Session.DoesNotExist:
        raise Http404("Session not found.")

    if str(
        getattr(session, "user_id", "")
    ) != str(request.user.id):
        raise Http404("Session not found.")

    return session


def _get_owned_request(
    request,
    acquisition_request_id,
):
    try:
        acquisition_request = (
            AcquisitionRequest.objects
            .select_related("session")
            .get(
                pk=acquisition_request_id
            )
        )
    except AcquisitionRequest.DoesNotExist:
        raise Http404(
            "Acquisition request not found."
        )

    if str(
        getattr(
            acquisition_request.session,
            "user_id",
            "",
        )
    ) != str(request.user.id):
        raise Http404(
            "Acquisition request not found."
        )

    return acquisition_request


def _get_owned_candidate(
    request,
    candidate_id,
):
    try:
        candidate = (
            AcquisitionCandidate.objects
            .select_related(
                "request",
                "request__session",
            )
            .get(
                pk=candidate_id
            )
        )
    except AcquisitionCandidate.DoesNotExist:
        raise Http404(
            "Acquisition candidate not found."
        )

    if str(
        getattr(
            candidate.request.session,
            "user_id",
            "",
        )
    ) != str(request.user.id):
        raise Http404(
            "Acquisition candidate not found."
        )

    return candidate


# ---------------------------------------------------------------------------
# Acquisition request list/create
# ---------------------------------------------------------------------------


class AcquisitionRequestListCreateView(APIView):
    """
    GET:
        List acquisition requests owned by the authenticated user.

    POST:
        Create an acquisition request for an owned session.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        queryset = (
            AcquisitionRequest.objects
            .select_related("session")
            .filter(
                session__user=request.user
            )
            .order_by("-created_at")
        )

        session_id = request.query_params.get(
            "session_id"
        )

        if session_id:
            queryset = queryset.filter(
                session_id=session_id
            )

        serializer = AcquisitionRequestSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(
            serializer.data
        )

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
            session = _get_session_for_user(
                request,
                session_id,
            )
        except Http404:
            return Response(
                {
                    "detail": (
                        "Session not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = dict(
            request.data
        )

        payload["session"] = session.pk

        serializer = AcquisitionRequestSerializer(
            data=payload,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        acquisition_request = serializer.save(
            session=session
        )

        return Response(
            AcquisitionRequestSerializer(
                acquisition_request,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Acquisition request detail
# ---------------------------------------------------------------------------


class AcquisitionRequestDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        request_id,
    ):
        acquisition_request = _get_owned_request(
            request,
            request_id,
        )

        serializer = AcquisitionRequestSerializer(
            acquisition_request,
            context={"request": request},
        )

        return Response(
            serializer.data
        )

    @transaction.atomic
    def post(
        self,
        request,
        request_id,
    ):
        """
        Explicitly queue processing for an acquisition request.
        """

        acquisition_request = _get_owned_request(
            request,
            request_id,
        )

        task_name = (
            "process_acquisition_request_task"
        )

        try:
            from .tasks import (
                process_acquisition_request_task,
            )
        except ImportError:
            logger.exception(
                "Unable to import acquisition task."
            )

            return Response(
                {
                    "detail": (
                        "Satellite acquisition "
                        "service is unavailable."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            task = (
                process_acquisition_request_task
                .delay(
                    str(
                        acquisition_request.pk
                    )
                )
            )
        except Exception as exc:
            logger.exception(
                "Unable to queue acquisition request."
            )

            return Response(
                {
                    "detail": (
                        "Unable to queue satellite "
                        "acquisition."
                    ),
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "queued",
                "task_id": task.id,
                "task": task_name,
                "request_id": str(
                    acquisition_request.pk
                ),
                "provider": (
                    "Copernicus Data Space Ecosystem"
                ),
                "data_mode": (
                    "real_catalogue_search"
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# Candidate list
# ---------------------------------------------------------------------------


class AcquisitionCandidateListView(APIView):
    """
    List real catalogue candidates attached to an owned acquisition request.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        request_id,
    ):
        acquisition_request = _get_owned_request(
            request,
            request_id,
        )

        queryset = (
            AcquisitionCandidate.objects
            .filter(
                request=acquisition_request
            )
            .order_by(
                "-created_at"
            )
        )

        status_filter = request.query_params.get(
            "status"
        )

        if status_filter:
            queryset = queryset.filter(
                status__iexact=status_filter
            )

        serializer = AcquisitionCandidateSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(
            serializer.data
        )


# ---------------------------------------------------------------------------
# Candidate detail / decision
# ---------------------------------------------------------------------------


class AcquisitionCandidateDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        candidate_id,
    ):
        candidate = _get_owned_candidate(
            request,
            candidate_id,
        )

        serializer = AcquisitionCandidateSerializer(
            candidate,
            context={"request": request},
        )

        return Response(
            serializer.data
        )

    @transaction.atomic
    def patch(
        self,
        request,
        candidate_id,
    ):
        """
        Update an acquisition candidate decision.

        Supported actions:
            status = ACCEPTED
            status = REJECTED

        The candidate must belong to the user's request/session.
        """

        candidate = _get_owned_candidate(
            request,
            candidate_id,
        )

        new_status = request.data.get(
            "status"
        )

        if not new_status:
            return Response(
                {
                    "detail": (
                        "status is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_status = str(
            new_status
        ).strip().upper()

        allowed_statuses = {
            "ACCEPTED",
            "REJECTED",
        }

        if normalized_status not in allowed_statuses:
            return Response(
                {
                    "detail": (
                        "status must be ACCEPTED "
                        "or REJECTED."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --------------------------------------------------------------
        # Do not allow a candidate that has already been ingested to
        # silently transition back into a normal decision state.
        # --------------------------------------------------------------

        current_status = str(
            getattr(
                candidate,
                "status",
                "",
            )
            or ""
        ).upper()

        immutable_statuses = {
            "INGESTED",
            "DOWNLOADED",
            "PROCESSING",
            "COMPLETED",
        }

        if current_status in immutable_statuses:
            return Response(
                {
                    "detail": (
                        "This candidate has already "
                        "entered the ingestion pipeline "
                        "and cannot be manually changed."
                    ),
                    "current_status": current_status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        candidate.status = normalized_status

        candidate.save(
            update_fields=[
                "status",
            ]
        )

        return Response(
            AcquisitionCandidateSerializer(
                candidate,
                context={"request": request},
            ).data
        )


# ---------------------------------------------------------------------------
# Candidate ingestion
# ---------------------------------------------------------------------------


class AcquisitionCandidateIngestView(APIView):
    """
    Explicitly queue ingestion of an accepted real catalogue candidate.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(
        self,
        request,
        candidate_id,
    ):
        candidate = _get_owned_candidate(
            request,
            candidate_id,
        )

        candidate_status = str(
            getattr(
                candidate,
                "status",
                "",
            )
            or ""
        ).upper()

        if candidate_status != "ACCEPTED":
            return Response(
                {
                    "detail": (
                        "Only an ACCEPTED catalogue "
                        "candidate can be ingested."
                    ),
                    "current_status": candidate_status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            from .tasks import (
                ingest_satellite_candidate_task,
            )
        except ImportError:
            logger.exception(
                "Unable to import candidate ingestion task."
            )

            return Response(
                {
                    "detail": (
                        "Satellite ingestion "
                        "service is unavailable."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            task = (
                ingest_satellite_candidate_task
                .delay(
                    str(candidate.pk)
                )
            )
        except Exception:
            logger.exception(
                "Unable to queue satellite candidate ingestion."
            )

            return Response(
                {
                    "detail": (
                        "Unable to queue satellite "
                        "candidate ingestion."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "queued",
                "task_id": task.id,
                "candidate_id": str(
                    candidate.pk
                ),
                "stac_item_id": getattr(
                    candidate,
                    "stac_item_id",
                    None,
                ),
                "provider": (
                    getattr(
                        candidate,
                        "provider",
                        None,
                    )
                    or "copernicus_cdse"
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# Bulk candidate ingestion
# ---------------------------------------------------------------------------


class AcquisitionCandidateBulkIngestView(APIView):
    """
    Queue ingestion for multiple accepted candidates owned by the user.

    Request:
        {
            "candidate_ids": [
                "...",
                "..."
            ]
        }
    """

    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(
        self,
        request,
    ):
        candidate_ids = request.data.get(
            "candidate_ids"
        )

        if not isinstance(
            candidate_ids,
            list,
        ):
            return Response(
                {
                    "detail": (
                        "candidate_ids must be an array."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not candidate_ids:
            return Response(
                {
                    "detail": (
                        "candidate_ids cannot be empty."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(candidate_ids) > 50:
            return Response(
                {
                    "detail": (
                        "A maximum of 50 candidates "
                        "can be queued in one request."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .tasks import (
                ingest_satellite_candidate_task,
            )
        except ImportError:
            logger.exception(
                "Unable to import candidate ingestion task."
            )

            return Response(
                {
                    "detail": (
                        "Satellite ingestion "
                        "service is unavailable."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        queued = []
        rejected = []

        for candidate_id in candidate_ids:
            try:
                candidate = _get_owned_candidate(
                    request,
                    candidate_id,
                )
            except Http404:
                rejected.append(
                    {
                        "candidate_id": str(
                            candidate_id
                        ),
                        "reason": (
                            "Candidate not found."
                        ),
                    }
                )
                continue

            candidate_status = str(
                getattr(
                    candidate,
                    "status",
                    "",
                )
                or ""
            ).upper()

            if candidate_status != "ACCEPTED":
                rejected.append(
                    {
                        "candidate_id": str(
                            candidate.pk
                        ),
                        "reason": (
                            "Candidate is not ACCEPTED."
                        ),
                        "current_status": (
                            candidate_status
                        ),
                    }
                )
                continue

            try:
                task = (
                    ingest_satellite_candidate_task
                    .delay(
                        str(candidate.pk)
                    )
                )

                queued.append(
                    {
                        "candidate_id": str(
                            candidate.pk
                        ),
                        "task_id": task.id,
                    }
                )

            except Exception:
                logger.exception(
                    "Unable to queue candidate %s.",
                    candidate.pk,
                )

                rejected.append(
                    {
                        "candidate_id": str(
                            candidate.pk
                        ),
                        "reason": (
                            "Unable to queue ingestion."
                        ),
                    }
                )

        return Response(
            {
                "status": (
                    "queued"
                    if queued
                    else "nothing_queued"
                ),
                "queued": queued,
                "rejected": rejected,
            },
            status=(
                status.HTTP_202_ACCEPTED
                if queued
                else status.HTTP_400_BAD_REQUEST
            ),
        )


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------


AcquisitionRequestView = (
    AcquisitionRequestListCreateView
)

AcquisitionCandidateView = (
    AcquisitionCandidateListView
)


__all__ = [
    "AcquisitionRequestListCreateView",
    "AcquisitionRequestDetailView",
    "AcquisitionCandidateListView",
    "AcquisitionCandidateDetailView",
    "AcquisitionCandidateIngestView",
    "AcquisitionCandidateBulkIngestView",
    "AcquisitionRequestView",
    "AcquisitionCandidateView",
]