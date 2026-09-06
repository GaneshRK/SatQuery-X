"""
API views for SatQuery-X intelligence reports.
"""

from __future__ import annotations

import logging

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, views
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.queries.models import Query
from apps.sessions.permissions import get_session_for_user_or_403

from .models import Report
from .serializers import (
    ReportCreateSerializer,
    ReportListSerializer,
    ReportSerializer,
)
from .tasks import generate_report_task


logger = logging.getLogger(__name__)


def _get_owned_session(session_id, user):
    """
    Resolve a session only when the authenticated user has access to it.
    """
    return get_session_for_user_or_403(session_id, user)


def _get_owned_report(session_id, report_id, user):
    """
    Resolve a report belonging to a user-owned session.
    """
    session = _get_owned_session(session_id, user)

    report = get_object_or_404(
        Report.objects.select_related("session", "query"),
        id=report_id,
        session_id=session.id,
    )

    return session, report


class SessionReportListCreateView(views.APIView):
    """
    List and create reports for a specific analysis session.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = _get_owned_session(session_id, request.user)

        reports = (
            Report.objects
            .filter(session_id=session.id)
            .select_related("query")
            .order_by("-generated_at")
        )

        serializer = ReportListSerializer(
            reports,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "session_id": str(session.id),
                "count": reports.count(),
                "reports": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, session_id):
        session = _get_owned_session(session_id, request.user)

        serializer = ReportCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "session": session,
            },
        )

        serializer.is_valid(raise_exception=True)

        query = None
        query_id = serializer.validated_data.get("query_id")

        if query_id:
            query = get_object_or_404(
                Query,
                id=query_id,
                session_id=session.id,
            )

            if query.user_id != request.user.id:
                raise PermissionDenied(
                    "You do not have access to this query."
                )

        report = Report.objects.create(
            session=session,
            query=query,
            format=serializer.validated_data["format"],
            status="GENERATING",
            source_snapshot=_build_source_snapshot(
                session=session,
                query=query,
            ),
            provenance=_build_provenance(
                query=query,
            ),
        )

        log_audit_event(
            request.user,
            "GENERATE_REPORT",
            "Report",
            str(report.id),
            {
                "format": report.format,
                "session_id": str(session.id),
                "query_id": str(query.id) if query else None,
            },
        )

        try:
            task_result = generate_report_task.delay(
                str(report.id)
            )

            logger.info(
                "Report generation queued: report=%s task=%s",
                report.id,
                getattr(task_result, "id", None),
            )

        except Exception:
            logger.exception(
                "Unable to queue report generation task: %s",
                report.id,
            )

            # Development / no-Celery fallback.
            #
            # The task itself handles errors and marks the report FAILED.
            try:
                generate_report_task(str(report.id))
            except Exception:
                logger.exception(
                    "Synchronous report generation failed: %s",
                    report.id,
                )

        report.refresh_from_db()

        return Response(
            ReportSerializer(
                report,
                context={"request": request},
            ).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ReportDetailView(views.APIView):
    """
    Retrieve metadata and generation state for a report.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, report_id):
        _, report = _get_owned_report(
            session_id,
            report_id,
            request.user,
        )

        return Response(
            ReportSerializer(
                report,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )


class ReportDownloadView(views.APIView):
    """
    Download a completed report.

    Authentication is required.  Reports are never publicly accessible
    because they may contain sensitive imagery analysis and user data.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, report_id):
        _, report = _get_owned_report(
            session_id,
            report_id,
            request.user,
        )

        if report.status != "READY":
            if report.status == "FAILED":
                raise Http404(
                    "This report could not be generated."
                )

            raise Http404(
                "The report is still being generated."
            )

        if not report.file:
            raise Http404(
                "The generated report file is unavailable."
            )

        if report.format == "PDF":
            content_type = "application/pdf"
            extension = "pdf"

        elif report.format == "HTML":
            content_type = "text/html; charset=utf-8"
            extension = "html"

        else:
            raise Http404(
                "Unsupported report format."
            )

        filename = (
            f"satquery_report_{report.id}.{extension}"
        )

        log_audit_event(
            request.user,
            "DOWNLOAD_REPORT",
            "Report",
            str(report.id),
            {
                "format": report.format,
                "session_id": str(report.session_id),
            },
        )

        try:
            file_handle = report.file.open("rb")
        except Exception:
            logger.exception(
                "Unable to open report file: %s",
                report.id,
            )
            raise Http404(
                "The report file is unavailable."
            )

        return FileResponse(
            file_handle,
            content_type=content_type,
            as_attachment=True,
            filename=filename,
        )


def _build_source_snapshot(*, session, query):
    """
    Capture the actual report inputs.

    This is intentionally metadata-only.  No scientific measurement is
    calculated here.
    """
    snapshot = {
        "session_id": str(session.id),
        "query_id": str(query.id) if query else None,
        "query_status": query.status if query else None,
    }

    if query:
        snapshot.update(
            {
                "input_asset_ids": [
                    str(asset.id)
                    for asset in query.input_assets.all()
                ],
                "legacy_image_id": (
                    str(query.image_id)
                    if query.image_id
                    else None
                ),
                "image_pair_id": (
                    str(query.image_pair_id)
                    if query.image_pair_id
                    else None
                ),
                "execution_step_count": (
                    query.execution_steps.count()
                ),
                "evidence_region_count": (
                    query.evidence_regions.count()
                    if hasattr(query, "evidence_regions")
                    else 0
                ),
            }
        )

    return snapshot


def _build_provenance(*, query):
    """
    Build a compact, auditable provenance summary.

    This deliberately does not expose chain-of-thought.
    """
    if not query:
        return {
            "source": "session",
            "query_linked": False,
        }

    steps = []

    for step in query.execution_steps.all():
        steps.append(
            {
                "step_number": step.step_number,
                "tool_name": step.tool_name,
                "agent_type": getattr(
                    step,
                    "agent_type",
                    "",
                ),
                "model_version": step.model_version,
                "status": step.status,
            }
        )

    return {
        "source": "satquery_analysis_pipeline",
        "query_linked": True,
        "query_id": str(query.id),
        "detected_mode": query.detected_mode,
        "detected_task": query.detected_task,
        "execution_steps": steps,
    }