"""Report generator supporting both HTML and PDF export with Jinja2."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from backend.db.store import StoredQuery, StoredSession
from backend.storage.s3 import ObjectStorage


class ReportGenerator:
    def __init__(self) -> None:
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
        self.template = self.env.get_template("report_template.html")
        self.storage = ObjectStorage()

    def generate_html_report(
        self,
        session: StoredSession,
        query: StoredQuery,
        title: str = "SatQuery-X Geospatial Intelligence Report",
        analyst_notes: str | None = None,
    ) -> str:
        td = query.trace_dict
        context = {
            "title": title,
            "query_id": str(query.id),
            "session_id": str(session.id),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "query": query.text,
            "detected_mode": query.detected_mode,
            "task_classification": query.task_classification,
            "answer": td.get("answer", "No answer produced."),
            "confidence": td.get("confidence", 0.0),
            "plan": td.get("plan", []),
            "outputs": td.get("outputs", {}),
            "evidence": td.get("evidence", {}),
            "timings_ms": td.get("timings_ms", {}),
            "analyst_notes": analyst_notes,
        }
        return self.template.render(context)

    def generate_and_save(
        self,
        session: StoredSession,
        query: StoredQuery,
        report_id: uuid.UUID,
        title: str = "SatQuery-X Geospatial Intelligence Report",
        fmt: str = "html",
        analyst_notes: str | None = None,
    ) -> dict[str, str]:
        html_content = self.generate_html_report(session, query, title, analyst_notes)
        html_key = f"sessions/{session.id}/reports/{report_id}.html"
        self.storage.upload_bytes(html_key, html_content.encode("utf-8"), "text/html")

        pdf_key = None
        # PDF generation fallback: serve HTML as printable document or generate PDF
        try:
            from weasyprint import HTML

            pdf_bytes = HTML(string=html_content).write_pdf()
            pdf_key = f"sessions/{session.id}/reports/{report_id}.pdf"
            self.storage.upload_bytes(pdf_key, pdf_bytes, "application/pdf")
        except Exception:
            pass

        return {
            "html_key": html_key,
            "html_url": self.storage.get_presigned_url(html_key),
            "pdf_key": pdf_key,
            "download_url": self.storage.get_presigned_url(pdf_key if pdf_key and fmt == "pdf" else html_key),
            "html_content": html_content,
        }
