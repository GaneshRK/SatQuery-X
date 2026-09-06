from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.audit.models import log_audit_event
from apps.imagery.models import ImageAsset, ImagePair
from apps.imagery.serializers import (
    ImageAssetSerializer,
    ImagePairSerializer,
)
from apps.imagery.tasks import (
    check_pair_compatibility_task,
    ingest_image_task,
)
from apps.sessions.models import Session
from apps.sessions.permissions import get_session_for_user_or_403


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE = 250 * 1024 * 1024  # 250 MiB

ALLOWED_FORMATS = {
    "GEOTIFF",
    "TIFF",
    "PNG",
    "JPEG",
}

ALLOWED_PAIR_TYPES = {
    "BI_TEMPORAL",
    "CROSS_MODAL",
}

ALLOWED_TILE_LAYERS = {
    "rgb",
    "false_color",
    "ndvi",
    "ndwi",
    "ndbi",
}


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

def _sanitize_filename(filename: str | None) -> str:
    """
    Return a filesystem-safe display filename.

    The sanitized filename is only metadata. Actual storage is handled by
    ImageAsset.image_upload_path().
    """

    raw_name = os.path.basename(
        filename or "imagery_asset"
    )

    clean_name = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "_",
        raw_name,
    )

    clean_name = clean_name.strip(".")

    if not clean_name:
        clean_name = "imagery_asset"

    return clean_name[:255]


def _detect_file_format(
    header: bytes,
    filename: str,
) -> str:
    """
    Detect supported image format from actual file signatures.

    Extension is used only as a compatibility fallback for formats where
    the signature is not sufficient for our upload endpoint.
    """

    # TIFF / classic TIFF
    if (
        header.startswith(b"II*\x00")
        or header.startswith(b"MM\x00*")
    ):
        return "GEOTIFF"

    # BigTIFF
    if (
        header.startswith(b"II+\x00")
        or header.startswith(b"MM\x00+")
    ):
        return "GEOTIFF"

    # PNG
    if header.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return "PNG"

    # JPEG
    if header.startswith(
        b"\xff\xd8\xff"
    ):
        return "JPEG"

    # Some test fixtures / unusual storage paths may have incomplete
    # headers. Permit only known extensions as a fallback.
    extension = Path(filename).suffix.lower()

    extension_map = {
        ".tif": "GEOTIFF",
        ".tiff": "GEOTIFF",
        ".geotiff": "GEOTIFF",
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
    }

    detected = extension_map.get(extension)

    if detected:
        return detected

    raise ValueError(
        "Unsupported imagery format. "
        "Supported formats are GeoTIFF/TIFF, PNG, and JPEG."
    )


def validate_raster_upload(
    file_obj,
) -> tuple[str, str]:
    """
    Validate an uploaded imagery file.

    Returns:
        (sanitized_filename, detected_format)

    Raises:
        ValueError
    """

    if file_obj is None:
        raise ValueError(
            "No imagery file was supplied."
        )

    filename = _sanitize_filename(
        getattr(file_obj, "name", None)
    )

    size = getattr(
        file_obj,
        "size",
        None,
    )

    if size is not None:
        if size <= 0:
            raise ValueError(
                "Uploaded file is empty."
            )

        if size > MAX_UPLOAD_SIZE:
            raise ValueError(
                "File exceeds the maximum upload size of 250 MiB."
            )

    try:
        file_obj.seek(0)
        header = file_obj.read(32)
        file_obj.seek(0)
    except Exception as exc:
        raise ValueError(
            f"Unable to read uploaded file: {exc}"
        ) from exc

    if not header:
        raise ValueError(
            "Uploaded file contains no readable data."
        )

    file_format = _detect_file_format(
        header,
        filename,
    )

    if file_format not in ALLOWED_FORMATS:
        raise ValueError(
            "Unsupported imagery format."
        )

    return filename, file_format


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

class SessionAccessMixin:
    """
    Common helper for session-scoped imagery endpoints.
    """

    def get_session(
        self,
        request,
        session_id,
    ):
        return get_session_for_user_or_403(
            session_id,
            request.user,
        )


