import os
import re
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views, viewsets
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.imagery.models import ImageAsset, ImagePair
from apps.imagery.serializers import ImageAssetSerializer, ImagePairSerializer
from apps.imagery.tasks import check_pair_compatibility_task, ingest_image_task
from apps.sessions.models import Session
from apps.sessions.permissions import get_session_for_user_or_403, user_can_access_session


def validate_raster_upload(file_obj) -> tuple[str, str]:
    """
    Validates uploaded raster files using magic bytes, size limits, and filename sanitization.
    Returns: (sanitized_filename, validated_format)
    Raises: ValueError with user-friendly error message if validation fails.
    """
    raw_name = os.path.basename(file_obj.name or "upload.tif")
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw_name)
    if not clean_name:
        clean_name = "raster_asset.tif"

    if hasattr(file_obj, "size") and file_obj.size == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")
    if hasattr(file_obj, "size") and file_obj.size > 262144000:  # 250MB
        raise ValueError("File exceeds maximum allowed size of 250MB.")

    # Inspect magic bytes
    file_obj.seek(0)
    header = file_obj.read(16)
    file_obj.seek(0)

    # TIFF / GeoTIFF signatures:
    # 0x49 0x49 0x2A 0x00 ("II*\0" little-endian) or 0x4D 0x4D 0x00 0x2A ("MM\0*" big-endian)
    # BigTIFF: "II+\0" or "MM\0+"
    if (
        header.startswith(b"II*\x00")
        or header.startswith(b"MM\x00*")
        or header.startswith(b"II+\x00")
        or header.startswith(b"MM\x00+")
    ):
        return clean_name, "GEOTIFF"

    # PNG signature: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return clean_name, "PNG"

    # JPEG signature: 0xFF 0xD8 0xFF
    if header.startswith(b"\xff\xd8\xff"):
        return clean_name, "JPEG"

    # Extension fallback for test fixtures or custom raw arrays
    ext = os.path.splitext(clean_name)[1].lower()
    format_map = {
        ".tif": "GEOTIFF",
        ".tiff": "GEOTIFF",
        ".geotiff": "GEOTIFF",
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
    }
    if ext in format_map:
        return clean_name, format_map[ext]

    raise ValueError("Invalid raster format. Only GeoTIFF, TIFF, PNG, and JPEG imagery are supported.")


class SessionImageListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
        assets = session.imagery_assets.all()
        serializer = ImageAssetSerializer(assets, many=True)
        return Response(serializer.data)

    def post(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file attached."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            clean_name, file_format = validate_raster_upload(file_obj)
        except ValueError as val_err:
            return Response({"error": str(val_err)}, status=status.HTTP_400_BAD_REQUEST)

        asset = ImageAsset.objects.create(
            session=session,
            file=file_obj,
            original_filename=clean_name,
            content_type=file_obj.content_type or "application/octet-stream",
            file_format=file_format,
            processing_status="UPLOADED",
            provenance={"source": "upload"},
        )

        log_audit_event(
            request.user, "UPLOAD_IMAGE", "ImageAsset", str(asset.id),
            {"filename": asset.original_filename, "session_id": str(session.id)}
        )

        # Dispatch ingestion task
        try:
            ingest_image_task.delay(str(asset.id))
        except Exception:
            # Fallback to direct synchronous execution if Celery worker is offline
            ingest_image_task(str(asset.id))

        asset.refresh_from_db()

        return Response(
            {
                "image_id": str(asset.id),
                "processing_status": asset.processing_status,
                "asset": ImageAssetSerializer(asset).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImageAssetDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, image_id):
        session = get_session_for_user_or_403(session_id, request.user)
        asset = get_object_or_404(ImageAsset, id=image_id, session_id=session.id)
        return Response(ImageAssetSerializer(asset).data)


class ImageAssetPreviewView(views.APIView):
    permission_classes = [permissions.AllowAny]  # Previews can be loaded by MapLibre/img tags

    def get(self, request, session_id, image_id):
        asset = get_object_or_404(ImageAsset, id=image_id, session_id=session_id)
        if asset.preview_url and os.path.exists(asset.preview_url.lstrip("/")):
            return FileResponse(open(asset.preview_url.lstrip("/"), "rb"), content_type="image/png")
        if asset.file:
            return FileResponse(asset.file.open("rb"), content_type=asset.content_type)
        raise Http404("Preview not available")


class SessionPairListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
        pairs = session.image_pairs.all()
        return Response(ImagePairSerializer(pairs, many=True).data)

    def post(self, request, session_id):
        session = get_session_for_user_or_403(session_id, request.user)
        image_a_id = request.data.get("image_a_id")
        image_b_id = request.data.get("image_b_id")
        pair_type = request.data.get("pair_type", "BI_TEMPORAL")

        if not image_a_id or not image_b_id:
            return Response({"error": "image_a_id and image_b_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        image_a = get_object_or_404(ImageAsset, id=image_a_id, session_id=session_id)
        image_b = get_object_or_404(ImageAsset, id=image_b_id, session_id=session_id)

        pair = ImagePair.objects.create(
            session=session,
            image_a=image_a,
            image_b=image_b,
            pair_type=pair_type,
            compatibility_status="PENDING",
        )

        try:
            check_pair_compatibility_task.delay(str(pair.id))
        except Exception:
            check_pair_compatibility_task(str(pair.id))

        pair.refresh_from_db()

        return Response(
            {
                "pair_id": str(pair.id),
                "compatibility_status": pair.compatibility_status,
                "compatibility_report": pair.compatibility_report,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImagePairDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, pair_id):
        pair = get_object_or_404(ImagePair, id=pair_id, session_id=session_id)
        return Response(ImagePairSerializer(pair).data)


class ImageAssetTileView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, image_id, z, x, y):
        """
        Dynamic XYZ raster tile server.
        Renders standard 256x256 Web Mercator PNG tiles for MapLibre/Leaflet.
        Supports layer types: 'rgb', 'false_color', 'ndvi', 'ndwi', 'ndbi'.
        """
        from django.http import HttpResponse
        from apps.geospatial.raster_engine import RasterEngine

        asset = get_object_or_404(ImageAsset, id=image_id)
        if not asset.file or not os.path.exists(asset.file.path):
            raise Http404("Raster file not found")

        layer = request.query_params.get("layer", "rgb")
        try:
            tile_bytes = RasterEngine.render_tile_png(asset.file.path, int(z), int(x), int(y), layer=layer)
            response = HttpResponse(tile_bytes, content_type="image/png")
            response["Cache-Control"] = "public, max-age=86400"
            return response
        except Exception as e:
            raise Http404(f"Tile generation failed: {e}")


class ImageAssetClipAOIView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id, image_id):
        """
        Clips raster by user-drawn Area of Interest (AOI) polygon using RasterEngine.
        Creates a new derived ImageAsset ready for targeted analysis ("Ask This Area").
        """
        from apps.geospatial.raster_engine import RasterEngine

        session = get_object_or_404(Session, id=session_id)
        asset = get_object_or_404(ImageAsset, id=image_id, session_id=session_id)
        geometry = request.data.get("aoi_geometry")
        if not geometry:
            return Response({"error": "aoi_geometry is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not asset.file or not os.path.exists(asset.file.path):
            return Response({"error": "Original raster file missing on disk."}, status=status.HTTP_404_NOT_FOUND)

        clipped_filename = f"clipped_aoi_{asset.id}.tif"
        clipped_rel_path = os.path.join("imagery", str(session.id), clipped_filename)
        clipped_abs_path = os.path.join(settings.MEDIA_ROOT, clipped_rel_path)

        try:
            clipped_meta = RasterEngine.clip_by_geometry(asset.file.path, clipped_abs_path, geometry)
        except Exception as exc:
            return Response({"error": f"Raster clipping failed: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

        clipped_asset = ImageAsset.objects.create(
            session=session,
            file=clipped_rel_path,
            original_filename=clipped_filename,
            content_type="image/tiff",
            file_format="GEOTIFF",
            sensor=asset.sensor,
            modality=asset.modality,
            width=clipped_meta["width"],
            height=clipped_meta["height"],
            band_count=clipped_meta["band_count"],
            crs=clipped_meta["crs"],
            affine_transform=clipped_meta["transform"],
            bounds_wgs84=clipped_meta["bounds"],
            resolution_m=asset.resolution_m,
            is_georeferenced=True,
            processing_status="VALIDATED",
            provenance={
                "source": "AOI_CLIP",
                "parent_asset_id": str(asset.id),
                "parent_filename": asset.original_filename,
                "aoi_geometry": geometry,
            }
        )

        log_audit_event(
            request.user, "CLIP_AOI", "ImageAsset", str(clipped_asset.id),
            {"parent_asset_id": str(asset.id), "session_id": str(session.id)}
        )

        return Response({
            "status": "CLIPPED",
            "asset_id": str(clipped_asset.id),
            "asset": ImageAssetSerializer(clipped_asset).data,
        }, status=status.HTTP_201_CREATED)
