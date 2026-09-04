import os
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views, viewsets
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.imagery.models import ImageAsset, ImagePair
from apps.imagery.serializers import ImageAssetSerializer, ImagePairSerializer
from apps.imagery.tasks import check_pair_compatibility_task, ingest_image_task
from apps.sessions.models import Session


class SessionImageListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        assets = session.imagery_assets.all()
        serializer = ImageAssetSerializer(assets, many=True)
        return Response(serializer.data)

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file attached."}, status=status.HTTP_400_BAD_REQUEST)

        # Detect format
        ext = os.path.splitext(file_obj.name)[1].lower()
        format_map = {
            ".tif": "GEOTIFF",
            ".tiff": "GEOTIFF",
            ".geotiff": "GEOTIFF",
            ".png": "PNG",
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
        }
        file_format = format_map.get(ext, "GEOTIFF")

        asset = ImageAsset.objects.create(
            session=session,
            file=file_obj,
            original_filename=file_obj.name,
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
        asset = get_object_or_404(ImageAsset, id=image_id, session_id=session_id)
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
        session = get_object_or_404(Session, id=session_id)
        pairs = session.image_pairs.all()
        return Response(ImagePairSerializer(pairs, many=True).data)

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id)
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