# ---------------------------------------------------------------------------
# Session imagery
# ---------------------------------------------------------------------------

class SessionImageListCreateView(
    SessionAccessMixin,
    views.APIView,
):
    """
    GET:
        List imagery belonging to the authenticated user's session.

    POST:
        Upload a new imagery asset.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        session_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        assets = (
            ImageAsset.objects
            .filter(session=session)
            .order_by("-created_at")
        )

        serializer = ImageAssetSerializer(
            assets,
            many=True,
        )

        return Response(
            serializer.data
        )

    def post(
        self,
        request,
        session_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        file_obj = request.FILES.get(
            "file"
        )

        if file_obj is None:
            return Response(
                {
                    "error":
                    "No imagery file was attached."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            clean_name, file_format = (
                validate_raster_upload(
                    file_obj
                )
            )
        except ValueError as exc:
            return Response(
                {
                    "error": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset = ImageAsset.objects.create(
            session=session,
            file=file_obj,
            original_filename=clean_name,
            content_type=(
                getattr(
                    file_obj,
                    "content_type",
                    None,
                )
                or "application/octet-stream"
            ),
            file_format=file_format,
            processing_status="UPLOADED",
            provenance={
                "source": "user_upload",
                "upload": {
                    "original_filename": clean_name,
                    "declared_content_type": (
                        getattr(
                            file_obj,
                            "content_type",
                            None,
                        )
                    ),
                },
            },
        )

        log_audit_event(
            request.user,
            "UPLOAD_IMAGE",
            "ImageAsset",
            str(asset.id),
            {
                "filename": asset.original_filename,
                "session_id": str(session.id),
            },
        )

        # ---------------------------------------------------------------
        # Queue ingestion.
        #
        # Do not silently execute a Celery task synchronously merely because
        # the worker is unavailable. That makes production behavior
        # unpredictable and can cause long HTTP requests/timeouts.
        # ---------------------------------------------------------------

        try:
            task_result = ingest_image_task.delay(
                str(asset.id)
            )

            task_id = getattr(
                task_result,
                "id",
                None,
            )

        except Exception as exc:
            asset.processing_status = "FAILED"
            asset.validation_report = {
                "errors": [
                    "Imagery ingestion could not be queued.",
                    str(exc),
                ]
            }
            asset.save(
                update_fields=[
                    "processing_status",
                    "validation_report",
                ]
            )

            return Response(
                {
                    "error":
                    "Imagery was uploaded, but ingestion could not be queued.",
                    "image_id":
                    str(asset.id),
                    "processing_status":
                    asset.processing_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = ImageAssetSerializer(
            asset
        )

        return Response(
            {
                "image_id":
                str(asset.id),
                "processing_status":
                asset.processing_status,
                "task_id":
                task_id,
                "asset":
                serializer.data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# Individual imagery asset
# ---------------------------------------------------------------------------

class ImageAssetDetailView(
    SessionAccessMixin,
    views.APIView,
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        session_id,
        image_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
            session_id=session.id,
        )

        return Response(
            ImageAssetSerializer(
                asset
            ).data
        )


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

class ImageAssetPreviewView(
    SessionAccessMixin,
    views.APIView,
):
    """
    Authenticated preview endpoint.

    Private imagery must not be exposed with AllowAny.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        session_id,
        image_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
            session_id=session.id,
        )

        try:
            from apps.imagery.services.artifacts import (
                register_imagery_artifacts,
            )

            dto = register_imagery_artifacts(
                asset
            )

        except Exception as exc:
            raise Http404(
                f"Preview generation failed: {exc}"
            )

        preview_path = getattr(
            dto,
            "preview_path",
            None,
        )

        if (
            preview_path
            and os.path.isfile(preview_path)
        ):
            return FileResponse(
                open(
                    preview_path,
                    "rb",
                ),
                content_type=(
                    "image/webp"
                    if str(
                        preview_path
                    ).lower().endswith(
                        ".webp"
                    )
                    else "image/png"
                ),
            )

        thumbnail_path = getattr(
            dto,
            "thumbnail_path",
            None,
        )

        if (
            thumbnail_path
            and os.path.isfile(
                thumbnail_path
            )
        ):
            return FileResponse(
                open(
                    thumbnail_path,
                    "rb",
                ),
                content_type="image/webp",
            )

        raise Http404(
            "Preview is not available for this imagery."
        )


