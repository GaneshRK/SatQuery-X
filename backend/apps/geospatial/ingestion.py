"""
Raster ingestion, metadata extraction and validation.

The ingestion layer never invents:
- CRS
- coordinates
- resolution
- sensor
- cloud percentage
- geotransform
"""

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
    from pyproj import CRS as PyprojCRS
    from shapely.geometry import box

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

    sensor: str | None
    modality: str | None

    is_georeferenced: bool

    cloud_cover_pct: float | None

    validation_report: dict[str, Any] = field(
        default_factory=dict
    )


def detect_sensor_and_modality(
    filename: str,
    band_count: int,
    tags: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """
    Conservative sensor identification.

    Sensor names are inferred only when the filename/metadata contains
    an explicit recognizable identifier.

    Unknown imagery remains UNKNOWN rather than being assigned a real
    satellite.
    """

    tags = tags or {}

    filename_lower = Path(filename).name.lower()

    description = str(
        tags.get("DESCRIPTION", "")
    ).lower()

    sensor_tag = str(
        tags.get("SENSOR", "")
    ).lower()

    combined = (
        f"{filename_lower} "
        f"{description} "
        f"{sensor_tag}"
    )

    if "sentinel-1" in combined or "sentinel1" in combined:
        return "SENTINEL-1", "SAR"

    if "risat" in combined:
        return "RISAT", "SAR"

    if "sentinel-2" in combined or "sentinel2" in combined:
        return "SENTINEL-2", "MULTISPECTRAL"

    if "landsat-8" in combined or "landsat8" in combined:
        return "LANDSAT-8", "MULTISPECTRAL"

    if "landsat-9" in combined or "landsat9" in combined:
        return "LANDSAT-9", "MULTISPECTRAL"

    if "landsat" in combined:
        return "LANDSAT-OLI", "MULTISPECTRAL"

    if "cartosat" in combined:
        return "CARTOSAT-2S", "OPTICAL"

    if "sar" in combined:
        return None, "SAR"

    if band_count > 4:
        return None, "MULTISPECTRAL"

    if band_count >= 3:
        return None, "OPTICAL"

    if band_count == 1:
        return None, "SINGLE_BAND"

    return None, None


def extract_metadata_from_bytes(
    data: bytes,
    filename: str,
) -> ExtractedRasterMetadata:
    """
    Extract metadata from uploaded raster/image bytes.
    """

    if not data:
        raise ValueError(
            "Uploaded raster is empty."
        )

    ext = Path(filename).suffix.lower()

    is_tiff = ext in {
        ".tif",
        ".tiff",
        ".geotiff",
    }

    if is_tiff:
        if not HAS_RASTERIO:
            raise RuntimeError(
                "rasterio is required to process GeoTIFF files."
            )

        return _extract_geotiff_metadata(
            data,
            filename,
        )

    return _extract_image_metadata(
        data,
        filename,
    )


def _extract_geotiff_metadata(
    data: bytes,
    filename: str,
) -> ExtractedRasterMetadata:
    with rasterio.open(
        io.BytesIO(data)
    ) as src:

        width = int(src.width)
        height = int(src.height)
        band_count = int(src.count)

        dtype = str(
            src.dtypes[0]
        )

        crs_str = (
            src.crs.to_string()
            if src.crs
            else None
        )

        affine = list(
            src.transform[:6]
        )

        bounds_native = {
            "left": float(src.bounds.left),
            "bottom": float(src.bounds.bottom),
            "right": float(src.bounds.right),
            "top": float(src.bounds.top),
        }

        bounds_wgs84 = None
        resolution_m = None

        if src.crs:

            try:
                transformed = transform_bounds(
                    src.crs,
                    CRS.from_epsg(4326),
                    *src.bounds,
                    densify_pts=21,
                )

                bounds_wgs84 = {
                    "west": float(transformed[0]),
                    "south": float(transformed[1]),
                    "east": float(transformed[2]),
                    "north": float(transformed[3]),
                }

            except Exception:
                bounds_wgs84 = None

            resolution_m = _calculate_resolution_m(
                src
            )

        tags = src.tags()

        sensor, modality = detect_sensor_and_modality(
            filename,
            band_count,
            tags,
        )

        cloud_cover = _extract_cloud_cover(
            tags
        )

        validation_report = {
            "status": "VALID",
            "driver": src.driver,
            "is_georeferenced": bool(
                src.crs is not None
                and src.transform is not None
            ),
            "has_crs": src.crs is not None,
            "has_transform": src.transform is not None,
            "has_bounds": bool(
                bounds_wgs84
            ),
            "has_nodata": src.nodata is not None,
        }

        if src.crs is None:
            validation_report["warnings"] = [
                "Raster has no CRS."
            ]

        if src.transform is None:
            validation_report.setdefault(
                "warnings",
                [],
            ).append(
                "Raster has no affine transform."
            )

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
            is_georeferenced=bool(
                src.crs is not None
                and src.transform is not None
            ),
            cloud_cover_pct=cloud_cover,
            validation_report=validation_report,
        )


