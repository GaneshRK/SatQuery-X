"""Geospatial math, projection-aware area quantification, and GeoJSON polygonization."""

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
    from pyproj import Transformer
    from shapely.geometry import Polygon, box, mapping, shape
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def calculate_pixel_area_m2(
    affine_list: list[float] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
    default_res_m: float = 10.0,
) -> float:
    """Calculate true ground area per pixel in m² using projection-aware math.

    Never multiplies by an arbitrary constant.
    """
    if not affine_list or len(affine_list) < 6:
        return float(default_res_m * default_res_m)

    dx = abs(affine_list[0])  # pixel width in native CRS
    dy = abs(affine_list[4])  # pixel height in native CRS

    # Check if CRS is projected (units typically in meters) or geographic (degrees)
    is_geographic = True
    if crs_str:
        lower_crs = crs_str.lower()
        if "utm" in lower_crs or "3857" in lower_crs or "326" in lower_crs or "327" in lower_crs:
            is_geographic = False
        elif "4326" in lower_crs or "wgs 84" in lower_crs or "degree" in lower_crs:
            is_geographic = True

    if not is_geographic:
        # Native units are already meters
        return float(dx * dy)

    # If geographic CRS (degrees), project locally at center latitude
    lat_center = 0.0
    if bounds_wgs84:
        lat_center = (bounds_wgs84.get("south", 0.0) + bounds_wgs84.get("north", 0.0)) / 2.0

    lat_rad = math.radians(lat_center)
    # WGS-84 degree length formulas
    deg_lat_m = 111132.954 - 559.822 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    deg_lon_m = 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)

    dx_m = dx * deg_lon_m
    dy_m = dy * deg_lat_m
    return float(dx_m * dy_m)


def quantify_mask_area(
    mask: np.ndarray,
    affine_list: list[float] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
) -> dict[str, float]:
    """Quantifies surface area from a binary raster mask."""
    valid_pixel_count = int(np.count_nonzero(mask))
    pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)

    area_m2 = float(valid_pixel_count * pixel_area_m2)
    area_ha = float(area_m2 / 10_000.0)
    area_km2 = float(area_m2 / 1_000_000.0)

    return {
        "valid_pixel_count": valid_pixel_count,
        "pixel_area_m2": round(pixel_area_m2, 4),
        "area_m2": round(area_m2, 2),
        "area_ha": round(area_ha, 4),
        "area_km2": round(area_km2, 6),
    }


def calculate_polygon_ground_area_m2(poly_geom: Any, crs_str: str | None = None) -> float:
    """Calculate true metric ground surface area in m² using equal-area projection."""
    if not HAS_SHAPELY:
        return 0.0

    poly = shape(poly_geom) if isinstance(poly_geom, dict) else poly_geom
    if poly.is_empty:
        return 0.0

    # If CRS is projected in meters (e.g. UTM)
    if crs_str and any(proj in crs_str.lower() for proj in ("utm", "326", "327")):
        return float(poly.area)

    # In Web Mercator (EPSG:3857)
    if crs_str and "3857" in crs_str:
        lat_center = math.radians(poly.centroid.y)
        return float(poly.area * (math.cos(lat_center) ** 2))

    # WGS84 Geographic degrees (EPSG:4326)
    centroid = poly.centroid
    lon_c, lat_c = centroid.x, centroid.y
    try:
        from shapely.ops import transform
        cea_crs = f"+proj=cea +lat_ts={lat_c:.4f} +lon_0={lon_c:.4f} +units=m"
        transformer = Transformer.from_crs("EPSG:4326", cea_crs, always_xy=True)
        poly_m = transform(transformer.transform, poly)
        return float(poly_m.area)
    except Exception:
        # Fallback using degree length conversion at center latitude
        lat_rad = math.radians(lat_c)
        deg_lat_m = 111132.954 - 559.822 * math.cos(2 * lat_rad)
        deg_lon_m = 111412.84 * math.cos(lat_rad)
        return float(poly.area * deg_lat_m * deg_lon_m)


def polygonize_mask_to_geojson(
    mask: np.ndarray,
    affine_list: list[float] | None,
    crs_str: str | None,
    bounds_wgs84: dict[str, float] | None = None,
    class_label: str = "detected_change",
    confidence: float = 0.85,
    min_area_pixels: int = 15,
) -> list[dict[str, Any]]:
    """Convert binary mask clusters into standard WGS84 GeoJSON polygon features."""
    features = []
    h, w = mask.shape[:2]

    # If rasterio is available and affine is provided
    if HAS_RASTERIO and affine_list and len(affine_list) >= 6:
        transform = Affine(*affine_list[:6])
        mask_uint8 = (mask > 0).astype(np.uint8)

        for geom, val in rasterio.features.shapes(mask_uint8, mask=(mask_uint8 > 0), transform=transform):
            poly_shape = shape(geom)
            if poly_shape.area <= 0:
                continue

            # Reproject geometry to WGS84 EPSG:4326 if needed
            geom_wgs84 = geom
            if crs_str and crs_str != "EPSG:4326":
                try:
                    geom_wgs84 = transform_geom(crs_str, "EPSG:4326", geom)
                except Exception:
                    pass

            # Calculate accurate metric area using geodesic equal-area projection
            feature_area_m2 = round(calculate_polygon_ground_area_m2(poly_shape, crs_str), 2)
            feature_area_km2 = round(feature_area_m2 / 1e6, 6)

            features.append({
                "type": "Feature",
                "geometry": geom_wgs84,
                "properties": {
                    "label": class_label,
                    "confidence": round(confidence, 3),
                    "area_km2": feature_area_km2,
                    "area_m2": feature_area_m2,
                },
            })
    else:
        # Fallback bounding box polygonization using connected components
        from scipy import ndimage
        labeled, num_features = ndimage.label(mask > 0)
        pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)

        for i in range(1, num_features + 1):
            ys, xs = np.where(labeled == i)
            if len(xs) < min_area_pixels:
                continue

            x_min, x_max = float(xs.min()), float(xs.max())
            y_min, y_max = float(ys.min()), float(ys.max())

            # Convert pixel coords to WGS84 bounds if bounds_wgs84 available
            if bounds_wgs84:
                w_wgs = bounds_wgs84["west"] + (x_min / w) * (bounds_wgs84["east"] - bounds_wgs84["west"])
                e_wgs = bounds_wgs84["west"] + (x_max / w) * (bounds_wgs84["east"] - bounds_wgs84["west"])
                n_wgs = bounds_wgs84["north"] - (y_min / h) * (bounds_wgs84["north"] - bounds_wgs84["south"])
                s_wgs = bounds_wgs84["north"] - (y_max / h) * (bounds_wgs84["north"] - bounds_wgs84["south"])
                coords = [[[w_wgs, s_wgs], [e_wgs, s_wgs], [e_wgs, n_wgs], [w_wgs, n_wgs], [w_wgs, s_wgs]]]
            else:
                # Normalized [0, 1] relative coordinates
                coords = [[[x_min / w, y_min / h], [x_max / w, y_min / h], [x_max / w, y_max / h], [x_min / w, y_max / h], [x_min / w, y_min / h]]]

            region_area_m2 = float(len(xs) * pixel_area_m2)
            region_area_km2 = float(region_area_m2 / 1_000_000.0)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coords,
                },
                "properties": {
                    "label": class_label,
                    "confidence": round(confidence, 3),
                    "area_km2": round(region_area_km2, 6),
                    "area_m2": round(region_area_m2, 2),
                    "pixel_count": int(len(xs)),
                },
            })

    return features
