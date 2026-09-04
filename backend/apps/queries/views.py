import json
import time
from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
import redis
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.imagery.models import ImageAsset, ImagePair
from apps.queries.models import ExecutionStep, Query
from apps.queries.serializers import QueryDetailSerializer
from apps.queries.tasks import run_query_task
from apps.sessions.models import Session


class SessionQueryListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        queries = session.queries.all()
        return Response(QueryDetailSerializer(queries, many=True).data)

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        text = request.data.get("text", "").strip()
        if not text:
            return Response({"error": "Query text cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        image_id = request.data.get("image_id")
        pair_id = request.data.get("pair_id")

        image = None
        pair = None
        if image_id:
            image = get_object_or_404(ImageAsset, id=image_id, session_id=session_id)
        if pair_id:
            pair = get_object_or_404(ImagePair, id=pair_id, session_id=session_id)

        # Fallback to active session image if not explicitly passed
        if not image and not pair:
            image = session.imagery_assets.filter(processing_status="VALIDATED").first()

        query = Query.objects.create(
            session=session,
            user=request.user,
            text=text,
            image=image,
            image_pair=pair,
            status="PENDING",
        )

        log_audit_event(
            request.user, "SUBMIT_QUERY", "Query", str(query.id),
            {"query_text": text, "session_id": str(session.id)}
        )

        # Dispatch async agent task
        try:
            run_query_task.delay(str(query.id))
        except Exception:
            # Fallback synchronous run if Celery offline
            run_query_task(str(query.id))

        query.refresh_from_db()

        return Response(
            {
                "query_id": str(query.id),
                "status": query.status,
                "detected_task": query.detected_task,
                "detected_mode": query.detected_mode,
                "plan": query.plan,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class QueryDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, query_id):
        query = get_object_or_404(Query, id=query_id, session_id=session_id)
        return Response(QueryDetailSerializer(query).data)


class QueryStreamView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, session_id, query_id):
        query = get_object_or_404(Query, id=query_id, session_id=session_id)

        def event_generator():
            # If already completed or failed, send final state immediately
            if query.status in ("COMPLETED", "FAILED"):
                yield f"data: {json.dumps({'event': f'QUERY_{query.status}', 'query_id': str(query.id), 'answer': query.answer, 'confidence': query.confidence})}\n\n"
                return

            redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            pubsub = None
            try:
                r = redis.from_url(redis_url)
                pubsub = r.pubsub()
                channel = f"query:{query_id}:events"
                pubsub.subscribe(channel)
            except Exception:
                pass

            if pubsub:
                timeout_counter = 0
                while timeout_counter < 120:  # Max 2 minutes
                    message = pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        data_str = message["data"].decode("utf-8") if isinstance(message["data"], bytes) else message["data"]
                        yield f"data: {data_str}\n\n"
                        payload = json.loads(data_str)
                        if payload.get("event") in ("QUERY_COMPLETED", "QUERY_FAILED"):
                            break
                    timeout_counter += 1
            else:
                # Polling fallback if Redis pubsub is unavailable
                for _ in range(30):
                    time.sleep(1)
                    query.refresh_from_db()
                    for step in query.execution_steps.all():
                        yield f"data: {json.dumps({'event': 'STEP_COMPLETED', 'step_number': step.step_number, 'tool': step.tool_name, 'status': step.status, 'latency_ms': step.latency_ms})}\n\n"
                    if query.status in ("COMPLETED", "FAILED"):
                        yield f"data: {json.dumps({'event': f'QUERY_{query.status}', 'query_id': str(query.id), 'answer': query.answer, 'confidence': query.confidence})}\n\n"
                        break

        response = StreamingHttpResponse(event_generator(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
