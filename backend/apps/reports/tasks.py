"""
Celery tasks for SatQuery-X report generation.

Reports are renderers of already-produced analysis evidence.

This module does not perform satellite analysis, image classification,
change detection, geospatial inference, or scientific measurement.

It only renders information already persisted by the analysis pipeline.

Rules:
- Never invent measurements.
- Never invent coordinates.
- Never invent confidence values.
- Never invent sensor metadata.
- Never invent model results.
- Never fabricate imagery.
- Never convert missing metadata into guessed values.
- Never expose private chain-of-thought.
- Preserve a concise, auditable execution/evidence trace.
"""

from __future__ import annotations

import html
import io
import logging
from typing import Any

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.reports.models import Report

logger = logging.getLogger(__name__)

REPORT_RENDERER_VERSION = "3.0-grounded"


# ============================================================================
# SAFE FORMATTING
# ============================================================================

def _safe_text(
    value: Any,
    default: str = "Not available",
) -> str:
    if value is None:
        return default

    if isinstance(value, str):
        text = value.strip()
        return text if text else default

    try:
        text = str(value).strip()
    except Exception:
        return default

    return text if text else default


def _escape(
    value: Any,
    default: str = "Not available",
) -> str:
    return html.escape(
        _safe_text(value, default),
        quote=True,
    )


def _format_number(
    value: Any,
    decimals: int = 4,
    suffix: str = "",
) -> str:
    if value is None or isinstance(value, bool):
        return "Not available"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"

    return f"{number:.{decimals}f}{suffix}"


