"""Celery background tasks for long-running specialist model inference and report generation."""

from __future__ import annotations

import uuid
from typing import Any

from backend.db.store import get_datastore
from backend.jobs.celery_app import celery_app
from backend.planner.executor import PlanExecutor
from backend.planner.planner import AgenticPlanner
from backend.planner.schemas import PlanStep


if celery_app:

    @celery_app.task(name="tasks.execute_query_job", bind=True)
    def execute_query_job(
        self,
        session_id_str: str,
        query_id_str: str,
        query_text: str,
        plan_dicts: list[dict[str, Any]],
        task_classification: str,
        detected_mode: str,
        image_metadata: list[dict[str, Any]],
    ) -> dict[str, Any]:
        store = get_datastore()
        session_id = uuid.UUID(session_id_str)
        query_id = uuid.UUID(query_id_str)

        session = store.get_session(session_id)
        if not session:
            return {"error": "Session not found"}

        image_bytes = [img.raw_bytes for img in session.images]
        plan_steps = [PlanStep(**p) for p in plan_dicts]

        executor = PlanExecutor()
        trace = executor.execute(
            query=query_text,
            plan=plan_steps,
            task_classification=task_classification,
            detected_mode=detected_mode,
            image_bytes=image_bytes,
            image_metadata=image_metadata,
            session_id=session_id,
            query_id=query_id,
        )

        trace_dict = trace.model_dump()
        store.update_query(query_id, status="completed", trace_dict=trace_dict)
        return trace_dict
else:
    # Dummy fallback when celery is not installed
    def execute_query_job(*args, **kwargs):
        pass
