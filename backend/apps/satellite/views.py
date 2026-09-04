import uuid
from datetime import date
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.satellite.models import AcquisitionCandidate, AcquisitionRequest
from apps.satellite.providers import get_satellite_provider
from apps.sessions.models import Session
from apps.imagery.models import ImageAsset


class SatelliteSearchView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        aoi_geometry = request.data.get("aoi_geometry", {})
        sensor = request.data.get("sensor", "SENTINEL-2")
        date_start = request.data.get("date_start", "2026-08-01")
        date_end = request.data.get("date_end", "2026-08-30")
        max_cloud = float(request.data.get("max_cloud_cover", 20.0))

        session = get_object_or_404(Session, id=session_id) if session_id else Session.objects.filter(user=request.user).first()
        if not session:
            session = Session.objects.create(user=request.user, name="Satellite Search Session")

        req = AcquisitionRequest.objects.create(
            session=session,
            aoi_geometry=aoi_geometry,
            sensor=sensor,
            date_start=date_start,
            date_end=date_end,
            max_cloud_cover=max_cloud,
            status="RESULTS_READY",
        )

        provider = get_satellite_provider()
        candidates_dto = provider.search_scenes(
            aoi_geometry=aoi_geometry,
            date_start=date_start,
            date_end=date_end,
            sensor=sensor,
            max_cloud_cover=max_cloud,
        )

        for c in candidates_dto:
            AcquisitionCandidate.objects.create(
                request=req,
                stac_item_id=c.stac_item_id,
                collection=c.collection,
                acquisition_date=c.acquisition_date,
                cloud_cover_pct=c.cloud_cover_pct,
                footprint_geom=c.footprint_geom,
            )

        log_audit_event(
            request.user, "SATELLITE_SEARCH", "AcquisitionRequest", str(req.id),
            {"sensor": sensor, "date_start": date_start, "date_end": date_end, "candidates": len(candidates_dto)}
        )

        return Response({
            "request_id": str(req.id),
            "status": req.status,
            "provider": provider.name,
            "candidate_count": len(candidates_dto),
        }, status=status.HTTP_201_CREATED)


class CandidateListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, request_id):
        acq_req = get_object_or_404(AcquisitionRequest, id=request_id)
        candidates = acq_req.candidates.all().order_by("cloud_cover_pct", "-acquisition_date")
        data = [
            {
                "id": str(c.id),
                "stac_item_id": c.stac_item_id,
                "collection": c.collection,
                "acquisition_date": c.acquisition_date,
                "cloud_cover_pct": c.cloud_cover_pct,
                "footprint_geom": c.footprint_geom,
                "selected": c.selected,
            }
            for c in candidates
        ]
        return Response(data)


class CandidateSelectView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, request_id):
        acq_req = get_object_or_404(AcquisitionRequest, id=request_id)
        stac_item_id = request.data.get("stac_item_id")
        candidate = get_object_or_404(AcquisitionCandidate, request=acq_req, stac_item_id=stac_item_id)

        from apps.satellite.tasks import ingest_satellite_candidate_task

        # Attempt async Celery task execution with immediate sync fallback
        task_dispatched = False
        try:
            task = ingest_satellite_candidate_task.delay(str(candidate.id), str(request.user.id))
            task_id = task.id
            task_dispatched = True
        except Exception:
            # Synchronous fallback if Celery/Redis is not running
            res = ingest_satellite_candidate_task(str(candidate.id), str(request.user.id))
            task_id = "sync_completed"

        # Refresh candidate to check if already completed
        candidate.refresh_from_db()
        asset = candidate.retrieved_image

        return Response({
            "status": "PROCESSING" if task_dispatched and not asset else "DONE",
            "task_id": task_id,
            "stac_item_id": stac_item_id,
            "candidate_id": str(candidate.id),
            "asset_id": str(asset.id) if asset else None,
            "asset_name": asset.original_filename if asset else None,
        }, status=status.HTTP_202_ACCEPTED)