def _calculate_resolution_m(
    src,
) -> float | None:
    """
    Determine approximate pixel size in meters.

    Returns None when the CRS cannot safely be interpreted in meters.
    """

    if not src.crs:
        return None

    try:
        crs = PyprojCRS.from_user_input(
            src.crs
        )

        if crs.is_projected:
            units = {
                axis.unit_name.lower()
                for axis in crs.axis_info
                if axis.unit_name
            }

            if not any(
                unit in {
                    "metre",
                    "meter",
                    "m",
                }
                for unit in units
            ):
                return None

            return float(
                (
                    abs(src.res[0])
                    + abs(src.res[1])
                )
                / 2.0
            )

        if crs.is_geographic:
            center_lat = (
                src.bounds.bottom
                + src.bounds.top
            ) / 2.0

            lat_rad = math.radians(
                center_lat
            )

            meters_lat = (
                111132.92
                - 559.82 * math.cos(
                    2 * lat_rad
                )
                + 1.175 * math.cos(
                    4 * lat_rad
                )
            )

            meters_lon = (
                111412.84 * math.cos(
                    lat_rad
                )
                - 93.5 * math.cos(
                    3 * lat_rad
                )
            )

            return float(
                (
                    abs(src.res[0]) * meters_lon
                    + abs(src.res[1]) * meters_lat
                )
                / 2.0
            )

    except Exception:
        return None

    return None


def _extract_cloud_cover(
    tags: dict[str, Any],
) -> float | None:
    candidates = (
        "CLOUD_COVER",
        "CLOUD_COVERAGE",
        "CLOUD_COVER_PERCENTAGE",
        "CLOUDY_PIXEL_PERCENTAGE",
    )

    for key in candidates:
        if key not in tags:
            continue

        try:
            value = float(
                tags[key]
            )

            if 0.0 <= value <= 100.0:
                return value

        except (
            TypeError,
            ValueError,
        ):
            continue

    return None


def _extract_image_metadata(
    data: bytes,
    filename: str,
) -> ExtractedRasterMetadata:
    with Image.open(
        io.BytesIO(data)
    ) as image:

        width, height = image.size
        band_count = len(
            image.getbands()
        )

        sensor, modality = detect_sensor_and_modality(
            filename,
            band_count,
        )

        return ExtractedRasterMetadata(
            width=int(width),
            height=int(height),
            band_count=int(band_count),
            dtype=str(
                np.asarray(image).dtype
            ),
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
                "has_crs": False,
                "has_transform": False,
                "notice": (
                    "Standard image format without embedded "
                    "geospatial metadata."
                ),
            },
        )


def generate_thumbnail_png(
    data: bytes,
    max_size: int = 512,
) -> bytes:
    """
    Generate a display thumbnail.

    This is a visualization operation and does not alter the source raster.
    """

    if max_size <= 0:
        raise ValueError(
            "max_size must be positive."
        )

    with Image.open(
        io.BytesIO(data)
    ) as image:

        image.thumbnail(
            (
                max_size,
                max_size,
            ),
            Image.Resampling.LANCZOS,
        )

        if image.mode not in {
            "RGB",
            "RGBA",
        }:
            image = image.convert(
                "RGB"
            )

        output = io.BytesIO()

        image.save(
            output,
            format="PNG",
            optimize=True,
        )

        return output.getvalue()


