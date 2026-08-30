"""Query processing, planner orchestration, trace retrieval, and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    EvidenceOutputSchema,
    ExecutionTraceResponse,
    PlanStepSchema,
    QueryRequest,
)
from backend.db.store import get_datastore
from backend.geospatial.ingestion import detect_input_mode
from backend.planner.executor import PlanExecutor
from backend.planner.planner import AgenticPlanner

router = APIRouter(prefix="/v1/sessions/{session_id}/query", tags=["Queries"])


@router.post("", response_model=ExecutionTraceResponse, status_code=status.HTTP_200_OK)
async def submit_query(
    session_id: uuid.UUID,
    payload: QueryRequest,
) -> ExecutionTraceResponse:
    store = get_datastore()
    session = store.get_session(session_id)
    if not session or not session.images:
        raise HTTPException(
            status_code=400,
            detail="Session does not exist or contains no uploaded images. Upload image(s) first.",
        )

    # Determine which images to analyze
    if payload.image_ids:
        selected_images = [img for img in session.images if img.id in payload.image_ids]
        if not selected_images:
            raise HTTPException(status_code=400, detail="None of the specified image_ids exist in this session.")
    else:
        selected_images = session.images

    image_metas = [img.metadata for img in selected_images]
    detected_mode = detect_input_mode(image_metas)

    # Step 1: Query Understanding & Agentic Planning
    planner = AgenticPlanner()
    meta_dicts = [
        {
            "image_id": str(img.id),
            "filename": img.filename,
            "sensor_type": img.metadata.sensor_type,
            "crs": img.metadata.crs,
            "affine": img.metadata.affine,
            "bounds_wgs84": img.metadata.bounds_wgs84,
            "width": img.metadata.width,
            "height": img.metadata.height,
        }
        for img in selected_images
    ]

    plan_steps, task_class = planner.create_plan(
        query=payload.text,
        detected_mode=detected_mode,
        image_count=len(selected_images),
        ingestion_metadata={"images": meta_dicts},
    )

    query_id = uuid.uuid4()
    image_bytes_list = [img.raw_bytes for img in selected_images]

    # Step 2: Plan Execution
    executor = PlanExecutor()
    trace = executor.execute(
        query=payload.text,
        plan=plan_steps,
        task_classification=task_class,
        detected_mode=detected_mode,
        image_bytes=image_bytes_list,
        image_metadata=meta_dicts,
        session_id=session_id,
        query_id=query_id,
    )

    trace_dict = trace.model_dump()
    stored_query = store.add_query(
        session_id=session_id,
        text=payload.text,
        image_ids=[img.id for img in selected_images],
        status="completed",
        detected_mode=detected_mode,
        task_classification=task_class,
        trace_dict=trace_dict,
        query_id=query_id,
    )

    return ExecutionTraceResponse(
        query_id=stored_query.id,
        session_id=session_id,
        query=trace.query,
        detected_mode=trace.detected_mode,
        task_classification=trace.task_classification,
        status=stored_query.status,
        plan=[
            PlanStepSchema(step=s.step, tool=s.tool, version=s.version, params=s.params)
            for s in trace.plan
        ],
        outputs=trace.outputs,
        answer=trace.answer,
        confidence=trace.confidence,
        evidence=EvidenceOutputSchema(
            change_mask_url=trace.evidence.change_mask_url,
            overlay_url=trace.evidence.overlay_url,
            bboxes=trace.evidence.bboxes,
            geojson=trace.evidence.geojson,
            quantified_area_km2=trace.evidence.quantified_area_km2,
            quantified_area_hectares=trace.evidence.quantified_area_hectares,
            change_percentage=trace.evidence.change_percentage,
        ),
        timings_ms=trace.timings_ms,
        errors=trace.errors,
        created_at=stored_query.created_at,
        completed_at=stored_query.completed_at,
    )


@router.get("/{query_id}", response_model=ExecutionTraceResponse)
async def get_query_trace(session_id: uuid.UUID, query_id: uuid.UUID) -> ExecutionTraceResponse:
    store = get_datastore()
    query = store.get_query(query_id)
    if not query or query.session_id != session_id:
        raise HTTPException(status_code=404, detail="Query record not found in this session.")

    td = query.trace_dict
    ev = td.get("evidence", {})

    return ExecutionTraceResponse(
        query_id=query.id,
        session_id=session_id,
        query=query.text,
        detected_mode=query.detected_mode,
        task_classification=query.task_classification,
        status=query.status,
        plan=[PlanStepSchema(**s) for s in td.get("plan", [])],
        outputs=td.get("outputs", {}),
        answer=td.get("answer", "No answer"),
        confidence=td.get("confidence", 0.0),
        evidence=EvidenceOutputSchema(
            change_mask_url=ev.get("change_mask_url"),
            overlay_url=ev.get("overlay_url"),
            bboxes=ev.get("bboxes", []),
            geojson=ev.get("geojson", []),
            quantified_area_km2=ev.get("quantified_area_km2"),
            quantified_area_hectares=ev.get("quantified_area_hectares"),
            change_percentage=ev.get("change_percentage"),
        ),
        timings_ms=td.get("timings_ms", {}),
        errors=td.get("errors", []),
        created_at=query.created_at,
        completed_at=query.completed_at,
    )


@router.get("/{query_id}/stream")
async def stream_query_trace(session_id: uuid.UUID, query_id: uuid.UUID) -> StreamingResponse:
    store = get_datastore()
    query = store.get_query(query_id)
    if not query or query.session_id != session_id:
        raise HTTPException(status_code=404, detail="Query record not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        # Stream planned step updates then final result
        td = query.trace_dict
        plan = td.get("plan", [])

        yield f"data: {json.dumps({'event': 'planning', 'plan': plan, 'mode': query.detected_mode})}\n\n"
        await asyncio.sleep(0.1)

        for step in plan:
            yield f"data: {json.dumps({'event': 'executing_step', 'step': step.get('step'), 'tool': step.get('tool')})}\n\n"
            await asyncio.sleep(0.1)

        yield f"data: {json.dumps({'event': 'completed', 'answer': td.get('answer'), 'confidence': td.get('confidence'), 'evidence': td.get('evidence')})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
