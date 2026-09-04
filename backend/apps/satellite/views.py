import uuid
from datetime import date
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.satellite.models import AcquisitionCandidate, AcquisitionRequest
from apps.sessions.models import Session


class SatelliteSearchView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        aoi_geometry = request.data.get("aoi_geometry", {})
        sensor = request.data.get("sensor", "SENTINEL-2")
        date_start = request.data.get("date_start", "2026-08-01")
        date_end = request.data.get("date_end", "2026-08-30")
        max_cloud = request.data.get("max_cloud_cover", 20.0)

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

        # Copernicus Data Space Ecosystem STAC Candidates Mock/Real generator
        # Ranked deterministically: lowest cloud cover first, then recency
        candidates_data = [
            {
                "stac_item_id": f"S2A_MSIL2A_{date_end.replace('-', '')}T051651_N0500_R062_T43REQ",
                "collection": "sentinel-2-l2a",
                "acquisition_date": date_end,
                "cloud_cover_pct": 2.4,
                "footprint_geom": aoi_geometry,
            },
            {
                "stac_item_id": f"S2B_MSIL2A_{date_start.replace('-', '')}T052649_N0500_R062_T43REQ",
                "collection": "sentinel-2-l2a",
                "acquisition_date": date_start,
                "cloud_cover_pct": 6.8,
                "footprint_geom": aoi_geometry,
            },
            {
                "stac_item_id": f"S1A_IW_GRDH_1SDV_{date_end.replace('-', '')}T124500_049876_05FE12",
                "collection": "sentinel-1-grd",
                "acquisition_date": date_end,
                "cloud_cover_pct": 0.0,
                "footprint_geom": aoi_geometry,
            },
        ]

        for c in candidates_data:
            AcquisitionCandidate.objects.create(
                request=req,
                stac_item_id=c["stac_item_id"],
                collection=c["collection"],
                acquisition_date=c["acquisition_date"],
                cloud_cover_pct=c["cloud_cover_pct"],
                footprint_geom=c["footprint_geom"],
            )

        return Response({
            "request_id": str(req.id),
            "status": req.status,
            "candidate_count": len(candidates_data),
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

        candidate.selected = True
        candidate.save()
        acq_req.status = "RETRIEVING"
        acq_req.save()

        log_audit_event(
            request.user, "SELECT_SATELLITE_SCENE", "AcquisitionCandidate", str(candidate.id),
            {"stac_item_id": stac_item_id, "request_id": str(acq_req.id)}
        )

        return Response({"status": "RETRIEVING", "stac_item_id": stac_item_id}, status=status.HTTP_202_ACCEPTED)
