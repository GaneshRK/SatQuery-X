"""GeoTIFF/PNG/JPEG ingestion, validation, and metadata extraction."""

from __future__ import annotations

import io
import uuid
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


ALLOWED_CONTENT_TYPES = {
    "image/tiff": ".tif",
    "image/geotiff": ".tif",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/octet-stream": ".tif",
}


@dataclass
class RasterMetadata:
    filename: str
    content_type: str
    width: int
    height: int
    band_count: int
    geo_referenced: bool = False
    crs: str | None = None
    bounds_wgs84: dict[str, float] | None = None
    affine: list[float] | None = None
    nodata: float | None = None
    sensor_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PairValidationResult:
    valid: bool
    message: str
    overlap_bounds: dict[str, float] | None = None
    requires_reprojection: bool = False


def detect_sensor_type(filename: str, band_count: int, metadata: dict | None = None) -> str:
    name = filename.lower()
    if "sar" in name or "s1" in name or "risat" in name:
        return "sar"
    if band_count == 1 and "sar" in (metadata or {}).get("description", "").lower():
        return "sar"
    if band_count >= 3:
        return "optical"
    return "unknown"


def parse_raster(data: bytes, filename: str, content_type: str) -> RasterMetadata:
    ext = Path(filename).suffix.lower()
    is_geotiff = ext in {".tif", ".tiff", ".geotiff"} or "tiff" in content_type

    if is_geotiff and HAS_RASTERIO:
        try:
            return _parse_geotiff(data, filename, content_type)
        except Exception:
            pass

    return _parse_plain_image(data, filename, content_type)


def _parse_geotiff(data: bytes, filename: str, content_type: str) -> RasterMetadata:
    with rasterio.open(io.BytesIO(data)) as src:
        crs_str = src.crs.to_string() if src.crs else None
        geo_referenced = src.crs is not None
        bounds_wgs84 = None
        if geo_referenced and src.crs:
            try:
                wgs84_bounds = transform_bounds(src.crs, CRS.from_epsg(4326), *src.bounds)
                bounds_wgs84 = {
                    "west": wgs84_bounds[0],
                    "south": wgs84_bounds[1],
                    "east": wgs84_bounds[2],
                    "north": wgs84_bounds[3],
                }
            except Exception:
                pass
        affine = list(src.transform)[:6] if src.transform else None
        band_count = src.count
        sensor = detect_sensor_type(filename, band_count, src.tags())
        return RasterMetadata(
            filename=filename,
            content_type=content_type,
            width=src.width,
            height=src.height,
            band_count=band_count,
            geo_referenced=geo_referenced,
            crs=crs_str,
            bounds_wgs84=bounds_wgs84,
            affine=affine,
            nodata=src.nodata,
            sensor_type=sensor,
            extra={"driver": src.driver, "dtype": str(src.dtypes[0])},
        )


def _parse_plain_image(data: bytes, filename: str, content_type: str) -> RasterMetadata:
    with Image.open(io.BytesIO(data)) as img:
        arr = np.array(img)
        band_count = 1 if arr.ndim == 2 else arr.shape[2]
        return RasterMetadata(
            filename=filename,
            content_type=content_type,
            width=img.width,
            height=img.height,
            band_count=band_count,
            geo_referenced=False,
            sensor_type=detect_sensor_type(filename, band_count),
        )


def validate_pair(meta_a: RasterMetadata, meta_b: RasterMetadata) -> PairValidationResult:
    if not meta_a.geo_referenced or not meta_b.geo_referenced:
        if meta_a.width == meta_b.width and meta_a.height == meta_b.height:
            return PairValidationResult(
                valid=True,
                message="Non-georeferenced pair accepted with matching dimensions.",
            )
        return PairValidationResult(
            valid=False,
            message="Non-georeferenced images must have matching width and height.",
        )

    if meta_a.bounds_wgs84 and meta_b.bounds_wgs84:
        a = meta_a.bounds_wgs84
        b = meta_b.bounds_wgs84
        overlap = {
            "west": max(a["west"], b["west"]),
            "south": max(a["south"], b["south"]),
            "east": min(a["east"], b["east"]),
            "north": min(a["north"], b["north"]),
        }
        if overlap["west"] >= overlap["east"] or overlap["south"] >= overlap["north"]:
            return PairValidationResult(valid=False, message="Images do not overlap geographically.")
        requires_reprojection = meta_a.crs != meta_b.crs
        return PairValidationResult(
            valid=True,
            message="Pair validated with geographic overlap.",
            overlap_bounds=overlap,
            requires_reprojection=requires_reprojection,
        )

    return PairValidationResult(valid=False, message="Unable to validate georeferenced pair.")


