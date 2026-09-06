"""Computer Vision & Remote Sensing deterministic feature detection engine."""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any
import numpy as np
from PIL import Image

try:
    from scipy import ndimage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from apps.geospatial.indices import compute_ndvi, compute_ndwi, compute_ndbi
from apps.geospatial.math import calculate_pixel_area_m2, calculate_polygon_ground_area_m2


@dataclass
class DetectedFeature:
    label: str
    confidence: float
    pixel_count: int
    area_m2: float
    area_km2: float
    bbox: list[int]  # [x_min, y_min, x_max, y_max]
    geojson_geometry: dict[str, Any]


def otsu_threshold(arr: np.ndarray) -> float:
    """Compute Otsu's optimal global binarization threshold on continuous spectral array."""
    valid = arr[~np.isnan(arr)]
    if len(valid) == 0:
        return 0.0
    hist, bin_edges = np.histogram(valid, bins=256, range=(-1.0, 1.0))
    hist = hist.astype(float) / hist.sum()
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]

    mean1 = np.cumsum(hist * bin_centers) / np.maximum(weight1, 1e-8)
    mean2 = (np.cumsum((hist * bin_centers)[::-1]) / np.maximum(weight2[::-1], 1e-8))[::-1]

    variance = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    idx = int(np.argmax(variance))
    return float(bin_centers[idx])


def segment_water(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> list[DetectedFeature]:
    """Segment water bodies using NDWI and adaptive thresholding."""
    h, w = rgb_or_multiband.shape[:2]
    pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)

    # Compute NDWI if multispectral, else blue/red ratio
    if rgb_or_multiband.shape[-1] >= 4:
        green = rgb_or_multiband[:, :, 1]
        nir = rgb_or_multiband[:, :, 3]
        ndwi = compute_ndwi(green, nir)
    elif rgb_or_multiband.shape[-1] >= 3:
        green = rgb_or_multiband[:, :, 1].astype(float)
        red = rgb_or_multiband[:, :, 0].astype(float)
        blue = rgb_or_multiband[:, :, 2].astype(float)
        ndwi = (blue - red) / np.maximum(blue + red, 1.0)
    else:
        ndwi = (rgb_or_multiband[:, :] < 50).astype(float)

    threshold = max(0.05, otsu_threshold(ndwi))
    binary_mask = (ndwi > threshold).astype(np.uint8)

    return _extract_features_from_binary_mask(
        binary_mask, "water_body", bounds_wgs84, pixel_area_m2, h, w, min_pixels=20
    )


def segment_vegetation(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> list[DetectedFeature]:
    """Segment dense and moderate vegetation canopies using NDVI."""
    h, w = rgb_or_multiband.shape[:2]
    pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)

    if rgb_or_multiband.shape[-1] >= 4:
        red = rgb_or_multiband[:, :, 2]
        nir = rgb_or_multiband[:, :, 3]
        ndvi = compute_ndvi(red, nir)
    elif rgb_or_multiband.shape[-1] >= 3:
        green = rgb_or_multiband[:, :, 1].astype(float)
        red = rgb_or_multiband[:, :, 0].astype(float)
        ndvi = (green - red) / np.maximum(green + red, 1.0)
    else:
        ndvi = np.zeros((h, w), dtype=float)

    binary_mask = (ndvi > 0.35).astype(np.uint8)

    return _extract_features_from_binary_mask(
        binary_mask, "dense_vegetation", bounds_wgs84, pixel_area_m2, h, w, min_pixels=30
    )


def detect_and_count_structures(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
    min_pixels: int = 15,
    max_pixels: int = 4000,
) -> tuple[int, list[DetectedFeature]]:
    """Detect and count building/infrastructure candidates using morphological high-frequency gradients."""
    h, w = rgb_or_multiband.shape[:2]
    pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)

    # Convert to grayscale
    if len(rgb_or_multiband.shape) >= 3:
        gray = np.mean(rgb_or_multiband[:, :, :3], axis=2).astype(float)
    else:
        gray = rgb_or_multiband.astype(float)

    # High frequency Sobel gradient for sharp building boundaries
    gx = ndimage.sobel(gray, axis=1)
    gy = ndimage.sobel(gray, axis=0)
    grad = np.hypot(gx, gy)

    grad_threshold = np.percentile(grad, 85)
    binary_structures = (grad > grad_threshold) & (gray > 90)

    # Morphological closing
    structure_elem = ndimage.generate_binary_structure(2, 1)
    closed = ndimage.binary_closing(binary_structures, structure=structure_elem, iterations=1)

    features = _extract_features_from_binary_mask(
        closed.astype(np.uint8),
        "structure_candidate",
        bounds_wgs84,
        pixel_area_m2,
        h,
        w,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
    )
    return len(features), features


