"""
Projection-aware geospatial calculations.

This module deliberately refuses to fabricate ground dimensions when
CRS/geotransform information is unavailable.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    import rasterio.features
    from rasterio.transform import Affine
    from rasterio.warp import transform_geom

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from pyproj import CRS, Geod, Transformer
    from shapely.geometry import shape

    HAS_GEO = True
except ImportError:
    HAS_GEO = False


def _is_geographic_crs(crs_str: str | None) -> bool:
    if not crs_str:
        return False

    try:
        crs = CRS.from_user_input(crs_str)
        return bool(crs.is_geographic)
    except Exception:
        value = crs_str.lower()
        return (
            "4326" in value
            or "wgs 84" in value
            or "geographic" in value
        )


def calculate_pixel_area_m2(
    affine_list: list[float] | tuple[float, ...] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
    default_res_m: float | None = None,
) -> float:
    """
    Calculate ground area represented by one raster pixel.

    `default_res_m` exists only for backwards compatibility.

    It is intentionally NOT used unless explicitly supplied by the caller.
    """

    if not affine_list or len(affine_list) < 6:
        if default_res_m is not None:
            if default_res_m <= 0:
                raise ValueError("default_res_m must be positive.")

            return float(default_res_m * default_res_m)

        raise ValueError(
            "Pixel area cannot be calculated because the raster has no "
            "valid affine transform."
        )

    if not crs_str:
        raise ValueError(
            "Pixel area cannot be calculated safely without CRS metadata."
        )

    a = float(affine_list[0])
    b = float(affine_list[1])
    d = float(affine_list[3])
    e = float(affine_list[4])

    if _is_geographic_crs(crs_str):
        if not bounds_wgs84:
            raise ValueError(
                "Geographic pixel area requires WGS84 bounds."
            )

        lat_center = (
            float(bounds_wgs84["south"])
            + float(bounds_wgs84["north"])
        ) / 2.0

        lat_rad = math.radians(lat_center)

        # Local ellipsoidal scale approximation.
        meters_per_degree_lat = (
            111132.92
            - 559.82 * math.cos(2 * lat_rad)
            + 1.175 * math.cos(4 * lat_rad)
            - 0.0023 * math.cos(6 * lat_rad)
        )

        meters_per_degree_lon = (
            111412.84 * math.cos(lat_rad)
            - 93.5 * math.cos(3 * lat_rad)
        )

        # For a north-up raster, this reduces to |a * e|.
        # For rotated rasters, use determinant of the affine matrix.
        pixel_area_degrees = abs(
            a * e - b * d
        )

        return float(
            pixel_area_degrees
            * meters_per_degree_lon
            * meters_per_degree_lat
        )

    # Projected CRS.
    try:
        crs = CRS.from_user_input(crs_str)

        axis_units = [
            axis.unit_name.lower()
            for axis in crs.axis_info
            if axis.unit_name
        ]

        if axis_units and not any(
            unit in {"metre", "meter", "m"}
            for unit in axis_units
        ):
            raise ValueError(
                f"Projected CRS '{crs_str}' does not use meter units."
            )

    except Exception as exc:
        raise ValueError(
            f"Unable to verify CRS units for '{crs_str}'."
        ) from exc

    return float(abs(a * e - b * d))


def quantify_mask_area(
    mask: np.ndarray,
    affine_list: list[float] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Quantify the ground area represented by a binary mask.
    """

    arr = np.asarray(mask)

    if arr.ndim != 2:
        raise ValueError(
            "Mask must be a 2D array."
        )

    valid_pixel_count = int(
        np.count_nonzero(arr)
    )

    pixel_area_m2 = calculate_pixel_area_m2(
        affine_list,
        crs_str,
        bounds_wgs84,
    )

    area_m2 = (
        valid_pixel_count
        * pixel_area_m2
    )

    return {
        "valid_pixel_count": valid_pixel_count,
        "pixel_area_m2": round(pixel_area_m2, 6),
        "area_m2": round(area_m2, 3),
        "area_ha": round(area_m2 / 10_000.0, 6),
        "area_km2": round(area_m2 / 1_000_000.0, 9),
    }


