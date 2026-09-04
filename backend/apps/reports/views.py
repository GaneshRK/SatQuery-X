from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.queries.models import Query
from apps.reports.models import Report
from apps.reports.tasks import generate_report_task
from apps.sessions.models import Session


class SessionReportListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        reports = session.reports.all()
        data = [
            {
                "id": str(r.id),
                "format": r.format,
                "status": r.status,
                "generated_at": r.generated_at,
            }
            for r in reports
        ]
        return Response(data)

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        query_id = request.data.get("query_id")
        fmt = request.data.get("format", "PDF").upper()

        query = None
        if query_id:
            query = get_object_or_404(Query, id=query_id, session_id=session_id)

        report = Report.objects.create(
            session=session,
            query=query,
            format=fmt,
            status="GENERATING",
        )

        log_audit_event(
            request.user, "GENERATE_REPORT", "Report", str(report.id),
            {"format": fmt, "session_id": str(session.id)}
        )

        try:
            generate_report_task.delay(str(report.id))
        except Exception:
            generate_report_task(str(report.id))

        report.refresh_from_db()

        return Response(
            {
                "report_id": str(report.id),
                "format": report.format,
                "status": report.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ReportDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, report_id):
        report = get_object_or_404(Report, id=report_id, session_id=session_id)
        return Response({
            "id": str(report.id),
            "format": report.format,
            "status": report.status,
            "generated_at": report.generated_at,
            "has_file": bool(report.file),
        })


class ReportDownloadView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, session_id, report_id):
        report = get_object_or_404(Report, id=report_id, session_id=session_id)
        if not report.file:
            raise Http404("Report file has not yet finished generating.")
        content_type = "application/pdf" if report.format == "PDF" else "text/html"
        ext = "html" if report.format == "HTML" else "pdf"
        return FileResponse(report.file.open("rb"), content_type=content_type, filename=f"satquery_report_{report.id}.{ext}")
