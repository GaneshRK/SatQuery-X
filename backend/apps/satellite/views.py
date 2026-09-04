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

        candidate.selected = True
        candidate.save()
        acq_req.status = "INGESTED"
        acq_req.save()

        # Check if asset already exists or create simulated asset for the scene
        sensor_type = "SENTINEL-2" if "S2" in stac_item_id else "SENTINEL-1"
        modality_type = "MULTISPECTRAL" if sensor_type == "SENTINEL-2" else "SAR"

        created_asset, _ = ImageAsset.objects.get_or_create(
            session=acq_req.session,
            original_filename=f"{stac_item_id}.tif",
            defaults={
                "sensor": sensor_type,
                "modality": modality_type,
                "file_format": "GEOTIFF",
                "width": 512,
                "height": 512,
                "band_count": 4 if sensor_type == "SENTINEL-2" else 2,
                "crs": "EPSG:4326",
                "affine_transform": [0.00048828125, 0.0, 93.00, 0.0, -0.00048828125, 26.75],
                "bounds_wgs84": {"west": 93.00, "south": 26.50, "east": 93.25, "north": 26.75},
                "resolution_m": 10.0,
                "is_georeferenced": True,
                "processing_status": "VALIDATED",
                "preview_url": f"/media/previews/preview_pre_{acq_req.session.id}.png",
                "provenance": {
                    "source": "Copernicus Data Space Ecosystem",
                    "stac_item_id": stac_item_id,
                    "collection": candidate.collection,
                    "cloud_cover": candidate.cloud_cover_pct,
                },
            }
        )

        log_audit_event(
            request.user, "SELECT_SATELLITE_SCENE", "AcquisitionCandidate", str(candidate.id),
            {"stac_item_id": stac_item_id, "request_id": str(acq_req.id), "asset_id": str(created_asset.id)}
        )

        return Response({
            "status": "INGESTED",
            "stac_item_id": stac_item_id,
            "asset_id": str(created_asset.id),
            "asset_name": created_asset.original_filename,
        }, status=status.HTTP_202_ACCEPTED)