def calculate_polygon_ground_area_m2(
    poly_geom: Any,
    crs_str: str | None = None,
) -> float:
    """
    Calculate polygon ground area in square meters.

    For geographic coordinates, geodesic area is calculated from WGS84.
    """

    if not HAS_GEO:
        raise RuntimeError(
            "pyproj and shapely are required for polygon area calculation."
        )

    poly = (
        shape(poly_geom)
        if isinstance(poly_geom, dict)
        else poly_geom
    )

    if poly.is_empty:
        return 0.0

    if not poly.is_valid:
        poly = poly.buffer(0)

    if poly.is_empty:
        return 0.0

    if not crs_str:
        raise ValueError(
            "Polygon CRS is required for metric area calculation."
        )

    crs = CRS.from_user_input(crs_str)

    if crs.is_projected:
        unit_names = {
            axis.unit_name.lower()
            for axis in crs.axis_info
            if axis.unit_name
        }

        if unit_names and not any(
            unit in {"metre", "meter", "m"}
            for unit in unit_names
        ):
            raise ValueError(
                "Polygon projected CRS does not use meters."
            )

        return float(poly.area)

    if not crs.is_geographic:
        raise ValueError(
            f"Unsupported CRS type for polygon area: {crs_str}"
        )

    geod = Geod(
        ellps="WGS84"
    )

    area, _ = geod.geometry_area_perimeter(
        poly
    )

    return float(abs(area))


def polygonize_mask_to_geojson(
    mask: np.ndarray,
    affine_list: list[float] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
    class_label: str = "detected_feature",
    confidence: float | None = None,
    min_area_pixels: int = 15,
) -> list[dict[str, Any]]:
    """
    Polygonize a binary mask.

    GeoJSON is returned only when the raster has enough spatial metadata
    to transform the geometry into WGS84.

    Unreferenced imagery does NOT receive fabricated coordinates.
    """

    arr = np.asarray(mask)

    if arr.ndim != 2:
        raise ValueError(
            "Mask must be a 2D array."
        )

    if not affine_list or len(affine_list) < 6:
        raise ValueError(
            "Polygonization requires a valid raster affine transform."
        )

    if not crs_str:
        raise ValueError(
            "Polygonization requires a valid CRS."
        )

    if not HAS_RASTERIO:
        raise RuntimeError(
            "rasterio is required for geospatial polygonization."
        )

    if not HAS_GEO:
        raise RuntimeError(
            "shapely and pyproj are required for geospatial polygonization."
        )

    transform = Affine(
        *affine_list[:6]
    )

    mask_uint8 = (
        arr > 0
    ).astype(np.uint8)

    features: list[dict[str, Any]] = []

    for geom, value in rasterio.features.shapes(
        mask_uint8,
        mask=mask_uint8.astype(bool),
        transform=transform,
    ):
        if value == 0:
            continue

        geometry = shape(geom)

        if geometry.is_empty:
            continue

        if not geometry.is_valid:
            geometry = geometry.buffer(0)

        if geometry.is_empty:
            continue

        pixel_count = int(
            np.count_nonzero(
                rasterio.features.geometry_mask(
                    [geometry],
                    out_shape=arr.shape,
                    transform=transform,
                    invert=True,
                )
            )
        )

        if pixel_count < min_area_pixels:
            continue

        area_m2 = calculate_polygon_ground_area_m2(
            geometry,
            crs_str,
        )

        geometry_wgs84 = geom

        if CRS.from_user_input(crs_str) != CRS.from_epsg(4326):
            geometry_wgs84 = transform_geom(
                crs_str,
                "EPSG:4326",
                geom,
                precision=8,
            )

        properties: dict[str, Any] = {
            "label": class_label,
            "pixel_count": pixel_count,
            "area_m2": round(area_m2, 3),
            "area_ha": round(area_m2 / 10_000.0, 6),
            "area_km2": round(area_m2 / 1_000_000.0, 9),
        }

        if confidence is not None:
            properties["confidence"] = round(
                float(np.clip(confidence, 0.0, 1.0)),
                4,
            )

        features.append(
            {
                "type": "Feature",
                "geometry": geometry_wgs84,
                "properties": properties,
            }
        )

    return features