def _extract_features_from_binary_mask(
    mask: np.ndarray,
    label: str,
    bounds_wgs84: dict[str, float] | None,
    pixel_area_m2: float,
    height: int,
    width: int,
    min_pixels: int = 15,
    max_pixels: int = 500000,
) -> list[DetectedFeature]:
    """Label connected components and construct standard WGS84 GeoJSON polygon features."""
    if not HAS_SCIPY:
        return []

    labeled, num_features = ndimage.label(mask > 0)
    results = []

    for i in range(1, min(num_features + 1, 150)):
        ys, xs = np.where(labeled == i)
        cnt = len(xs)
        if cnt < min_pixels or cnt > max_pixels:
            continue

        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())

        area_m2 = float(cnt * pixel_area_m2)
        area_km2 = float(area_m2 / 1_000_000.0)

        # Coordinate transformation
        if bounds_wgs84:
            w_wgs = bounds_wgs84["west"] + (x_min / width) * (bounds_wgs84["east"] - bounds_wgs84["west"])
            e_wgs = bounds_wgs84["west"] + (x_max / width) * (bounds_wgs84["east"] - bounds_wgs84["west"])
            n_wgs = bounds_wgs84["north"] - (y_min / height) * (bounds_wgs84["north"] - bounds_wgs84["south"])
            s_wgs = bounds_wgs84["north"] - (y_max / height) * (bounds_wgs84["north"] - bounds_wgs84["south"])
            coordinates = [[[w_wgs, s_wgs], [e_wgs, s_wgs], [e_wgs, n_wgs], [w_wgs, n_wgs], [w_wgs, s_wgs]]]
        else:
            coordinates = [[[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max], [x_min, y_min]]]

        results.append(
            DetectedFeature(
                label=label,
                confidence=round(min(0.95, 0.75 + (cnt / (cnt + 50.0)) * 0.2), 3),
                pixel_count=cnt,
                area_m2=round(area_m2, 2),
                area_km2=round(area_km2, 6),
                bbox=[x_min, y_min, x_max, y_max],
                geojson_geometry={
                    "type": "Polygon",
                    "coordinates": coordinates,
                },
            )
        )

    # Sort largest features first
    results.sort(key=lambda f: f.area_m2, reverse=True)
    return results


@dataclass
class LandCoverMetrics:
    aoi_total_area_km2: float
    valid_cloud_free_area_km2: float
    built_up_area_km2: float
    built_up_pct: float
    vegetation_area_km2: float
    vegetation_pct: float
    dense_vegetation_km2: float
    dense_vegetation_pct: float
    sparse_vegetation_km2: float
    sparse_vegetation_pct: float
    open_water_area_km2: float
    open_water_pct: float
    salt_pan_area_km2: float
    salt_pan_pct: float
    bare_soil_area_km2: float
    bare_soil_pct: float
    mean_ndvi: float
    mean_ndwi: float
    pixel_counts: dict[str, int]


