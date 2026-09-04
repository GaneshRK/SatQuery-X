"""Celery task for intelligence report generation (HTML / PDF) per §13.1."""

from __future__ import annotations

import io
from celery import shared_task
from django.core.files.base import ContentFile

from apps.reports.models import Report


@shared_task(bind=True)
def generate_report_task(self, report_id: str):
    report = Report.objects.get(id=report_id)
    session = report.session
    query = report.query

    # Generate PDF using ReportLab
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e3a8a"),
    )
    h2_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1e293b"),
    )
    body_style = styles["Normal"]

    # Header
    story.append(Paragraph("SATQUERY AI — INTELLIGENCE MISSION REPORT", title_style))
    story.append(Paragraph(f"<b>Session:</b> {session.name} | <b>ID:</b> {session.id}", body_style))
    story.append(Spacer(1, 15))

    # Executive Summary
    story.append(Paragraph("1. Executive Summary & Geospatial Evidence", h2_style))
    if query:
        story.append(Paragraph(f"<b>Primary Query:</b> {query.text}", body_style))
        story.append(Paragraph(f"<b>Detected Task:</b> {query.detected_task} ({query.detected_mode})", body_style))
        story.append(Paragraph(f"<b>Answer:</b> {query.answer or 'N/A'}", body_style))
        story.append(Paragraph(f"<b>Confidence:</b> {query.confidence or 0.0:.2f} (uncalibrated, conservative)", body_style))
    else:
        story.append(Paragraph("Comprehensive session summary covering all uploaded imagery assets.", body_style))
    story.append(Spacer(1, 15))

    # Imagery Assets Table
    story.append(Paragraph("2. Ingested Imagery Assets & Provenance", h2_style))
    img_data = [["Filename", "Sensor", "Modality", "CRS", "Resolution", "Status"]]
    for img in session.imagery_assets.all():
        img_data.append([
            img.original_filename[:20],
            img.sensor,
            img.modality,
            img.crs or "N/A",
            f"{img.resolution_m:.1f}m" if img.resolution_m else "N/A",
            img.processing_status,
        ])
    t_imgs = Table(img_data, colWidths=[120, 70, 70, 70, 70, 70])
    t_imgs.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(t_imgs)
    story.append(Spacer(1, 15))

    # Model Audit Section (Honest Labeling per §2 & §9)
    story.append(Paragraph("3. Model Registry Audit & Honest Adaptation Disclosure", h2_style))
    model_rows = [["Tool", "Model Base", "Adaptation Status", "Latency", "Status"]]
    if query:
        for step in query.execution_steps.all():
            model_rows.append([
                step.tool_name,
                step.model_version,
                "BASELINE (Non-Fine-Tuned)",
                f"{step.latency_ms}ms" if step.latency_ms else "N/A",
                step.status,
            ])
    t_models = Table(model_rows, colWidths=[120, 110, 140, 50, 50])
    t_models.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(t_models)

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    filename = f"report_{report.id}.pdf"
    report.file.save(filename, ContentFile(pdf_bytes))
    report.status = "READY"
    report.save()

    return {"report_id": str(report.id), "status": "READY"}
