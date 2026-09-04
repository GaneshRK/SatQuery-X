"""Raster ingestion, metadata extraction, validation, and pair compatibility."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from pyproj import Transformer
    from shapely.geometry import box, mapping
    HAS_GEO_LIBS = True
except ImportError:
    HAS_GEO_LIBS = False


@dataclass
class ExtractedRasterMetadata:
    width: int
    height: int
    band_count: int
    dtype: str
    crs: str | None
    affine_transform: list[float] | None
    bounds_native: dict[str, float] | None
    bounds_wgs84: dict[str, float] | None
    resolution_m: float | None
    sensor: str
    modality: str
    is_georeferenced: bool
    cloud_cover_pct: float | None
    validation_report: dict[str, Any] = field(default_factory=dict)


def detect_sensor_and_modality(filename: str, band_count: int, tags: dict[str, Any] | None = None) -> tuple[str, str]:
    tags = tags or {}
    lower_name = filename.lower()
    desc = str(tags.get("DESCRIPTION", "")).lower()

    if "sentinel-1" in lower_name or "s1" in lower_name or "risat" in lower_name or "sar" in lower_name:
        sensor = "RISAT" if "risat" in lower_name else "SENTINEL-1"
        return sensor, "SAR"

    if "cartosat" in lower_name:
        return "CARTOSAT-2S", "OPTICAL"

    if "sentinel-2" in lower_name or "sentinel2" in lower_name or "s2" in lower_name:
        modality = "MULTISPECTRAL" if band_count > 3 else "OPTICAL"
        return "SENTINEL-2", modality

    if band_count == 1 and ("sar" in desc or "db" in desc):
        return "SENTINEL-1", "SAR"

    if band_count > 3:
        return "UNKNOWN", "MULTISPECTRAL"
    if band_count in (3, 4):
        return "UNKNOWN", "OPTICAL"
    if band_count == 1:
        return "UNKNOWN", "SAR"

    return "UNKNOWN", "OPTICAL"


def extract_metadata_from_bytes(data: bytes, filename: str) -> ExtractedRasterMetadata:
    ext = Path(filename).suffix.lower()
    is_tiff = ext in (".tif", ".tiff", ".geotiff")

    if is_tiff and HAS_RASTERIO:
        try:
            return _extract_geotiff_metadata(data, filename)
        except Exception as e:
            # Fall back to image parser
            report = {"warning": f"Rasterio parsing error: {e}. Falling back to standard image decode."}
            meta = _extract_image_metadata(data, filename)
            meta.validation_report.update(report)
            return meta

    return _extract_image_metadata(data, filename)


def _extract_geotiff_metadata(data: bytes, filename: str) -> ExtractedRasterMetadata:
    with rasterio.open(io.BytesIO(data)) as src:
        width = src.width
        height = src.height
        band_count = src.count
        dtype = str(src.dtypes[0])
        crs_str = src.crs.to_string() if src.crs else None
        is_geo = src.crs is not None

        affine = list(src.transform)[:6]
        bounds_native = {
            "left": float(src.bounds.left),
            "bottom": float(src.bounds.bottom),
            "right": float(src.bounds.right),
            "top": float(src.bounds.top),
        }

        bounds_wgs84 = None
        resolution_m = None

        if is_geo and src.crs:
            try:
                wgs_bounds = transform_bounds(src.crs, CRS.from_epsg(4326), *src.bounds)
                bounds_wgs84 = {
                    "west": float(wgs_bounds[0]),
                    "south": float(wgs_bounds[1]),
                    "east": float(wgs_bounds[2]),
                    "north": float(wgs_bounds[3]),
                }
            except Exception:
                pass

            # Estimate ground sampling distance in meters
            if src.crs.is_projected:
                resolution_m = float(abs(src.res[0]))
            elif bounds_wgs84:
                # Geographic CRS degree to approx meters at center latitude
                lat_center = (bounds_wgs84["south"] + bounds_wgs84["north"]) / 2.0
                deg_lat_m = 111132.954 - 559.822 * math.cos(2 * math.radians(lat_center))
                resolution_m = float(abs(src.res[0]) * deg_lat_m)

        tags = src.tags()
        sensor, modality = detect_sensor_and_modality(filename, band_count, tags)

        validation_report = {
            "status": "VALID",
            "is_georeferenced": is_geo,
            "crs": crs_str,
            "driver": src.driver,
        }

        return ExtractedRasterMetadata(
            width=width,
            height=height,
            band_count=band_count,
            dtype=dtype,
            crs=crs_str,
            affine_transform=affine,
            bounds_native=bounds_native,
            bounds_wgs84=bounds_wgs84,
            resolution_m=resolution_m,
            sensor=sensor,
            modality=modality,
            is_georeferenced=is_geo,
            cloud_cover_pct=None,
            validation_report=validation_report,
        )


def _extract_image_metadata(data: bytes, filename: str) -> ExtractedRasterMetadata:
    img = Image.open(io.BytesIO(data))
    width, height = img.size
    bands = len(img.getbands())
    sensor, modality = detect_sensor_and_modality(filename, bands)

    return ExtractedRasterMetadata(
        width=width,
        height=height,
        band_count=bands,
        dtype="uint8",
        crs=None,
        affine_transform=None,
        bounds_native=None,
        bounds_wgs84=None,
        resolution_m=None,
        sensor=sensor,
        modality=modality,
        is_georeferenced=False,
        cloud_cover_pct=None,
        validation_report={
            "status": "VALID",
            "is_georeferenced": False,
            "notice": "Standard image format without embedded geospatial metadata.",
        },
    )


def generate_thumbnail_png(data: bytes, max_size: int = 512) -> bytes:
    img = Image.open(io.BytesIO(data))
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def validate_image_pair_compatibility(image_a, image_b, pair_type: str) -> dict[str, Any]:
    issues = []
    actions = []

    # Modality check
    if pair_type == "CROSS_MODAL":
        mods = {image_a.modality, image_b.modality}
        has_optical = any(m in ("OPTICAL", "MULTISPECTRAL") for m in mods)
        has_sar = "SAR" in mods
        if not (has_optical and has_sar):
            issues.append(
                f"CROSS_MODAL requires one optical/multispectral image and one SAR image. Found: {image_a.modality} and {image_b.modality}."
            )

    if pair_type == "BI_TEMPORAL":
        if image_a.modality != image_b.modality:
            actions.append(f"Modality difference ({image_a.modality} vs {image_b.modality}) in bi-temporal pair.")

    # CRS check
    if image_a.crs != image_b.crs:
        actions.append(f"CRS mismatch: {image_a.crs} vs {image_b.crs} — will require reprojection during coregistration.")

    # Resolution check
    if image_a.resolution_m and image_b.resolution_m:
        res_ratio = max(image_a.resolution_m, image_b.resolution_m) / max(0.001, min(image_a.resolution_m, image_b.resolution_m))
        if res_ratio > 3.0:
            actions.append(f"Resolution mismatch: {image_a.resolution_m}m vs {image_b.resolution_m}m — will resample to finer grid.")

    # Overlap check
    overlap_pct = 100.0
    if image_a.bounds_wgs84 and image_b.bounds_wgs84 and HAS_GEO_LIBS:
        box_a = box(
            image_a.bounds_wgs84["west"], image_a.bounds_wgs84["south"],
            image_a.bounds_wgs84["east"], image_a.bounds_wgs84["north"]
        )
        box_b = box(
            image_b.bounds_wgs84["west"], image_b.bounds_wgs84["south"],
            image_b.bounds_wgs84["east"], image_b.bounds_wgs84["north"]
        )
        if not box_a.intersects(box_b):
            issues.append("Rasters do not intersect geographically (0% spatial overlap).")
            overlap_pct = 0.0
        else:
            intersection_area = box_a.intersection(box_b).area
            smaller_area = min(box_a.area, box_b.area)
            overlap_pct = round((intersection_area / smaller_area) * 100.0, 1)
            if overlap_pct < 20.0:
                issues.append(f"Insufficient spatial overlap between rasters ({overlap_pct}%). Minimum 20% required.")

    is_compatible = len(issues) == 0
    status = "COMPATIBLE" if is_compatible else "INCOMPATIBLE"

    return {
        "status": status,
        "compatible": is_compatible,
        "issues": issues,
        "actions_required": actions,
        "overlap_percentage": overlap_pct,
    }