def classify_land_cover(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> LandCoverMetrics:
    """
    Deterministically classifies multispectral or optical raster into mutually exclusive
    semantic land-cover classes per SIH 26167:
    - Open Surface Water (NDWI)
    - Salt Pan (Coastal evaporative basins, distinct from deep water)
    - Dense Vegetation & Canopy (High NDVI)
    - Sparse Vegetation / Agro-Scrub
    - Built-Up / Impervious Structures
    - Bare Soil / Arid Sediment
    """
    h, w = rgb_or_multiband.shape[:2]
    total_pixels = h * w
    pixel_area_m2 = calculate_pixel_area_m2(affine_list, crs_str, bounds_wgs84)
    total_area_km2 = round((total_pixels * pixel_area_m2) / 1_000_000.0, 3)

    # Spectral band extraction
    if rgb_or_multiband.ndim == 3 and rgb_or_multiband.shape[-1] >= 4:
        blue = rgb_or_multiband[:, :, 0].astype(float)
        green = rgb_or_multiband[:, :, 1].astype(float)
        red = rgb_or_multiband[:, :, 2].astype(float)
        nir = rgb_or_multiband[:, :, 3].astype(float)
        ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
        ndwi = (green - nir) / np.maximum(green + nir, 1e-6)
    elif rgb_or_multiband.ndim == 3 and rgb_or_multiband.shape[-1] >= 3:
        red = rgb_or_multiband[:, :, 0].astype(float)
        green = rgb_or_multiband[:, :, 1].astype(float)
        blue = rgb_or_multiband[:, :, 2].astype(float)
        nir = green * 1.15
        ndvi = (green - red) / np.maximum(green + red, 1.0)
        ndwi = (blue - red) / np.maximum(blue + red, 1.0)
    else:
        gray = rgb_or_multiband.astype(float) if rgb_or_multiband.ndim == 2 else rgb_or_multiband[:, :, 0].astype(float)
        red = green = blue = nir = gray
        ndvi = np.zeros((h, w), dtype=float)
        ndwi = np.zeros((h, w), dtype=float)

    whiteness = (blue + green + red) / 3.0

    # 1. Open Surface Water (Deep inland / marine water: high absorption in NIR/red, dark optical luminance)
    water_mask = (ndwi > 0.10) & (nir < 95.0) & (whiteness < 140.0)

    # 2. Salt Pan (Coastal high-reflectance evaporative flats: bright crust, shallow brine)
    # Distinctive spectral signature: high visible brightness, low NDVI, elevated coastal moisture
    is_coastal = False
    if bounds_wgs84:
        # Check proximity to coastline (e.g. Gulf of Mannar / Coromandel Coast)
        lon_c = (bounds_wgs84.get("west", 0.0) + bounds_wgs84.get("east", 0.0)) / 2.0
        lat_c = (bounds_wgs84.get("south", 0.0) + bounds_wgs84.get("north", 0.0)) / 2.0
        if (78.0 <= lon_c <= 78.4 and 8.6 <= lat_c <= 9.2) or (80.1 <= lon_c <= 80.4 and 12.8 <= lat_c <= 13.3):
            is_coastal = True

    salt_pan_mask = (whiteness >= 140.0) & (ndvi < 0.20) & (~water_mask)
    if is_coastal:
        salt_pan_mask = salt_pan_mask | ((whiteness >= 135.0) & (ndvi < 0.20) & (~water_mask))

    # 3. Dense Vegetation (High canopy cover, NDVI > 0.40)
    dense_veg_mask = (ndvi > 0.40) & (~water_mask) & (~salt_pan_mask)

    # 4. Sparse Vegetation / Agriculture (0.20 <= NDVI <= 0.40)
    sparse_veg_mask = (ndvi >= 0.20) & (ndvi <= 0.40) & (~water_mask) & (~salt_pan_mask)

    # 5. Built-up / Urban Structural Footprint
    # High edge variance + moderate reflectance or low NDVI with grey tone
    built_up_mask = (
        (ndvi < 0.20)
        & (whiteness > 85.0)
        & (whiteness < 180.0)
        & (~water_mask)
        & (~salt_pan_mask)
        & (~dense_veg_mask)
        & (~sparse_veg_mask)
    )

    # 6. Bare Soil / Sediment
    soil_mask = (~water_mask) & (~salt_pan_mask) & (~dense_veg_mask) & (~sparse_veg_mask) & (~built_up_mask)

    # Pixel counts
    cnt_water = int(np.count_nonzero(water_mask))
    cnt_salt = int(np.count_nonzero(salt_pan_mask))
    cnt_dense = int(np.count_nonzero(dense_veg_mask))
    cnt_sparse = int(np.count_nonzero(sparse_veg_mask))
    cnt_built = int(np.count_nonzero(built_up_mask))
    cnt_soil = int(np.count_nonzero(soil_mask))

    def to_km2(cnt: int) -> float:
        return round((cnt * pixel_area_m2) / 1_000_000.0, 3)

    area_water = to_km2(cnt_water)
    area_salt = to_km2(cnt_salt)
    area_dense = to_km2(cnt_dense)
    area_sparse = to_km2(cnt_sparse)
    area_veg = round(area_dense + area_sparse, 3)
    area_built = to_km2(cnt_built)
    area_soil = to_km2(cnt_soil)

    valid_area = round(area_water + area_salt + area_veg + area_built + area_soil, 3)
    valid_area_safe = max(valid_area, 0.001)

    return LandCoverMetrics(
        aoi_total_area_km2=total_area_km2,
        valid_cloud_free_area_km2=valid_area,
        built_up_area_km2=area_built,
        built_up_pct=round((area_built / valid_area_safe) * 100.0, 1),
        vegetation_area_km2=area_veg,
        vegetation_pct=round((area_veg / valid_area_safe) * 100.0, 1),
        dense_vegetation_km2=area_dense,
        dense_vegetation_pct=round((area_dense / valid_area_safe) * 100.0, 1),
        sparse_vegetation_km2=area_sparse,
        sparse_vegetation_pct=round((area_sparse / valid_area_safe) * 100.0, 1),
        open_water_area_km2=area_water,
        open_water_pct=round((area_water / valid_area_safe) * 100.0, 1),
        salt_pan_area_km2=area_salt,
        salt_pan_pct=round((area_salt / valid_area_safe) * 100.0, 1),
        bare_soil_area_km2=area_soil,
        bare_soil_pct=round((area_soil / valid_area_safe) * 100.0, 1),
        mean_ndvi=round(float(np.mean(ndvi)), 3),
        mean_ndwi=round(float(np.mean(ndwi)), 3),
        pixel_counts={
            "open_water": cnt_water,
            "salt_pan": cnt_salt,
            "dense_vegetation": cnt_dense,
            "sparse_vegetation": cnt_sparse,
            "built_up": cnt_built,
            "bare_soil": cnt_soil,
        },
    )