def _format_confidence(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return "Not reported"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not reported"

    if 0.0 <= number <= 1.0:
        return f"{number * 100:.1f}%"

    if 1.0 < number <= 100.0:
        return f"{number:.1f}%"

    return "Not reported"


def _format_value(value: Any) -> str:
    if value is None:
        return "Not available"

    if isinstance(value, dict):
        parts = []

        for key, item in value.items():
            parts.append(
                f"{_safe_text(key)}: {_format_value(item)}"
            )

        return "; ".join(parts) if parts else "Not available"

    if isinstance(value, (list, tuple, set)):
        values = [
            _format_value(item)
            for item in value
        ]

        return ", ".join(values) if values else "Not available"

    return _safe_text(value)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0

    return False


# ============================================================================
# QUERY EVIDENCE
# ============================================================================

def _query_measurements(query) -> dict[str, Any]:
    if query is None:
        return {}

    candidates = [
        getattr(query, "evidence_bundle", None),
        getattr(query, "evidence_graph", None),
    ]

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        measurements = candidate.get("measurements")

        if isinstance(measurements, dict):
            return measurements

    return {}


def _query_evidence_bundle(query) -> dict[str, Any]:
    if query is None:
        return {}

    bundle = getattr(
        query,
        "evidence_bundle",
        None,
    )

    return bundle if isinstance(bundle, dict) else {}


def _query_answer_contract(query) -> dict[str, Any]:
    if query is None:
        return {}

    contract = getattr(
        query,
        "answer_contract",
        None,
    )

    return contract if isinstance(contract, dict) else {}


def _query_evidence_regions(query) -> list[Any]:
    if query is None:
        return []

    manager = getattr(
        query,
        "evidence_regions",
        None,
    )

    if manager is None:
        return []

    try:
        return list(manager.all())
    except Exception:
        logger.exception(
            "Unable to load evidence regions for query %s",
            getattr(query, "id", None),
        )
        return []


def _query_execution_steps(query) -> list[Any]:
    if query is None:
        return []

    manager = getattr(
        query,
        "execution_steps",
        None,
    )

    if manager is None:
        return []

    try:
        return list(
            manager.all().order_by("step_number")
        )
    except Exception:
        logger.exception(
            "Unable to load execution steps for query %s",
            getattr(query, "id", None),
        )
        return []


# ============================================================================
# QUERY / SESSION ASSETS
# ============================================================================

def _query_input_assets(query) -> list[Any]:
    if query is None:
        return []

    assets: list[Any] = []

    manager = getattr(
        query,
        "input_assets",
        None,
    )

    if manager is not None:
        try:
            assets.extend(
                list(manager.all())
            )
        except Exception:
            logger.exception(
                "Unable to load input assets for query %s",
                getattr(query, "id", None),
            )

    legacy_image = getattr(
        query,
        "image",
        None,
    )

    if legacy_image is not None:
        legacy_id = getattr(
            legacy_image,
            "id",
            None,
        )

        existing_ids = {
            getattr(asset, "id", None)
            for asset in assets
        }

        if legacy_id not in existing_ids:
            assets.append(legacy_image)

    return assets


def _session_assets(session) -> list[Any]:
    if session is None:
        return []

    for manager_name in (
        "imagery_assets",
        "images",
    ):
        manager = getattr(
            session,
            manager_name,
            None,
        )

        if manager is None:
            continue

        try:
            return list(manager.all())
        except Exception:
            continue

    return []


def _asset_rows(
    session,
    query=None,
) -> list[dict[str, Any]]:
    assets = _query_input_assets(query)

    if not assets:
        assets = _session_assets(session)

    rows: list[dict[str, Any]] = []

    for asset in assets:
        acquisition = getattr(
            asset,
            "acquisition_datetime",
            None,
        )

        filename = (
            getattr(
                asset,
                "original_filename",
                None,
            )
            or getattr(
                asset,
                "filename",
                None,
            )
        )

        if not filename:
            file_obj = getattr(
                asset,
                "file",
                None,
            )

            filename = getattr(
                file_obj,
                "name",
                None,
            )

        rows.append(
            {
                "id": getattr(asset, "id", None),
                "filename": filename,
                "sensor": getattr(asset, "sensor", None),
                "modality": getattr(asset, "modality", None),
                "crs": getattr(asset, "crs", None),
                "resolution_m": getattr(
                    asset,
                    "resolution_m",
                    None,
                ),
                "width": getattr(asset, "width", None),
                "height": getattr(asset, "height", None),
                "band_count": getattr(
                    asset,
                    "band_count",
                    None,
                ),
                "dtype": getattr(asset, "dtype", None),
                "processing_status": getattr(
                    asset,
                    "processing_status",
                    None,
                ),
                "is_georeferenced": getattr(
                    asset,
                    "is_georeferenced",
                    None,
                ),
                "acquisition_datetime": acquisition,
            }
        )

    return rows


# ============================================================================
# PROVENANCE
# ============================================================================

def _build_source_snapshot(
    report: Report,
    session,
    query,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "session_id": (
            str(report.session_id)
            if getattr(report, "session_id", None)
            else None
        ),
        "query_id": (
            str(query.id)
            if query is not None
            else None
        ),
        "format": getattr(
            report,
            "format",
            None,
        ),
        "renderer_version": REPORT_RENDERER_VERSION,
    }

    if query is not None:
        input_assets = _query_input_assets(query)

        snapshot.update(
            {
                "query_status": getattr(
                    query,
                    "status",
                    None,
                ),
                "input_asset_ids": [
                    str(asset.id)
                    for asset in input_assets
                    if getattr(asset, "id", None)
                ],
                "legacy_image_id": (
                    str(query.image_id)
                    if getattr(query, "image_id", None)
                    else None
                ),
                "image_pair_id": (
                    str(query.image_pair_id)
                    if getattr(query, "image_pair_id", None)
                    else None
                ),
                "detected_mode": getattr(
                    query,
                    "detected_mode",
                    None,
                ),
                "detected_task": getattr(
                    query,
                    "detected_task",
                    None,
                ),
                "execution_step_count": len(
                    _query_execution_steps(query)
                ),
                "evidence_region_count": len(
                    _query_evidence_regions(query)
                ),
            }
        )

    return snapshot


def _build_provenance(
    report: Report,
    query,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "renderer": "SatQuery-X report renderer",
        "renderer_version": REPORT_RENDERER_VERSION,
        "query_linked": query is not None,
        "generated_at": timezone.now().isoformat(),
    }

    if query is None:
        return provenance

    steps = _query_execution_steps(query)

    provenance.update(
        {
            "query_id": str(query.id),
            "detected_mode": getattr(
                query,
                "detected_mode",
                None,
            ),
            "detected_task": getattr(
                query,
                "detected_task",
                None,
            ),
            "steps": [
                {
                    "step_number": getattr(
                        step,
                        "step_number",
                        None,
                    ),
                    "tool_name": getattr(
                        step,
                        "tool_name",
                        None,
                    ),
                    "agent_type": getattr(
                        step,
                        "agent_type",
                        None,
                    ),
                    "model_version": getattr(
                        step,
                        "model_version",
                        None,
                    ),
                    "status": getattr(
                        step,
                        "status",
                        None,
                    ),
                    "latency_ms": getattr(
                        step,
                        "latency_ms",
                        None,
                    ),
                }
                for step in steps
            ],
        }
    )

    return provenance


# ============================================================================
# EVIDENCE RENDERING
# ============================================================================

def _evidence_region_rows(
    query,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for region in _query_evidence_regions(query):
        rows.append(
            {
                "class_name": getattr(
                    region,
                    "class_name",
                    None,
                ),
                "confidence": getattr(
                    region,
                    "confidence",
                    None,
                ),
                "area_km2": getattr(
                    region,
                    "area_km2",
                    None,
                ),
                "geometry": getattr(
                    region,
                    "geometry",
                    None,
                ),
            }
        )

    return rows


def _render_measurements_html(query) -> str:
    measurements = _query_measurements(query)

    if not measurements:
        return """
        <div class="empty">
          No quantitative measurements were reported by the analysis.
        </div>
        """

    rendered: list[str] = []

    for key, value in measurements.items():
        key_html = _escape(key)
        value_html = _escape(
            _format_value(value)
        )

        rendered.append(
            f"""
            <tr>
              <td>{key_html}</td>
              <td>{value_html}</td>
            </tr>
            """
        )

    rows_html = "".join(rendered)

    return f"""
    <table>
      <thead>
        <tr>
          <th>Measurement</th>
          <th>Reported Value</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _render_evidence_html(query) -> str:
    rows = _evidence_region_rows(query)

    if not rows:
        return """
        <div class="empty">
          No polygonal evidence regions were recorded for this analysis.
        </div>
        """

    rendered: list[str] = []

    for row in rows:
        area = row["area_km2"]

        if area is not None:
            area_text = _format_number(
                area,
                4,
                " km²",
            )
        else:
            area_text = "Not reported"

        hectares_text = "Not reported"

        if area is not None:
            try:
                hectares_text = (
                    f"{float(area) * 100:.2f} ha"
                )
            except (TypeError, ValueError):
                hectares_text = "Not reported"

        class_html = _escape(
            row["class_name"]
        )

        confidence_html = _escape(
            _format_confidence(
                row["confidence"]
            )
        )

        area_html = _escape(area_text)
        hectares_html = _escape(
            hectares_text
        )

        rendered.append(
            f"""
            <tr>
              <td>{class_html}</td>
              <td>{confidence_html}</td>
              <td>{area_html}</td>
              <td>{hectares_html}</td>
            </tr>
            """
        )

    rows_html = "".join(rendered)

    return f"""
    <table>
      <thead>
        <tr>
          <th>Region / Class</th>
          <th>Confidence</th>
          <th>Area</th>
          <th>Area (ha)</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _render_assets_html(
    session,
    query,
) -> str:
    rows = _asset_rows(
        session,
        query,
    )

    if not rows:
        return """
        <div class="empty">
          No imagery assets are associated with this analysis.
        </div>
        """

    rendered: list[str] = []

    for row in rows:
        acquisition = row["acquisition_datetime"]

        acquisition_text = (
            str(acquisition)
            if acquisition is not None
            else "Not available"
        )

        filename_html = _escape(
            row["filename"]
        )

        sensor_html = _escape(
            row["sensor"]
        )

        modality_html = _escape(
            row["modality"]
        )

        crs_html = _escape(
            row["crs"]
        )

        resolution_html = _escape(
            _format_number(
                row["resolution_m"],
                3,
                " m",
            )
        )

        status_html = _escape(
            row["processing_status"]
        )

        acquisition_html = _escape(
            acquisition_text
        )

        rendered.append(
            f"""
            <tr>
              <td>{filename_html}</td>
              <td>{sensor_html}</td>
              <td>{modality_html}</td>
              <td>{crs_html}</td>
              <td>{resolution_html}</td>
              <td>{status_html}</td>
              <td>{acquisition_html}</td>
            </tr>
            """
        )

    rows_html = "".join(rendered)

    return f"""
    <table>
      <thead>
        <tr>
          <th>Filename</th>
          <th>Sensor</th>
          <th>Modality</th>
          <th>CRS</th>
          <th>Resolution</th>
          <th>Processing Status</th>
          <th>Acquisition</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _render_execution_html(query) -> str:
    steps = _query_execution_steps(query)

    if not steps:
        return """
        <div class="empty">
          No execution steps were recorded.
        </div>
        """

    rendered: list[str] = []

    for step in steps:
        step_html = _escape(
            getattr(
                step,
                "step_number",
                None,
            )
        )

        tool_html = _escape(
            getattr(
                step,
                "tool_name",
                None,
            )
        )

        agent_html = _escape(
            getattr(
                step,
                "agent_type",
                None,
            )
        )

        version_html = _escape(
            getattr(
                step,
                "model_version",
                None,
            )
        )

        status_html = _escape(
            getattr(
                step,
                "status",
                None,
            )
        )

        latency_html = _escape(
            _format_number(
                getattr(
                    step,
                    "latency_ms",
                    None,
                ),
                0,
                " ms",
            )
        )

        rendered.append(
            f"""
            <tr>
              <td>{step_html}</td>
              <td>{tool_html}</td>
              <td>{agent_html}</td>
              <td>{version_html}</td>
              <td>{status_html}</td>
              <td>{latency_html}</td>
            </tr>
            """
        )

    rows_html = "".join(rendered)

    return f"""
    <table>
      <thead>
        <tr>
          <th>Step</th>
          <th>Tool</th>
          <th>Agent</th>
          <th>Model / Version</th>
          <th>Status</th>
          <th>Latency</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _render_answer_contract_html(query) -> str:
    contract = _query_answer_contract(query)

    if not contract:
        return """
        <div class="empty">
          No answer contract was recorded.
        </div>
        """

    rendered: list[str] = []

    for key, value in contract.items():
        key_html = _escape(key)
        value_html = _escape(
            _format_value(value)
        )

        rendered.append(
            f"""
            <tr>
              <td>{key_html}</td>
              <td>{value_html}</td>
            </tr>
            """
        )

    rows_html = "".join(rendered)

    return f"""
    <table>
      <thead>
        <tr>
          <th>Evidence Contract Field</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


# ============================================================================
# HTML REPORT
# ============================================================================

def _generate_html_report(
    report: Report,
    session,
    query,
) -> str:
    query_text = (
        getattr(query, "text", None)
        if query is not None
        else None
    )

    if _is_empty(query_text):
        query_text = "Session-level report"

    answer = (
        getattr(query, "answer", None)
        if query is not None
        else None
    )

    if _is_empty(answer):
        answer = "No final answer was recorded."

    detected_task = (
        getattr(query, "detected_task", None)
        if query is not None
        else None
    )

    detected_mode = (
        getattr(query, "detected_mode", None)
        if query is not None
        else None
    )

    confidence = (
        _format_confidence(
            getattr(
                query,
                "confidence",
                None,
            )
        )
        if query is not None
        else "Not reported"
    )

    session_name = getattr(
        session,
        "name",
        None,
    )

    report_id = getattr(
        report,
        "id",
        None,
    )

    generated_at = getattr(
        report,
        "generated_at",
        None,
    )

    session_html = _escape(session_name)
    report_id_html = _escape(report_id)
    generated_html = _escape(generated_at)
    format_html = _escape(
        getattr(report, "format", None)
    )
    task_html = _escape(detected_task)
    mode_html = _escape(detected_mode)
    confidence_html = _escape(confidence)
    query_html = _escape(query_text)
    answer_html = _escape(answer)

    measurements_html = _render_measurements_html(query)
    evidence_html = _render_evidence_html(query)
    assets_html = _render_assets_html(
        session,
        query,
    )
    execution_html = _render_execution_html(query)
    contract_html = _render_answer_contract_html(query)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
  >
  <title>
    SatQuery-X Report — {session_html}
  </title>

  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: #f8fafc;
      color: #0f172a;
      font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    }}

    .container {{
      width: min(1180px, calc(100% - 40px));
      margin: 0 auto;
      padding: 42px 0 64px;
    }}

    header {{
      border-bottom: 1px solid #cbd5e1;
      padding-bottom: 28px;
      margin-bottom: 28px;
    }}

    .eyebrow {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e2e8f0;
      color: #334155;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}

    h1 {{
      margin: 12px 0 6px;
      font-size: 30px;
      line-height: 1.15;
    }}

    h2 {{
      margin: 0 0 16px;
      font-size: 19px;
    }}

    .muted {{
      color: #64748b;
    }}

    .meta {{
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 20px;
    }}

    .meta-card {{
      padding: 14px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
    }}

    .meta-label {{
      display: block;
      margin-bottom: 5px;
      color: #64748b;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .06em;
    }}

    .section {{
      margin-bottom: 22px;
      padding: 22px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
    }}

    .answer {{
      padding: 18px;
      background: #f1f5f9;
      border-left: 4px solid #334155;
      border-radius: 8px;
      line-height: 1.65;
      white-space: pre-wrap;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th,
    td {{
      padding: 10px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      vertical-align: top;
      word-break: break-word;
    }}

    th {{
      background: #f8fafc;
      color: #475569;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}

    .empty {{
      padding: 16px;
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      border-radius: 8px;
      color: #64748b;
    }}

    footer {{
      margin-top: 34px;
      padding-top: 18px;
      border-top: 1px solid #cbd5e1;
      color: #64748b;
      font-size: 11px;
      line-height: 1.6;
    }}

    @media print {{
      body {{
        background: white;
      }}

      .container {{
        width: 100%;
        padding: 0;
      }}

      .section {{
        break-inside: avoid;
        box-shadow: none;
      }}
    }}
  </style>
</head>

<body>
  <div class="container">

    <header>
      <span class="eyebrow">
        SatQuery-X Intelligence Report
      </span>

      <h1>
        Remote-Sensing Analysis Report
      </h1>

      <div class="muted">
        Session:
        <strong>{session_html}</strong>
        &nbsp;·&nbsp;
        Report ID:
        <strong>{report_id_html}</strong>
      </div>

      <div class="meta">
        <div class="meta-card">
          <span class="meta-label">Generated</span>
          {generated_html}
        </div>

        <div class="meta-card">
          <span class="meta-label">Format</span>
          {format_html}
        </div>

        <div class="meta-card">
          <span class="meta-label">Task</span>
          {task_html}
        </div>

        <div class="meta-card">
          <span class="meta-label">Mode</span>
          {mode_html}
        </div>

        <div class="meta-card">
          <span class="meta-label">Reported Confidence</span>
          {confidence_html}
        </div>
      </div>
    </header>

    <section class="section">
      <h2>1. Query and Finding</h2>

      <p>
        <strong>Query:</strong>
        {query_html}
      </p>

      <div class="answer">
        {answer_html}
      </div>
    </section>

    <section class="section">
      <h2>2. Quantitative Evidence</h2>
      {measurements_html}
    </section>

    <section class="section">
      <h2>3. Spatial Evidence</h2>
      {evidence_html}
    </section>

    <section class="section">
      <h2>4. Imagery and Provenance</h2>
      {assets_html}
    </section>

    <section class="section">
      <h2>5. Analysis Execution Trace</h2>
      {execution_html}
    </section>

    <section class="section">
      <h2>6. Evidence Contract</h2>
      {contract_html}
    </section>

    <footer>
      SatQuery-X generates reports exclusively from evidence available
      in the analysis pipeline.

      Missing metadata, measurements, coordinates, and confidence values
      are explicitly reported as unavailable rather than estimated.

      The execution trace is an auditable action/evidence summary and
      does not expose private model reasoning.
    </footer>

  </div>
</body>
</html>
"""


# ============================================================================
# PDF REPORT
# ============================================================================

def _generate_pdf_report(
    report: Report,
    session,
    query,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import (
        ParagraphStyle,
        getSampleStyleSheet,
    )
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
        title="SatQuery-X Intelligence Report",
        author="SatQuery-X",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "SatQueryTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "SatQuerySubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14,
    )

    heading_style = ParagraphStyle(
        "SatQueryHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=17,
        spaceBefore=10,
        spaceAfter=7,
    )

    body_style = ParagraphStyle(
        "SatQueryBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
    )

    small_style = ParagraphStyle(
        "SatQuerySmall",
        parent=body_style,
        fontSize=7.5,
        leading=10,
    )

    story: list[Any] = []

    session_text = _escape(
        getattr(session, "name", None)
    )

    report_id_text = _escape(
        getattr(report, "id", None)
    )

    story.append(
        Paragraph(
            "SatQuery-X Intelligence Report",
            title_style,
        )
    )

    story.append(
        Paragraph(
            (
                f"Session: {session_text}"
                " &nbsp;|&nbsp; "
                f"Report ID: {report_id_text}"
            ),
            subtitle_style,
        )
    )

    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#64748b"),
            spaceAfter=14,
        )
    )

    # ------------------------------------------------------------------
    # Query and finding
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "1. Query and Finding",
            heading_style,
        )
    )

    if query is not None:
        query_text = _escape(
            getattr(query, "text", None)
        )

        task_text = _escape(
            getattr(query, "detected_task", None)
        )

        mode_text = _escape(
            getattr(query, "detected_mode", None)
        )

        confidence_text = _escape(
            _format_confidence(
                getattr(
                    query,
                    "confidence",
                    None,
                )
            )
        )

        answer_text = _escape(
            getattr(query, "answer", None)
        )

        story.append(
            Paragraph(
                f"<b>Query:</b> {query_text}",
                body_style,
            )
        )

        story.append(Spacer(1, 6))

        task_block = (
            f"<b>Task:</b> {task_text}<br/>"
            f"<b>Mode:</b> {mode_text}<br/>"
            f"<b>Reported confidence:</b> {confidence_text}"
        )

        story.append(
            Paragraph(
                task_block,
                body_style,
            )
        )

        story.append(Spacer(1, 8))

        answer_block = (
            "<b>Answer</b><br/>"
            f"{answer_text}"
        )

        story.append(
            Paragraph(
                answer_block,
                body_style,
            )
        )

    else:
        story.append(
            Paragraph(
                "This report covers the session without a linked query.",
                body_style,
            )
        )

    # ------------------------------------------------------------------
    # Quantitative evidence
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "2. Quantitative Evidence",
            heading_style,
        )
    )

    measurements = _query_measurements(query)

    if measurements:
        measurement_data = [
            [
                Paragraph(
                    "<b>Measurement</b>",
                    small_style,
                ),
                Paragraph(
                    "<b>Reported Value</b>",
                    small_style,
                ),
            ]
        ]

        for key, value in measurements.items():
            measurement_data.append(
                [
                    Paragraph(
                        _escape(key),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            _format_value(value)
                        ),
                        small_style,
                    ),
                ]
            )

        table = Table(
            measurement_data,
            colWidths=[
                2.1 * inch,
                4.4 * inch,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#cbd5e1"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#f1f5f9"),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        story.append(table)

    else:
        story.append(
            Paragraph(
                "No quantitative measurements were reported.",
                body_style,
            )
        )

    # ------------------------------------------------------------------
    # Spatial evidence
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "3. Spatial Evidence",
            heading_style,
        )
    )

    regions = _evidence_region_rows(query)

    if regions:
        evidence_data = [
            [
                Paragraph("<b>Class</b>", small_style),
                Paragraph("<b>Confidence</b>", small_style),
                Paragraph("<b>Area</b>", small_style),
            ]
        ]

        for region in regions[:100]:
            class_text = _escape(
                region["class_name"]
            )

            confidence_text = _escape(
                _format_confidence(
                    region["confidence"]
                )
            )

            area_text = _escape(
                _format_number(
                    region["area_km2"],
                    4,
                    " km²",
                )
            )

            evidence_data.append(
                [
                    Paragraph(
                        class_text,
                        small_style,
                    ),
                    Paragraph(
                        confidence_text,
                        small_style,
                    ),
                    Paragraph(
                        area_text,
                        small_style,
                    ),
                ]
            )

        table = Table(
            evidence_data,
            colWidths=[
                2.5 * inch,
                1.5 * inch,
                2.5 * inch,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#cbd5e1"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#f1f5f9"),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        story.append(table)

    else:
        story.append(
            Paragraph(
                "No polygonal evidence regions were recorded.",
                body_style,
            )
        )

    # ------------------------------------------------------------------
    # Imagery
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "4. Imagery and Provenance",
            heading_style,
        )
    )

    assets = _asset_rows(
        session,
        query,
    )

    if assets:
        asset_data = [
            [
                Paragraph("<b>Filename</b>", small_style),
                Paragraph("<b>Sensor</b>", small_style),
                Paragraph("<b>Modality</b>", small_style),
                Paragraph("<b>CRS</b>", small_style),
                Paragraph("<b>Resolution</b>", small_style),
                Paragraph("<b>Status</b>", small_style),
            ]
        ]

        for asset in assets[:100]:
            asset_data.append(
                [
                    Paragraph(
                        _escape(
                            asset["filename"]
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            asset["sensor"]
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            asset["modality"]
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            asset["crs"]
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            _format_number(
                                asset["resolution_m"],
                                3,
                                " m",
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            asset["processing_status"]
                        ),
                        small_style,
                    ),
                ]
            )

        table = Table(
            asset_data,
            colWidths=[
                1.45 * inch,
                0.85 * inch,
                0.75 * inch,
                0.9 * inch,
                0.9 * inch,
                1.0 * inch,
            ],
            repeatRows=1,
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#cbd5e1"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#f1f5f9"),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                ]
            )
        )

        story.append(table)

    else:
        story.append(
            Paragraph(
                "No imagery assets were recorded for this analysis.",
                body_style,
            )
        )

    # ------------------------------------------------------------------
    # Execution trace
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "5. Analysis Execution Trace",
            heading_style,
        )
    )

    steps = _query_execution_steps(query)

    if steps:
        step_data = [
            [
                Paragraph("<b>Step</b>", small_style),
                Paragraph("<b>Tool</b>", small_style),
                Paragraph("<b>Agent</b>", small_style),
                Paragraph("<b>Version</b>", small_style),
                Paragraph("<b>Status</b>", small_style),
                Paragraph("<b>Latency</b>", small_style),
            ]
        ]

        for step in steps[:100]:
            step_data.append(
                [
                    Paragraph(
                        _escape(
                            getattr(
                                step,
                                "step_number",
                                None,
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            getattr(
                                step,
                                "tool_name",
                                None,
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            getattr(
                                step,
                                "agent_type",
                                None,
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            getattr(
                                step,
                                "model_version",
                                None,
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            getattr(
                                step,
                                "status",
                                None,
                            )
                        ),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            _format_number(
                                getattr(
                                    step,
                                    "latency_ms",
                                    None,
                                ),
                                0,
                                " ms",
                            )
                        ),
                        small_style,
                    ),
                ]
            )

        table = Table(
            step_data,
            colWidths=[
                0.45 * inch,
                1.35 * inch,
                1.0 * inch,
                1.15 * inch,
                0.85 * inch,
                0.8 * inch,
            ],
            repeatRows=1,
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#cbd5e1"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#f1f5f9"),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                ]
            )
        )

        story.append(table)

    else:
        story.append(
            Paragraph(
                "No execution steps were recorded.",
                body_style,
            )
        )

    # ------------------------------------------------------------------
    # Evidence contract
    # ------------------------------------------------------------------

    story.append(
        Paragraph(
            "6. Evidence Contract",
            heading_style,
        )
    )

    contract = _query_answer_contract(query)

    if contract:
        contract_data = [
            [
                Paragraph(
                    "<b>Field</b>",
                    small_style,
                ),
                Paragraph(
                    "<b>Value</b>",
                    small_style,
                ),
            ]
        ]

        for key, value in contract.items():
            contract_data.append(
                [
                    Paragraph(
                        _escape(key),
                        small_style,
                    ),
                    Paragraph(
                        _escape(
                            _format_value(value)
                        ),
                        small_style,
                    ),
                ]
            )

        table = Table(
            contract_data,
            colWidths=[
                2.1 * inch,
                4.4 * inch,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#cbd5e1"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#f1f5f9"),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        story.append(table)

    else:
        story.append(
            Paragraph(
                "No evidence contract was recorded.",
                body_style,
            )
        )

    story.append(Spacer(1, 16))

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#cbd5e1"),
        )
    )

    story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            (
                "SatQuery-X report renderer "
                f"{REPORT_RENDERER_VERSION}. "
                "Scientific quantities, spatial evidence, sensor "
                "metadata, and model results shown in this report "
                "originate from the persisted analysis evidence. "
                "Missing information is not fabricated."
            ),
            small_style,
        )
    )

    document.build(story)

    return buffer.getvalue()


