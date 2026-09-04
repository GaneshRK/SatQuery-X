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
