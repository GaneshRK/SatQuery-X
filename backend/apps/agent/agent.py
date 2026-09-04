"""Top-level Agent orchestrator invoked strictly in understand->validate->plan->execute order per §8."""

from __future__ import annotations

import json
from typing import Any

from django.utils import timezone
import redis

from apps.agent.executor import execute_plan, publish_query_event
from apps.agent.planner import create_execution_plan
from apps.agent.understander import understand_query
from apps.agent.validator import validate_agent_inputs
from apps.queries.models import Query


class Agent:
    @classmethod
    def run(cls, query: Query, session_context: dict[str, Any] | None = None) -> dict[str, Any]:
        from django.conf import settings

        redis_client = None
        try:
            redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url, socket_connect_timeout=0.1, socket_timeout=0.1)
        except Exception:
            pass

        query.status = "RUNNING"
        query.save()

        publish_query_event(redis_client, str(query.id), {
            "event": "QUERY_STARTED",
            "query_id": str(query.id),
            "text": query.text,
        })

        # 1. UNDERSTAND
        intent = understand_query(query.text, session_context)
        query.detected_task = intent.intent.upper()
        if intent.temporal:
            query.detected_mode = "BI_TEMPORAL"
        elif intent.cross_modal:
            query.detected_mode = "CROSS_MODAL"
        else:
            query.detected_mode = "SINGLE_IMAGE"

        # Resolve inputs
        image_assets = []
        if query.image:
            image_assets.append(query.image)
        elif query.session:
            image_assets = list(query.session.imagery_assets.filter(processing_status="VALIDATED"))

        image_pair = query.image_pair
        if not image_pair and len(image_assets) >= 2 and (intent.temporal or intent.cross_modal):
            # Locate active pair if exists
            pair_type = "CROSS_MODAL" if intent.cross_modal else "BI_TEMPORAL"
            image_pair = query.session.image_pairs.filter(pair_type=pair_type).first()

        # 2. VALIDATE
        validation = validate_agent_inputs(intent, image_assets, image_pair)
        if not validation["valid"]:
            error_msg = "; ".join(validation["reasons"])
            query.status = "FAILED"
            query.error = error_msg
            query.completed_at = timezone.now()
            query.save()

            publish_query_event(redis_client, str(query.id), {
                "event": "QUERY_FAILED",
                "query_id": str(query.id),
                "error": error_msg,
            })
            return {"status": "FAILED", "error": error_msg}

        # 3. PLAN
        plan = create_execution_plan(intent, validation["mode"])
        query.plan = plan
        query.save()

        publish_query_event(redis_client, str(query.id), {
            "event": "PLAN_CREATED",
            "query_id": str(query.id),
            "plan": plan,
        })

        # 4. EXECUTE
        result = execute_plan(query, plan, image_assets, image_pair)

        query.answer = result.get("answer")
        query.confidence = result.get("confidence")
        query.status = "COMPLETED"
        query.completed_at = timezone.now()
        query.save()

        publish_query_event(redis_client, str(query.id), {
            "event": "QUERY_COMPLETED",
            "query_id": str(query.id),
            "answer": query.answer,
            "confidence": query.confidence,
        })

        return result