# ============================================================================
# REPORT GENERATION
# ============================================================================

def _mark_report_failed(
    report: Report,
    message: str,
) -> None:
    try:
        report.mark_failed(message)
        return
    except Exception:
        logger.exception(
            "Report.mark_failed() failed for %s",
            getattr(report, "id", None),
        )

    try:
        report.status = "FAILED"
        report.error = message
        report.completed_at = timezone.now()

        report.save(
            update_fields=[
                "status",
                "error",
                "completed_at",
                "updated_at",
            ]
        )
    except Exception:
        logger.exception(
            "Unable to persist FAILED report state for %s",
            getattr(report, "id", None),
        )


def _generate_report(
    report_id: str,
) -> dict[str, Any]:
    report = (
        Report.objects
        .select_related(
            "session",
            "query",
        )
        .get(id=report_id)
    )

    query = report.query

    if query is not None:
        query_status = getattr(
            query,
            "status",
            None,
        )

        if query_status not in {
            "COMPLETED",
            "FAILED",
        }:
            message = (
                "The linked analysis has not finished yet."
            )

            logger.warning(
                "Report %s rejected because query %s is still %s",
                report.id,
                query.id,
                query_status,
            )

            _mark_report_failed(
                report,
                message,
            )

            return {
                "report_id": str(report.id),
                "status": "FAILED",
                "error": message,
            }

    report.renderer_version = (
        REPORT_RENDERER_VERSION
    )

    report.mark_generating()

    try:
        session = report.session

        source_snapshot = _build_source_snapshot(
            report,
            session,
            query,
        )

        provenance = _build_provenance(
            report,
            query,
        )

        if report.format == "HTML":
            content = _generate_html_report(
                report,
                session,
                query,
            )

            filename = (
                f"satquery_report_{report.id}.html"
            )

            content_file = ContentFile(
                content.encode("utf-8")
            )

        elif report.format == "PDF":
            content = _generate_pdf_report(
                report,
                session,
                query,
            )

            filename = (
                f"satquery_report_{report.id}.pdf"
            )

            content_file = ContentFile(
                content
            )

        else:
            raise ValueError(
                f"Unsupported report format: {report.format}"
            )

        with transaction.atomic():
            report.file.save(
                filename,
                content_file,
                save=False,
            )

            report.renderer_version = (
                REPORT_RENDERER_VERSION
            )

            report.source_snapshot = (
                source_snapshot
            )

            report.provenance = (
                provenance
            )

            report.status = "READY"
            report.error = ""
            report.completed_at = timezone.now()

            report.save(
                update_fields=[
                    "file",
                    "renderer_version",
                    "source_snapshot",
                    "provenance",
                    "status",
                    "error",
                    "completed_at",
                    "updated_at",
                ]
            )

        logger.info(
            "Report generated successfully: %s",
            report.id,
        )

        return {
            "report_id": str(report.id),
            "status": "READY",
            "format": report.format,
            "renderer_version": REPORT_RENDERER_VERSION,
        }

    except Exception:
        logger.exception(
            "Report generation failed: %s",
            report_id,
        )

        safe_message = (
            "Report generation failed. "
            "Check the analysis state and server logs."
        )

        _mark_report_failed(
            report,
            safe_message,
        )

        return {
            "report_id": str(report_id),
            "status": "FAILED",
            "error": "Report generation failed.",
        }


# ============================================================================
# CELERY ENTRY POINT
# ============================================================================

@shared_task(
    bind=True,
    autoretry_for=(),
)
def generate_report_task(
    self,
    report_id: str,
) -> dict[str, Any]:
    """
    Celery entry point for evidence-backed report generation.
    """
    return _generate_report(
        str(report_id)
    )