def validate_image_pair_compatibility(
    image_a,
    image_b,
    pair_type: str,
) -> dict[str, Any]:
    """
    Validate two imagery assets for comparison/fusion.

    The function reports compatibility issues and required processing
    actions without silently performing them.
    """

    pair_type = pair_type.upper().strip()

    issues: list[str] = []
    actions: list[str] = []

    modality_a = getattr(
        image_a,
        "modality",
        None,
    )

    modality_b = getattr(
        image_b,
        "modality",
        None,
    )

    crs_a = getattr(
        image_a,
        "crs",
        None,
    )

    crs_b = getattr(
        image_b,
        "crs",
        None,
    )

    resolution_a = getattr(
        image_a,
        "resolution_m",
        None,
    )

    resolution_b = getattr(
        image_b,
        "resolution_m",
        None,
    )

    bounds_a = getattr(
        image_a,
        "bounds_wgs84",
        None,
    )

    bounds_b = getattr(
        image_b,
        "bounds_wgs84",
        None,
    )

    if pair_type not in {
        "BI_TEMPORAL",
        "CROSS_MODAL",
    }:
        issues.append(
            f"Unsupported pair type: {pair_type}"
        )

    if pair_type == "CROSS_MODAL":
        optical_values = {
            "OPTICAL",
            "MULTISPECTRAL",
        }

        if not (
            modality_a in optical_values
            and modality_b == "SAR"
        ) and not (
            modality_b in optical_values
            and modality_a == "SAR"
        ):
            issues.append(
                "Cross-modal comparison requires one optical/"
                "multispectral raster and one SAR raster."
            )

    if pair_type == "BI_TEMPORAL":
        if (
            modality_a
            and modality_b
            and modality_a != modality_b
        ):
            actions.append(
                "Different modalities detected. "
                "Temporal comparison should verify whether the "
                "chosen analysis is scientifically valid."
            )

    if crs_a != crs_b:
        if crs_a and crs_b:
            actions.append(
                f"CRS mismatch: {crs_a} vs {crs_b}. "
                "Coregistration/reprojection is required."
            )
        else:
            issues.append(
                "Both images require verified CRS information "
                "for geographic comparison."
            )

    if (
        resolution_a is not None
        and resolution_b is not None
    ):
        smaller = min(
            resolution_a,
            resolution_b,
        )
        larger = max(
            resolution_a,
            resolution_b,
        )

        if smaller > 0:
            ratio = larger / smaller

            if ratio > 3.0:
                actions.append(
                    "Resolution mismatch is substantial; "
                    "resampling strategy must be selected explicitly."
                )

    overlap_pct: float | None = None

    if bounds_a and bounds_b:
        if HAS_GEO_LIBS:

            try:
                box_a = box(
                    bounds_a["west"],
                    bounds_a["south"],
                    bounds_a["east"],
                    bounds_a["north"],
                )

                box_b = box(
                    bounds_b["west"],
                    bounds_b["south"],
                    bounds_b["east"],
                    bounds_b["north"],
                )

                if not box_a.intersects(
                    box_b
                ):
                    overlap_pct = 0.0
                    issues.append(
                        "The two rasters have no geographic intersection."
                    )
                else:
                    intersection = box_a.intersection(
                        box_b
                    )

                    smaller_area = min(
                        box_a.area,
                        box_b.area,
                    )

                    if smaller_area > 0:
                        overlap_pct = round(
                            (
                                intersection.area
                                / smaller_area
                            )
                            * 100.0,
                            2,
                        )

                        if overlap_pct < 20.0:
                            issues.append(
                                f"Geographic overlap is only "
                                f"{overlap_pct}%; comparison may be unreliable."
                            )

            except Exception as exc:
                actions.append(
                    f"Could not calculate geographic overlap: {exc}"
                )

    else:
        actions.append(
            "Geographic overlap cannot be verified because one or "
            "both rasters lack WGS84 bounds."
        )

    compatible = not issues

    return {
        "status": (
            "COMPATIBLE"
            if compatible
            else "INCOMPATIBLE"
        ),
        "compatible": compatible,
        "issues": issues,
        "actions_required": actions,
        "overlap_percentage": overlap_pct,
    }