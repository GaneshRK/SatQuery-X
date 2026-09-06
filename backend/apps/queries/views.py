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
from apps.sessions.permissions import get_session_for_user_or_403


class SessionQueryListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
        queries = session.queries.all()
        return Response(QueryDetailSerializer(queries, many=True).data)

    def post(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
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

        # Fallback to active session image pair or image if not explicitly passed
        if not image and not pair:
            pair = session.image_pairs.first()
            if not pair:
                image = session.imagery_assets.filter(processing_status="VALIDATED").first()

        # Ingest visual context & AOI geometry if passed from client
        visual_ctx = request.data.get("visual_context")
        aoi_geom = request.data.get("aoi_geometry")
        if (visual_ctx and isinstance(visual_ctx, dict)) or aoi_geom:
            current_ctx = dict(session.conversation_context or {})
            if visual_ctx and isinstance(visual_ctx, dict):
                current_ctx["current_visual_state"] = visual_ctx
                if visual_ctx.get("active_region"):
                    current_ctx["active_region"] = visual_ctx["active_region"]
                if visual_ctx.get("current_viewport"):
                    current_ctx["current_viewport"] = visual_ctx["current_viewport"]
            if aoi_geom:
                current_ctx["aoi_geometry"] = aoi_geom
            session.conversation_context = current_ctx
            session.save(update_fields=["conversation_context"])

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
        session = get_session_for_user_or_403(session_id, request.user)
        query = get_object_or_404(Query, id=query_id, session_id=session.id)
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


class QueryExportView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, query_id, export_format):
        """
        Exports query findings, evidence regions, or raster data in requested format:
        'geojson', 'csv', 'json', 'png', 'geotiff'.
        """
        import csv
        import io
        from django.http import HttpResponse, FileResponse

        query = get_object_or_404(Query, id=query_id, session_id=session_id)
        fmt = export_format.lower().strip()

        # 1. GeoJSON Export
        if fmt == "geojson":
            features = []
            for r in query.evidence_regions.all():
                features.append({
                    "type": "Feature",
                    "id": str(r.id),
                    "geometry": r.geojson_geometry,
                    "properties": {
                        "class_name": r.class_name,
                        "confidence": r.confidence,
                        "area_m2": r.area_m2,
                        "area_km2": r.area_km2,
                        "area_ha": r.area_ha,
                    }
                })
            geojson_data = {
                "type": "FeatureCollection",
                "query_id": str(query.id),
                "query_text": query.text,
                "answer": query.answer,
                "confidence": query.confidence,
                "features": features,
            }
            resp = HttpResponse(json.dumps(geojson_data, indent=2), content_type="application/geo+json")
            resp["Content-Disposition"] = f'attachment; filename="satquery_evidence_{query.id}.geojson"'
            return resp

        # 2. CSV Export
        elif fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["region_id", "class_name", "confidence", "area_m2", "area_km2", "area_ha", "centroid_or_bbox"])
            for r in query.evidence_regions.all():
                geom = r.geojson_geometry or {}
                coords = str(geom.get("coordinates", []))[:60]
                writer.writerow([str(r.id), r.class_name, r.confidence, r.area_m2, r.area_km2, r.area_ha, coords])
            resp = HttpResponse(buf.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="satquery_measurements_{query.id}.csv"'
            return resp

        # 3. JSON Export (Full 10-Key Answer Contract)
        elif fmt == "json":
            contract = QueryDetailSerializer(query).data.get("answer_contract", {})
            resp = HttpResponse(json.dumps(contract, indent=2), content_type="application/json")
            resp["Content-Disposition"] = f'attachment; filename="satquery_answer_{query.id}.json"'
            return resp

        # 4. GeoTIFF / Raster Export
        elif fmt in ("geotiff", "tif", "tiff"):
            img = query.image or (query.image_pair.image_a if query.image_pair else None)
            if img and img.file and os.path.exists(img.file.path):
                return FileResponse(open(img.file.path, "rb"), content_type="image/tiff", as_attachment=True, filename=f"satquery_raster_{query.id}.tif")
            return Response({"error": "No GeoTIFF available for this query."}, status=status.HTTP_404_NOT_FOUND)

        # 5. PNG Preview Export
        elif fmt == "png":
            img = query.image or (query.image_pair.image_a if query.image_pair else None)
            if img and img.preview_url and os.path.exists(img.preview_url.lstrip("/")):
                return FileResponse(open(img.preview_url.lstrip("/"), "rb"), content_type="image/png", as_attachment=True, filename=f"satquery_preview_{query.id}.png")
            return Response({"error": "No PNG preview available for this query."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"error": f"Unsupported export format '{format}'. Supported: geojson, csv, json, geotiff, png."}, status=status.HTTP_400_BAD_REQUEST)


class SessionContextView(views.APIView):
    """GET /api/v1/sessions/{session_id}/context/ - returns current multi-turn conversation context."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        from apps.agent.conversation_engine import ConversationEngine
        ctx = session.conversation_context or ConversationEngine.get_default_context()
        return Response({
            "session_id": str(session.id),
            "conversation_context": ctx,
        })


class SessionContextResetView(views.APIView):
    """POST /api/v1/sessions/{session_id}/context/reset/ - resets conversation context to fresh default."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        from apps.agent.conversation_engine import ConversationEngine
        session.conversation_context = ConversationEngine.get_default_context()
        session.save(update_fields=["conversation_context"])
        log_audit_event(
            request.user, "RESET_CONTEXT", "Session", str(session.id),
            {"message": "Conversation context reset to default."}
        )
        return Response({
            "session_id": str(session.id),
            "status": "reset",
            "conversation_context": session.conversation_context,
        })

