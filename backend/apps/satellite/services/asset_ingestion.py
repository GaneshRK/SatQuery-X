"""Real satellite asset download and validation service.

Only provider-hosted assets are downloaded. A successful ingestion is recorded
only after bytes exist locally and, for raster assets, the file can be opened
and its geospatial metadata inspected.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.satellite.models import SatelliteAsset, SatelliteScene
from apps.satellite.providers import get_satellite_provider

try:
    import rasterio
except ImportError:  # pragma: no cover
    rasterio = None


RASTER_EXTENSIONS = {".tif", ".tiff", ".jp2", ".vrt", ".img"}


def _sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _storage_root() -> Path:
    root = getattr(settings, "SATELLITE_ASSET_ROOT", None)
    if root:
        return Path(root).expanduser().resolve()
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        raise RuntimeError("MEDIA_ROOT or SATELLITE_ASSET_ROOT must be configured.")
    return Path(media_root).resolve() / "satellite"


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def _validate_raster(path: str) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    if suffix not in RASTER_EXTENSIONS:
        return {"validated": False, "validation": "binary_asset_only"}
    if rasterio is None:
        raise RuntimeError("rasterio is required to validate geospatial raster assets.")
    with rasterio.open(path) as dataset:
        if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
            raise ValueError("Downloaded raster has invalid dimensions/band count.")
        if dataset.crs is None:
            raise ValueError("Downloaded raster has no CRS; refusing to mark it analysis-ready.")
        if dataset.transform is None:
            raise ValueError("Downloaded raster has no affine transform; refusing to mark it analysis-ready.")
        return {
            "validated": True,
            "validation": "geospatial_raster",
            "width": dataset.width,
            "height": dataset.height,
            "bands": dataset.count,
            "dtype": dataset.dtypes,
            "crs": dataset.crs.to_string(),
            "transform": tuple(dataset.transform),
            "bounds": [dataset.bounds.left, dataset.bounds.bottom, dataset.bounds.right, dataset.bounds.top],
            "resolution": [float(dataset.res[0]), float(dataset.res[1])],
        }


def download_scene_asset(scene: SatelliteScene, asset: SatelliteAsset) -> dict[str, Any]:
    """Download one real provider asset and persist auditable provenance."""
    if not asset.href:
        raise ValueError("Satellite asset has no remote href.")
    provider_name = str(scene.provider or "copernicus").strip() or "copernicus"
    provider = get_satellite_provider(provider_name)

    root = _storage_root() / _safe_name(str(scene.sensor)) / _safe_name(str(scene.external_id))
    root.mkdir(parents=True, exist_ok=True)
    suffix = Path(asset.href.split("?", 1)[0]).suffix.lower() or ".bin"
    destination = root / f"{_safe_name(asset.asset_key)}{suffix}"

    result = provider.download_asset(asset.href, str(destination))
    actual_path = str(result.get("destination") or destination)
    if not os.path.isfile(actual_path) or os.path.getsize(actual_path) <= 0:
        raise RuntimeError("Provider reported a download, but no non-empty local file exists.")

    validation = _validate_raster(actual_path)
    checksum = _sha256(actual_path)
    byte_size = os.path.getsize(actual_path)

    asset.local_path = actual_path
    asset.is_downloaded = True
    asset.byte_size = byte_size
    asset.checksum = checksum
    asset.metadata = {
        **(asset.metadata or {}),
        "ingestion": {
            "provider": provider_name,
            "sha256": checksum,
            "validated": validation.get("validated", False),
            "validation": validation,
        },
    }
    asset.save(update_fields=["local_path", "is_downloaded", "byte_size", "checksum", "metadata", "updated_at"])

    scene.availability_status = "AVAILABLE"
    scene.save(update_fields=["availability_status", "updated_at"])

    return {
        "status": "downloaded",
        "scene_id": str(scene.id),
        "asset_id": str(asset.id),
        "asset_key": asset.asset_key,
        "local_path": actual_path,
        "bytes": byte_size,
        "sha256": checksum,
        "validation": validation,
    }