# ---------------------------------------------------------------------------
# Dedicated imagery API
# ---------------------------------------------------------------------------

class DedicatedImageryDetailView(
    views.APIView,
):
    """
    GET /api/imagery/<uuid:image_id>/

    This endpoint requires authentication because imagery belongs to users'
    sessions.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        image_id,
    ):
        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
        )

        # Explicit ownership check.
        get_session_for_user_or_403(
            asset.session_id,
            request.user,
        )

        try:
            from apps.imagery.services.artifacts import (
                make_absolute_url,
                register_imagery_artifacts,
            )

            dto = register_imagery_artifacts(
                asset
            )

        except Exception as exc:
            return Response(
                {
                    "error":
                    f"Unable to prepare imagery artifacts: {exc}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        artifacts = []

        for artifact in asset.artifacts.all():
            file_url = None

            if artifact.file:
                try:
                    file_url = make_absolute_url(
                        artifact.file.url,
                        request,
                    )
                except Exception:
                    file_url = None

            artifacts.append(
                {
                    "id":
                    str(artifact.id),
                    "type":
                    artifact.artifact_type,
                    "url":
                    file_url,
                    "mime_type":
                    artifact.mime_type,
                    "width":
                    artifact.width,
                    "height":
                    artifact.height,
                    "bounds":
                    artifact.bounds,
                    "provenance":
                    artifact.provenance,
                }
            )

        data = {
            "id":
            str(asset.id),

            "session_id":
            str(asset.session_id),

            "original_filename":
            asset.original_filename,

            "sensor":
            asset.sensor,

            "modality":
            asset.modality,

            "file_format":
            asset.file_format,

            "content_type":
            asset.content_type,

            "acquisition_date":
            (
                asset.acquisition_date.isoformat()
                if asset.acquisition_date
                else None
            ),

            # IMPORTANT:
            # Do not convert missing values into 0.0 or another fabricated
            # scientific value.
            "cloud_cover_pct":
            (
                float(asset.cloud_cover_pct)
                if asset.cloud_cover_pct is not None
                else None
            ),

            "resolution_m":
            (
                float(asset.resolution_m)
                if asset.resolution_m is not None
                else None
            ),

            "bounds_native":
            asset.bounds_native,

            "bounds_wgs84":
            asset.bounds_wgs84,

            "crs":
            asset.crs,

            "affine_transform":
            asset.affine_transform,

            "width":
            asset.width,

            "height":
            asset.height,

            "band_count":
            asset.band_count,

            "dtype":
            asset.dtype,

            "is_georeferenced":
            asset.is_georeferenced,

            "processing_status":
            asset.processing_status,

            "validation_report":
            asset.validation_report,

            "geotiff_url":
            make_absolute_url(
                getattr(
                    dto,
                    "geotiff_url",
                    None,
                ),
                request,
            ),

            "preview_url":
            make_absolute_url(
                getattr(
                    dto,
                    "preview_url",
                    None,
                ),
                request,
            ),

            "thumbnail_url":
            make_absolute_url(
                getattr(
                    dto,
                    "thumbnail_url",
                    None,
                ),
                request,
            ),

            "artifacts":
            artifacts,

            "provenance":
            asset.provenance,

            "created_at":
            asset.created_at.isoformat(),
        }

        return Response(data)


class DedicatedImageryPreviewView(
    views.APIView,
):
    """
    GET /api/imagery/<uuid:image_id>/preview/
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        image_id,
    ):
        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
        )

        get_session_for_user_or_403(
            asset.session_id,
            request.user,
        )

        try:
            from apps.imagery.services.artifacts import (
                register_imagery_artifacts,
            )

            dto = register_imagery_artifacts(
                asset
            )

        except Exception as exc:
            raise Http404(
                f"Unable to generate imagery preview: {exc}"
            )

        candidates = [
            (
                getattr(
                    dto,
                    "preview_path",
                    None,
                ),
                "image/webp",
            ),
            (
                getattr(
                    dto,
                    "thumbnail_path",
                    None,
                ),
                "image/webp",
            ),
        ]

        for path, mime_type in candidates:
            if path and os.path.isfile(path):
                return FileResponse(
                    open(path, "rb"),
                    content_type=mime_type,
                )

        raise Http404(
            "Preview is not available."
        )


