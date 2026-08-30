"""Report generation and export endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status

from backend.api.schemas import ReportGenerateRequest, ReportResponse
from backend.db.store import get_datastore
from backend.reports.generator import ReportGenerator

router = APIRouter(prefix="/v1/sessions/{session_id}/report", tags=["Reports"])


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    session_id: uuid.UUID,
    payload: ReportGenerateRequest,
) -> ReportResponse:
    store = get_datastore()
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    query = store.get_query(payload.query_id)
    if not query or query.session_id != session_id:
        raise HTTPException(status_code=404, detail="Query not found in this session.")

    report_id = uuid.uuid4()
    generator = ReportGenerator()
    result = generator.generate_and_save(
        session=session,
        query=query,
        report_id=report_id,
        title=payload.title,
        fmt=payload.format,
        analyst_notes=payload.analyst_notes,
    )

    store.add_report(
        report_id=report_id,
        report_data={
            "report_id": str(report_id),
            "session_id": str(session_id),
            "query_id": str(query.id),
            "format": payload.format,
            "html_content": result["html_content"],
            "download_url": result["download_url"],
            "html_url": result["html_url"],
            "created_at": datetime.now(timezone.utc),
        },
    )

    return ReportResponse(
        report_id=report_id,
        query_id=query.id,
        format=payload.format,
        download_url=result["download_url"],
        html_preview_url=f"/api/v1/sessions/{session_id}/report/{report_id}/view",
        created_at=datetime.now(timezone.utc),
    )


@router.get("/{report_id}/view")
async def view_report_html(session_id: uuid.UUID, report_id: uuid.UUID) -> Response:
    store = get_datastore()
    report = store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    return Response(content=report["html_content"], media_type="text/html")