def detect_input_mode(image_metas: list[RasterMetadata]) -> str:
    if len(image_metas) == 1:
        return "single_image"
    if len(image_metas) == 2:
        sensors = {m.sensor_type for m in image_metas}
        if sensors == {"optical", "sar"} or ("optical" in sensors and "sar" in sensors):
            return "cross_modal_pair"
        return "bi_temporal"
    raise ValueError(f"Unsupported image count: {len(image_metas)}")


def raster_to_preview_png(data: bytes, filename: str) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext in {".tif", ".tiff"} and HAS_RASTERIO:
        try:
            with rasterio.open(io.BytesIO(data)) as src:
                if src.count >= 3:
                    rgb = np.stack([src.read(i) for i in (1, 2, 3)], axis=-1)
                else:
                    band = src.read(1)
                    rgb = np.stack([band, band, band], axis=-1)
                rgb = _normalize_to_uint8(rgb)
                img = Image.fromarray(rgb)
        except Exception:
            img = Image.open(io.BytesIO(data)).convert("RGB")
    else:
        img = Image.open(io.BytesIO(data)).convert("RGB")

    buf = io.BytesIO()
    img.thumbnail((512, 512))
    img.save(buf, format="PNG")
    return buf.getvalue()


def pixel_bbox_to_geojson(
    bbox: list[float],
    affine: list[float] | None,
    crs: str | None,
    bounds_wgs84: dict[str, float] | None,
) -> dict:
    """Convert pixel-space bbox [x1,y1,x2,y2] to GeoJSON polygon."""
    x1, y1, x2, y2 = bbox

    # Method 1: Affine matrix transform + CRS reprojection
    if affine and len(affine) >= 6:
        # standard 6-param affine: [a, b, c, d, e, f] where
        # x_geo = c + x * a + y * b
        # y_geo = f + x * d + y * e
        a, b, c, d, e, f = affine[:6]
        corners = [
            (c + x1 * a + y1 * b, f + x1 * d + y1 * e),
            (c + x2 * a + y1 * b, f + x2 * d + y1 * e),
            (c + x2 * a + y2 * b, f + x2 * d + y2 * e),
            (c + x1 * a + y2 * b, f + x1 * d + y2 * e),
        ]

        if crs and HAS_GEO_LIBS:
            try:
                transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                coords = [list(transformer.transform(x, y)) for x, y in corners]
                coords.append(coords[0])
                return {"type": "Polygon", "coordinates": [coords]}
            except Exception:
                pass

        coords = [list(pt) for pt in corners]
        coords.append(coords[0])
        return {"type": "Polygon", "coordinates": [coords]}

    # Method 2: Bounds WGS84 bounding box
    if bounds_wgs84:
        w, s, e, n = bounds_wgs84["west"], bounds_wgs84["south"], bounds_wgs84["east"], bounds_wgs84["north"]
        coords = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        return {"type": "Polygon", "coordinates": [coords]}

    # Method 3: Normalized coordinate fallback
    coords = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]
    return {"type": "Polygon", "coordinates": [coords]}


def _normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    p2, p98 = np.percentile(arr, (2, 98))
    if p98 <= p2:
        p2, p98 = arr.min(), arr.max()
    if p98 <= p2:
        return np.zeros(arr.shape, dtype=np.uint8)
    scaled = np.clip((arr - p2) / (p98 - p2) * 255, 0, 255)
    return scaled.astype(np.uint8)


def generate_storage_key(session_id: uuid.UUID, filename: str) -> str:
    return f"sessions/{session_id}/raw/{uuid.uuid4()}_{Path(filename).name}"
