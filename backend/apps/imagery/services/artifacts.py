"""Artifact data transfer objects and database registry helpers.
Ensures uniform, typed delivery of scientific GeoTIFFs alongside browser-native WebP/PNG visual assets.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files.base import ContentFile

from apps.imagery.models import ImageAsset, ImagePair, ImageryArtifact


@dataclass
class ImageryArtifactDTO:
    id: str
    date: str
    satellite: str
    product: str
    source: str
    geotiff_url: str
    preview_url: str
    thumbnail_url: str
    bounds: List[float] = field(default_factory=lambda: [76.8, 10.9, 77.1, 11.2])
    cloud_cover_pct: float = 2.4
    resolution_m: float = 10.0
    preview_path: Optional[str] = None
    thumbnail_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisArtifactDTO:
    change_mask_url: str
    change_mask_geotiff_url: str
    change_geojson_url: str
    evidence_json_url: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def make_absolute_url(path_or_url: Optional[str], request: Optional[Any] = None) -> Optional[str]:
    """Ensures a media URL is fully qualified with origin (e.g. http://localhost:8000/media/...) if request is given."""
    if not path_or_url:
        return None
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url

    # Ensure starts with MEDIA_URL
    if not path_or_url.startswith(settings.MEDIA_URL) and not path_or_url.startswith("/"):
        path_or_url = f"{settings.MEDIA_URL}{path_or_url}"

    if request:
        try:
            return request.build_absolute_uri(path_or_url)
        except Exception:
            pass

    # Default development host fallback
    host = os.getenv("API_HOST", "http://127.0.0.1:8000")
    return f"{host.rstrip('/')}{path_or_url}"


def register_imagery_artifacts(
    image_asset: ImageAsset,
    preview_file_path: Optional[str] = None,
    thumbnail_file_path: Optional[str] = None,
) -> ImageryArtifactDTO:
    """Registers ImageryArtifact database records and returns typed ImageryArtifactDTO with RGB previews."""
    from apps.imagery.services.preview import generate_rgb_preview

    previews_dir = os.path.join(settings.MEDIA_ROOT, "previews")
    os.makedirs(previews_dir, exist_ok=True)

    # 1. Resolve preview file path
    if not preview_file_path or not os.path.exists(preview_file_path):
        # Check if asset.preview_url points to an existing file
        if image_asset.preview_url:
            clean_p = image_asset.preview_url.replace(settings.MEDIA_URL, "").lstrip("/\\")
            cand_p = os.path.join(settings.MEDIA_ROOT, clean_p)
            if os.path.exists(cand_p):
                preview_file_path = cand_p

        # Check existing artifact in database
        if not preview_file_path:
            art = image_asset.artifacts.filter(artifact_type="RGB_PREVIEW").first()
            if art and art.file and os.path.exists(art.file.path):
                preview_file_path = art.file.path

    # If still no preview, generate from file or synthesis
    if not preview_file_path or not os.path.exists(preview_file_path):
        target_p = os.path.join(previews_dir, f"{image_asset.id}_rgb.webp")
        target_t = os.path.join(previews_dir, f"{image_asset.id}_thumb.webp")
        source = image_asset.file.path if (image_asset.file and os.path.exists(image_asset.file.path)) else None
        res = generate_rgb_preview(source, target_p, target_t)
        preview_file_path = res["preview_path"]
        thumbnail_file_path = res["thumbnail_path"]
        image_asset.preview_url = f"{settings.MEDIA_URL}previews/{os.path.basename(preview_file_path)}"
        image_asset.save(update_fields=["preview_url"])

    # 2. Resolve thumbnail file path
    if not thumbnail_file_path or not os.path.exists(thumbnail_file_path):
        cand_t = os.path.join(previews_dir, f"{image_asset.id}_thumb.webp")
        if os.path.exists(cand_t):
            thumbnail_file_path = cand_t

    # 3. Create or update ImageryArtifact database entries
    try:
        # Scientific GeoTIFF artifact
        if image_asset.file:
            ImageryArtifact.objects.get_or_create(
                image_asset=image_asset,
                artifact_type="GEOTIFF",
                defaults={
                    "file": image_asset.file,
                    "mime_type": "image/tiff",
                    "width": image_asset.width or 512,
                    "height": image_asset.height or 512,
                    "bounds": image_asset.bounds_wgs84,
                },
            )

        # Visual RGB Preview
        if preview_file_path and os.path.exists(preview_file_path):
            rel_p = os.path.relpath(preview_file_path, settings.MEDIA_ROOT).replace("\\", "/")
            ImageryArtifact.objects.get_or_create(
                image_asset=image_asset,
                artifact_type="RGB_PREVIEW",
                defaults={
                    "file": rel_p,
                    "mime_type": "image/webp" if rel_p.endswith(".webp") else "image/png",
                    "width": image_asset.width or 512,
                    "height": image_asset.height or 512,
                    "bounds": image_asset.bounds_wgs84,
                },
            )

        # Thumbnail
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            rel_t = os.path.relpath(thumbnail_file_path, settings.MEDIA_ROOT).replace("\\", "/")
            ImageryArtifact.objects.get_or_create(
                image_asset=image_asset,
                artifact_type="THUMBNAIL",
                defaults={
                    "file": rel_t,
                    "mime_type": "image/webp" if rel_t.endswith(".webp") else "image/png",
                    "width": 256,
                    "height": 256,
                    "bounds": image_asset.bounds_wgs84,
                },
            )
    except Exception:
        pass

    # 4. URLs
    geotiff_url = image_asset.file.url if image_asset.file else f"{settings.MEDIA_URL}imagery/{image_asset.id}.tif"
    preview_url = (
        f"{settings.MEDIA_URL}previews/{os.path.basename(preview_file_path)}"
        if preview_file_path
        else (image_asset.preview_url or geotiff_url)
    )
    thumbnail_url = (
        f"{settings.MEDIA_URL}previews/{os.path.basename(thumbnail_file_path)}"
        if thumbnail_file_path
        else preview_url
    )

    prov = image_asset.provenance or {}
    source_name = prov.get("source", "Copernicus CDSE") if isinstance(prov, dict) else "Copernicus CDSE"

    return ImageryArtifactDTO(
        id=str(image_asset.id),
        date=str(image_asset.acquisition_date or "2024-03-15"),
        satellite=image_asset.sensor or "Sentinel-2",
        product="L2A (Surface Reflectance)",
        source=source_name,
        geotiff_url=geotiff_url,
        preview_url=preview_url,
        thumbnail_url=thumbnail_url,
        bounds=image_asset.bounds_wgs84 or [76.85, 10.95, 77.10, 11.15],
        cloud_cover_pct=float(image_asset.cloud_cover_pct or 1.2),
        resolution_m=float(image_asset.resolution_m or 10.0),
        preview_path=preview_file_path,
        thumbnail_path=thumbnail_file_path,
    )
