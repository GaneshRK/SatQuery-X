"""Celery tasks for imagery ingestion and pairing per §13.1."""

from __future__ import annotations

from pathlib import Path
from celery import shared_task
from django.core.files.base import ContentFile

from apps.geospatial.ingestion import (
    extract_metadata_from_bytes,
    generate_thumbnail_png,
    validate_image_pair_compatibility,
)
from apps.imagery.models import ImageAsset, ImagePair


@shared_task(bind=True, max_retries=2)
def ingest_image_task(self, image_id: str):
    try:
        asset = ImageAsset.objects.get(id=image_id)
        asset.processing_status = "VALIDATING"
        asset.save()

        # Read raster bytes
        with asset.file.open("rb") as f:
            data = f.read()

        # Extract real geospatial metadata
        meta = extract_metadata_from_bytes(data, asset.original_filename)

        asset.width = meta.width
        asset.height = meta.height
        asset.band_count = meta.band_count
        asset.dtype = meta.dtype
        asset.crs = meta.crs
        asset.affine_transform = meta.affine_transform
        asset.bounds_native = meta.bounds_native
        asset.bounds_wgs84 = meta.bounds_wgs84
        asset.resolution_m = meta.resolution_m
        asset.sensor = meta.sensor
        asset.modality = meta.modality
        asset.is_georeferenced = meta.is_georeferenced
        asset.validation_report = meta.validation_report
        asset.processing_status = "VALIDATED"

        # Generate RGB preview and thumbnail
        try:
            from django.conf import settings
            from apps.imagery.services.preview import generate_rgb_preview
            from apps.imagery.services.artifacts import register_imagery_artifacts

            preview_dir = os.path.join(settings.MEDIA_ROOT, "previews")
            thumb_dir = os.path.join(settings.MEDIA_ROOT, "thumbnails")
            os.makedirs(preview_dir, exist_ok=True)
            os.makedirs(thumb_dir, exist_ok=True)

            out_preview = os.path.join(preview_dir, f"{asset.id}_rgb.webp")
            out_thumb = os.path.join(thumb_dir, f"{asset.id}_thumb.webp")

            raster_source = asset.file.path if hasattr(asset.file, "path") and os.path.exists(asset.file.path) else data
            res_dict = generate_rgb_preview(raster_source, out_preview, out_thumb)

            asset.preview_url = f"{settings.MEDIA_URL}previews/{asset.id}_rgb.webp"
            register_imagery_artifacts(asset, out_preview, out_thumb)
        except Exception as p_err:
            try:
                thumb_bytes = generate_thumbnail_png(data, max_size=512)
                preview_filename = f"preview_{asset.id}.png"
                from django.core.files.storage import default_storage
                preview_path = default_storage.save(f"previews/{preview_filename}", ContentFile(thumb_bytes))
                asset.preview_url = default_storage.url(preview_path)
            except Exception:
                pass

        asset.save()
        return {"status": "VALIDATED", "image_id": image_id}

    except Exception as exc:
        try:
            asset = ImageAsset.objects.get(id=image_id)
            asset.processing_status = "FAILED"
            asset.validation_report = {"error": str(exc)}
            asset.save()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=3)


@shared_task(bind=True)
def check_pair_compatibility_task(self, pair_id: str):
    pair = ImagePair.objects.get(id=pair_id)
    report = validate_image_pair_compatibility(pair.image_a, pair.image_b, pair.pair_type)
    pair.compatibility_status = report["status"]
    pair.compatibility_report = report
    pair.save()
    return report