# ---------------------------------------------------------------------------
# Image pairs
# ---------------------------------------------------------------------------

class SessionPairListCreateView(
    SessionAccessMixin,
    views.APIView,
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        session_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        pairs = (
            ImagePair.objects
            .filter(session=session)
            .select_related(
                "image_a",
                "image_b",
            )
            .order_by("-created_at")
        )

        return Response(
            ImagePairSerializer(
                pairs,
                many=True,
            ).data
        )

    def post(
        self,
        request,
        session_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        image_a_id = request.data.get(
            "image_a_id"
        )

        image_b_id = request.data.get(
            "image_b_id"
        )

        pair_type = str(
            request.data.get(
                "pair_type",
                "BI_TEMPORAL",
            )
        ).upper()

        if not image_a_id:
            return Response(
                {
                    "error":
                    "image_a_id is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not image_b_id:
            return Response(
                {
                    "error":
                    "image_b_id is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if pair_type not in ALLOWED_PAIR_TYPES:
            return Response(
                {
                    "error":
                    "Unsupported pair_type.",
                    "allowed":
                    sorted(ALLOWED_PAIR_TYPES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        image_a = get_object_or_404(
            ImageAsset,
            id=image_a_id,
            session_id=session.id,
        )

        image_b = get_object_or_404(
            ImageAsset,
            id=image_b_id,
            session_id=session.id,
        )

        if image_a.id == image_b.id:
            return Response(
                {
                    "error":
                    "Image A and Image B must be different assets."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        pair = ImagePair.objects.create(
            session=session,
            image_a=image_a,
            image_b=image_b,
            pair_type=pair_type,
            compatibility_status="PENDING",
        )

        log_audit_event(
            request.user,
            "CREATE_IMAGE_PAIR",
            "ImagePair",
            str(pair.id),
            {
                "session_id":
                str(session.id),
                "image_a_id":
                str(image_a.id),
                "image_b_id":
                str(image_b.id),
                "pair_type":
                pair_type,
            },
        )

        try:
            task_result = (
                check_pair_compatibility_task.delay(
                    str(pair.id)
                )
            )

            task_id = getattr(
                task_result,
                "id",
                None,
            )

        except Exception as exc:
            pair.compatibility_status = "INCOMPATIBLE"
            pair.compatibility_report = {
                "status":
                "INCOMPATIBLE",
                "error":
                (
                    "Compatibility validation "
                    "could not be queued."
                ),
            }
            pair.coregistration_status = "FAILED"

            pair.save(
                update_fields=[
                    "compatibility_status",
                    "compatibility_report",
                    "coregistration_status",
                ]
            )

            return Response(
                {
                    "error":
                    "Pair was created but compatibility validation could not be queued.",
                    "pair_id":
                    str(pair.id),
                    "compatibility_status":
                    pair.compatibility_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "pair_id":
                str(pair.id),
                "compatibility_status":
                pair.compatibility_status,
                "compatibility_report":
                pair.compatibility_report,
                "coregistration_status":
                pair.coregistration_status,
                "task_id":
                task_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImagePairDetailView(
    SessionAccessMixin,
    views.APIView,
):
    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        session_id,
        pair_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        pair = get_object_or_404(
            ImagePair.objects.select_related(
                "image_a",
                "image_b",
            ),
            id=pair_id,
            session_id=session.id,
        )

        return Response(
            ImagePairSerializer(
                pair
            ).data
        )


# ---------------------------------------------------------------------------
# XYZ tile endpoint
# ---------------------------------------------------------------------------

class ImageAssetTileView(
    views.APIView,
):
    """
    Dynamic XYZ raster tile endpoint.

    Supported layers:
        rgb
        false_color
        ndvi
        ndwi
        ndbi

    The actual RasterEngine is responsible for determining whether a
    requested scientific layer can genuinely be computed from the asset.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        image_id,
        z,
        x,
        y,
    ):
        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
        )

        get_session_for_user_or_403(
            asset.session_id,
            request.user,
        )

        if not asset.file:
            raise Http404(
                "Raster file is not available."
            )

        try:
            raster_path = asset.file.path
        except (AttributeError, ValueError):
            raise Http404(
                "Raster file path is unavailable."
            )

        if not os.path.isfile(
            raster_path
        ):
            raise Http404(
                "Raster file was not found."
            )

        layer = str(
            request.query_params.get(
                "layer",
                "rgb",
            )
        ).lower()

        if layer not in ALLOWED_TILE_LAYERS:
            return Response(
                {
                    "error":
                    "Unsupported tile layer.",
                    "allowed":
                    sorted(
                        ALLOWED_TILE_LAYERS
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            z_value = int(z)
            x_value = int(x)
            y_value = int(y)

        except (
            TypeError,
            ValueError,
        ):
            return Response(
                {
                    "error":
                    "Tile coordinates must be integers."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if z_value < 0:
            return Response(
                {
                    "error":
                    "Zoom level cannot be negative."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_tile = (2 ** z_value) - 1

        if x_value < 0 or x_value > max_tile:
            raise Http404(
                "Invalid tile X coordinate."
            )

        if y_value < 0 or y_value > max_tile:
            raise Http404(
                "Invalid tile Y coordinate."
            )

        try:
            from apps.geospatial.raster_engine import (
                RasterEngine,
            )

            tile_bytes = (
                RasterEngine.render_tile_png(
                    raster_path,
                    z_value,
                    x_value,
                    y_value,
                    layer=layer,
                )
            )

        except Exception as exc:
            raise Http404(
                f"Tile generation failed: {exc}"
            )

        if not tile_bytes:
            raise Http404(
                "The requested tile contains no renderable data."
            )

        response = HttpResponse(
            tile_bytes,
            content_type="image/png",
        )

        response["Cache-Control"] = (
            "private, max-age=86400"
        )

        return response


# ---------------------------------------------------------------------------
# AOI clipping
# ---------------------------------------------------------------------------

class ImageAssetClipAOIView(
    SessionAccessMixin,
    views.APIView,
):
    """
    Clip an imagery asset to a user-supplied AOI.

    The resulting asset retains the source geospatial reference only when
    the clipping operation actually produces trustworthy georeferenced
    metadata.
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def post(
        self,
        request,
        session_id,
        image_id,
    ):
        session = self.get_session(
            request,
            session_id,
        )

        asset = get_object_or_404(
            ImageAsset,
            id=image_id,
            session_id=session.id,
        )

        geometry = request.data.get(
            "aoi_geometry"
        )

        if not geometry:
            return Response(
                {
                    "error":
                    "aoi_geometry is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(
            geometry,
            dict,
        ):
            return Response(
                {
                    "error":
                    "aoi_geometry must be a GeoJSON geometry object."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        geometry_type = geometry.get(
            "type"
        )

        if geometry_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            return Response(
                {
                    "error":
                    "AOI geometry must be a Polygon or MultiPolygon."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        coordinates = geometry.get(
            "coordinates"
        )

        if not coordinates:
            return Response(
                {
                    "error":
                    "AOI geometry contains no coordinates."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not asset.file:
            return Response(
                {
                    "error":
                    "Original raster file is unavailable."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            source_path = asset.file.path
        except (AttributeError, ValueError):
            return Response(
                {
                    "error":
                    "Original raster file path is unavailable."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not os.path.isfile(
            source_path
        ):
            return Response(
                {
                    "error":
                    "Original raster file is missing from storage."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------------
        # Require trustworthy georeferencing for AOI clipping.
        #
        # A polygon expressed in geographic coordinates cannot safely be
        # applied to an unreferenced raster.
        # ---------------------------------------------------------------

        if not asset.is_georeferenced:
            return Response(
                {
                    "error":
                    (
                        "This imagery is not georeferenced. "
                        "An AOI in geographic/map coordinates cannot be "
                        "applied without a real CRS and affine transform."
                    ),
                    "code":
                    "MISSING_GEOREFERENCE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not asset.crs or not asset.affine_transform:
            return Response(
                {
                    "error":
                    (
                        "The imagery does not contain sufficient "
                        "geospatial metadata for AOI clipping."
                    ),
                    "code":
                    "INCOMPLETE_GEOREFERENCE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        clipped_filename = (
            f"clipped_aoi_{asset.id}.tif"
        )

        relative_dir = os.path.join(
            "imagery",
            str(session.id),
        )

        clipped_rel_path = os.path.join(
            relative_dir,
            clipped_filename,
        )

        media_root = getattr(
            settings,
            "MEDIA_ROOT",
            None,
        )

        if not media_root:
            return Response(
                {
                    "error":
                    "MEDIA_ROOT is not configured."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        clipped_abs_path = os.path.join(
            media_root,
            clipped_rel_path,
        )

        os.makedirs(
            os.path.dirname(
                clipped_abs_path
            ),
            exist_ok=True,
        )

        try:
            from apps.geospatial.raster_engine import (
                RasterEngine,
            )

            clipped_meta = (
                RasterEngine.clip_by_geometry(
                    source_path,
                    clipped_abs_path,
                    geometry,
                )
            )

        except Exception as exc:
            return Response(
                {
                    "error":
                    f"Raster clipping failed: {exc}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(
            clipped_meta,
            dict,
        ):
            return Response(
                {
                    "error":
                    "Raster clipping returned invalid metadata."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ---------------------------------------------------------------
        # Determine georeferencing from the actual clipping result.
        # ---------------------------------------------------------------

        clipped_crs = clipped_meta.get(
            "crs"
        )

        clipped_transform = clipped_meta.get(
            "transform"
        )

        clipped_bounds = clipped_meta.get(
            "bounds"
        )

        clipped_is_georeferenced = bool(
            clipped_crs
            and clipped_transform
        )

        clipped_resolution = (
            clipped_meta.get(
                "resolution_m"
            )
        )

        if clipped_resolution is None:
            # Do not invent resolution.
            clipped_resolution = (
                asset.resolution_m
                if asset.resolution_m is not None
                else None
            )

        clipped_asset = ImageAsset.objects.create(
            session=session,

            file=clipped_rel_path,

            original_filename=clipped_filename,

            content_type="image/tiff",

            file_format="GEOTIFF",

            sensor=asset.sensor,

            modality=asset.modality,

            width=clipped_meta.get(
                "width"
            ),

            height=clipped_meta.get(
                "height"
            ),

            band_count=clipped_meta.get(
                "band_count"
            ),

            dtype=clipped_meta.get(
                "dtype",
                asset.dtype,
            ),

            crs=clipped_crs,

            affine_transform=clipped_transform,

            bounds_native=clipped_meta.get(
                "bounds_native"
            ),

            bounds_wgs84=clipped_meta.get(
                "bounds_wgs84"
            ),

            resolution_m=clipped_resolution,

            acquisition_date=(
                asset.acquisition_date
            ),

            cloud_cover_pct=(
                asset.cloud_cover_pct
            ),

            is_georeferenced=(
                clipped_is_georeferenced
            ),

            processing_status="VALIDATED",

            validation_report={
                "source":
                "AOI_CLIP",
                "valid":
                True,
            },

            provenance={
                "source":
                "AOI_CLIP",

                "parent_asset_id":
                str(asset.id),

                "parent_filename":
                asset.original_filename,

                "aoi_geometry":
                geometry,

                "parent_georeferenced":
                asset.is_georeferenced,

                "derived_georeferenced":
                clipped_is_georeferenced,
            },
        )

        log_audit_event(
            request.user,
            "CLIP_AOI",
            "ImageAsset",
            str(clipped_asset.id),
            {
                "parent_asset_id":
                str(asset.id),
                "session_id":
                str(session.id),
            },
        )

        return Response(
            {
                "status":
                "CLIPPED",

                "asset_id":
                str(clipped_asset.id),

                "asset":
                ImageAssetSerializer(
                    clipped_asset
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )