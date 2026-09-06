"""
Deterministic computer-vision and remote-sensing feature engine.

This module provides evidence-producing algorithms.

Important:
- It does not claim that heuristic detections are ground truth.
- Confidence is only returned when an algorithm provides a measurable
  score.
- Ground coordinates are returned only when valid geospatial metadata exists.
- No synthetic coordinates are created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from apps.geospatial.indices import (
    compute_ndvi,
    compute_ndwi,
    compute_ndbi,
)
from apps.geospatial.math import (
    calculate_pixel_area_m2,
    polygonize_mask_to_geojson,
)


try:
    from scipy import ndimage

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class DetectedFeature:
    label: str
    confidence: float | None
    pixel_count: int

    area_m2: float | None
    area_km2: float | None

    bbox: list[int]

    geojson_geometry: dict[str, Any] | None

    properties: dict[str, Any] | None = None


def otsu_threshold(
    arr: np.ndarray,
) -> float:
    """
    Compute Otsu threshold over finite values.

    The histogram range is derived from the actual data rather than
    assuming a fixed physical index range.
    """

    values = np.asarray(
        arr,
        dtype=np.float32,
    )

    valid = values[
        np.isfinite(values)
    ]

    if valid.size == 0:
        return 0.0

    minimum = float(
        np.min(valid)
    )

    maximum = float(
        np.max(valid)
    )

    if minimum == maximum:
        return minimum

    histogram, edges = np.histogram(
        valid,
        bins=256,
        range=(minimum, maximum),
    )

    histogram = histogram.astype(
        np.float64
    )

    probability = (
        histogram
        / max(
            histogram.sum(),
            1.0,
        )
    )

    centers = (
        edges[:-1]
        + edges[1:]
    ) / 2.0

    cumulative_weight = np.cumsum(
        probability
    )

    cumulative_mean = np.cumsum(
        probability
        * centers
    )

    total_mean = cumulative_mean[-1]

    denominator = (
        cumulative_weight
        * (
            1.0
            - cumulative_weight
        )
    )

    between_variance = np.divide(
        (
            total_mean
            * cumulative_weight
            - cumulative_mean
        )
        ** 2,
        denominator,
        out=np.zeros_like(
            denominator
        ),
        where=denominator > 0,
    )

    return float(
        centers[
            int(
                np.argmax(
                    between_variance
                )
            )
        ]
    )


def _validate_image_array(
    raster: np.ndarray,
) -> np.ndarray:
    arr = np.asarray(
        raster
    )

    if arr.ndim not in {
        2,
        3,
    }:
        raise ValueError(
            "Raster must be 2D or 3D."
        )

    return arr.astype(
        np.float32,
        copy=False,
    )


def _to_hwc(
    raster: np.ndarray,
) -> np.ndarray:
    arr = _validate_image_array(
        raster
    )

    if arr.ndim == 2:
        return arr[:, :, None]

    if arr.shape[0] <= 16 and arr.shape[1] > 16:
        return np.transpose(
            arr,
            (1, 2, 0),
        )

    if arr.shape[2] <= 16:
        return arr

    raise ValueError(
        "Unable to safely infer raster layout."
    )


def _calculate_component_area(
    pixel_count: int,
    pixel_area_m2: float | None,
) -> tuple[float | None, float | None]:

    if pixel_area_m2 is None:
        return None, None

    area_m2 = (
        pixel_count
        * pixel_area_m2
    )

    return (
        float(area_m2),
        float(
            area_m2 / 1_000_000.0
        ),
    )


def _component_features(
    mask: np.ndarray,
    label: str,
    bounds_wgs84: dict[str, float] | None,
    affine_list: list[float] | None,
    crs_str: str | None,
    min_pixels: int = 15,
    max_pixels: int = 500_000,
) -> list[DetectedFeature]:

    if not HAS_SCIPY:
        raise RuntimeError(
            "scipy is required for connected-component detection."
        )

    if mask.ndim != 2:
        raise ValueError(
            "Mask must be 2D."
        )

    try:
        pixel_area = calculate_pixel_area_m2(
            affine_list,
            crs_str,
            bounds_wgs84,
        )
    except ValueError:
        pixel_area = None

    labeled, count = ndimage.label(
        mask.astype(bool)
    )

    objects = ndimage.find_objects(
        labeled
    )

    results: list[DetectedFeature] = []

    for component_id, component_slice in enumerate(
        objects,
        start=1,
    ):

        if component_slice is None:
            continue

        ys, xs = np.where(
            labeled[
                component_slice
            ]
            == component_id
        )

        pixel_count = int(
            len(xs)
        )

        if (
            pixel_count < min_pixels
            or pixel_count > max_pixels
        ):
            continue

        y0 = component_slice[0].start
        x0 = component_slice[1].start

        x_min = int(
            xs.min() + x0
        )
        x_max = int(
            xs.max() + x0
        )

        y_min = int(
            ys.min() + y0
        )
        y_max = int(
            ys.max() + y0
        )

        area_m2, area_km2 = (
            _calculate_component_area(
                pixel_count,
                pixel_area,
            )
        )

        geometry = None

        # Only generate geographic geometry when the source has valid
        # geospatial metadata.
        if affine_list and crs_str:
            try:
                component_mask = (
                    labeled
                    == component_id
                )

                geojson_features = polygonize_mask_to_geojson(
                    component_mask,
                    affine_list,
                    crs_str,
                    bounds_wgs84,
                    class_label=label,
                    confidence=None,
                    min_area_pixels=min_pixels,
                )

                if geojson_features:
                    geometry = geojson_features[0][
                        "geometry"
                    ]

            except Exception:
                geometry = None

        results.append(
            DetectedFeature(
                label=label,
                confidence=None,
                pixel_count=pixel_count,
                area_m2=area_m2,
                area_km2=area_km2,
                bbox=[
                    x_min,
                    y_min,
                    x_max,
                    y_max,
                ],
                geojson_geometry=geometry,
                properties={
                    "detection_type": "heuristic",
                    "georeferenced": bool(
                        geometry
                    ),
                },
            )
        )

    results.sort(
        key=lambda feature: (
            feature.area_m2
            if feature.area_m2 is not None
            else feature.pixel_count
        ),
        reverse=True,
    )

    return results


def segment_water(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> list[DetectedFeature]:
    """
    Water screening using NDWI when verified green/NIR bands are available.

    For RGB-only imagery, a spectral NDWI claim is not made.
    """

    hwc = _to_hwc(
        rgb_or_multiband
    )

    bands = hwc.shape[2]

    if bands < 4:
        raise ValueError(
            "Water segmentation requires verified multispectral "
            "Green and NIR bands. RGB-only imagery is insufficient "
            "for this NDWI-based detector."
        )

    green = hwc[:, :, 1]
    nir = hwc[:, :, 3]

    ndwi = compute_ndwi(
        green,
        nir,
    )

    valid = ndwi[
        np.isfinite(ndwi)
    ]

    if valid.size == 0:
        return []

    threshold = otsu_threshold(
        valid
    )

    mask = (
        ndwi > threshold
    )

    return _component_features(
        mask,
        "water_body_candidate",
        bounds_wgs84,
        affine_list,
        crs_str,
        min_pixels=20,
    )


def segment_vegetation(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> list[DetectedFeature]:
    """
    Vegetation screening using NDVI.

    Requires verified Red and NIR bands.
    """

    hwc = _to_hwc(
        rgb_or_multiband
    )

    if hwc.shape[2] < 4:
        raise ValueError(
            "Vegetation segmentation requires verified Red and NIR "
            "bands. RGB-only imagery is insufficient for NDVI."
        )

    red = hwc[:, :, 2]
    nir = hwc[:, :, 3]

    ndvi = compute_ndvi(
        red,
        nir,
    )

    valid = ndvi[
        np.isfinite(ndvi)
    ]

    if valid.size == 0:
        return []

    threshold = otsu_threshold(
        valid
    )

    mask = (
        ndvi > threshold
    )

    return _component_features(
        mask,
        "vegetation_candidate",
        bounds_wgs84,
        affine_list,
        crs_str,
        min_pixels=30,
    )


def detect_and_count_structures(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
    min_pixels: int = 15,
    max_pixels: int = 4000,
) -> tuple[int, list[DetectedFeature]]:
    """
    Detect high-gradient image structures.

    IMPORTANT:
    This is a candidate detector, not a building classifier.
    Results must be described as image-structure candidates unless
    validated by a trained object-detection model.
    """

    if not HAS_SCIPY:
        raise RuntimeError(
            "scipy is required for structure detection."
        )

    hwc = _to_hwc(
        rgb_or_multiband
    )

    gray = np.mean(
        hwc[:, :, : min(3, hwc.shape[2])],
        axis=2,
    )

    gray = np.nan_to_num(
        gray,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    gradient_x = ndimage.sobel(
        gray,
        axis=1,
    )

    gradient_y = ndimage.sobel(
        gray,
        axis=0,
    )

    gradient = np.hypot(
        gradient_x,
        gradient_y,
    )

    finite_gradient = gradient[
        np.isfinite(gradient)
    ]

    if finite_gradient.size == 0:
        return 0, []

    threshold = np.percentile(
        finite_gradient,
        90.0,
    )

    candidates = (
        gradient >= threshold
    )

    candidates = ndimage.binary_closing(
        candidates,
        structure=ndimage.generate_binary_structure(
            2,
            1,
        ),
        iterations=1,
    )

    features = _component_features(
        candidates,
        "structure_candidate",
        bounds_wgs84,
        affine_list,
        crs_str,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
    )

    return len(features), features


@dataclass
class LandCoverMetrics:
    aoi_total_area_km2: float | None
    valid_cloud_free_area_km2: float | None

    built_up_area_km2: float | None
    built_up_pct: float | None

    vegetation_area_km2: float | None
    vegetation_pct: float | None

    dense_vegetation_km2: float | None
    dense_vegetation_pct: float | None

    sparse_vegetation_km2: float | None
    sparse_vegetation_pct: float | None

    open_water_area_km2: float | None
    open_water_pct: float | None

    salt_pan_area_km2: float | None
    salt_pan_pct: float | None

    bare_soil_area_km2: float | None
    bare_soil_pct: float | None

    mean_ndvi: float | None
    mean_ndwi: float | None

    pixel_counts: dict[str, int]

    warnings: list[str]


def classify_land_cover(
    rgb_or_multiband: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs_str: str | None = None,
) -> LandCoverMetrics:
    """
    Conservative land-cover screening.

    This is not a trained land-cover classifier.

    The function refuses to produce physical area values when spatial
    metadata is unavailable.
    """

    hwc = _to_hwc(
        rgb_or_multiband
    )

    height, width, bands = hwc.shape

    total_pixels = (
        height
        * width
    )

    warnings: list[str] = []

    try:
        pixel_area = calculate_pixel_area_m2(
            affine_list,
            crs_str,
            bounds_wgs84,
        )
    except ValueError:
        pixel_area = None
        warnings.append(
            "Ground area unavailable because valid CRS/geotransform "
            "metadata was not provided."
        )

    total_area_km2 = (
        total_pixels
        * pixel_area
        / 1_000_000.0
        if pixel_area is not None
        else None
    )

    ndvi = None
    ndwi = None

    if bands >= 4:
        red = hwc[:, :, 2]
        nir = hwc[:, :, 3]
        green = hwc[:, :, 1]

        ndvi = compute_ndvi(
            red,
            nir,
        )

        ndwi = compute_ndwi(
            green,
            nir,
        )
    else:
        warnings.append(
            "Verified multispectral Red/NIR bands are unavailable; "
            "NDVI-based vegetation analysis is not produced."
        )

    if ndvi is not None:
        vegetation_mask = (
            np.isfinite(ndvi)
            & (ndvi > 0.3)
        )

        dense_mask = (
            np.isfinite(ndvi)
            & (ndvi > 0.5)
        )

        sparse_mask = (
            np.isfinite(ndvi)
            & (ndvi > 0.1)
            & (ndvi <= 0.3)
        )
    else:
        vegetation_mask = np.zeros(
            (height, width),
            dtype=bool,
        )

        dense_mask = vegetation_mask.copy()
        sparse_mask = vegetation_mask.copy()

    if ndwi is not None:
        water_mask = (
            np.isfinite(ndwi)
            & (ndwi > 0.2)
        )
    else:
        water_mask = np.zeros(
            (height, width),
            dtype=bool,
        )

    # These classes are intentionally labeled as heuristic candidates.
    #
    # They are not treated as certified land-cover classes.
    non_vegetated = (
        ~water_mask
        & ~vegetation_mask
    )

    built_mask = np.zeros(
        (height, width),
        dtype=bool,
    )

    bare_mask = non_vegetated.copy()

    if bands >= 3:
        visible = np.mean(
            hwc[:, :, :3],
            axis=2,
        )

        visible_normalized = (
            _normalize_visible(
                visible
            )
        )

        built_mask = (
            non_vegetated
            & (visible_normalized > 0.25)
            & (visible_normalized < 0.80)
        )

        bare_mask = (
            non_vegetated
            & ~built_mask
        )

    counts = {
        "open_water": int(
            np.count_nonzero(
                water_mask
            )
        ),
        "dense_vegetation": int(
            np.count_nonzero(
                dense_mask
            )
        ),
        "sparse_vegetation": int(
            np.count_nonzero(
                sparse_mask
            )
        ),
        "vegetation": int(
            np.count_nonzero(
                vegetation_mask
            )
        ),
        "built_up_candidate": int(
            np.count_nonzero(
                built_mask
            )
        ),
        "bare_soil_candidate": int(
            np.count_nonzero(
                bare_mask
            )
        ),
    }

    def area_km2(
        count: int,
    ) -> float | None:
        if pixel_area is None:
            return None

        return round(
            count
            * pixel_area
            / 1_000_000.0,
            6,
        )

    def percentage(
        count: int,
    ) -> float | None:
        if total_pixels == 0:
            return None

        return round(
            count
            / total_pixels
            * 100.0,
            4,
        )

    mean_ndvi = (
        float(
            np.nanmean(
                ndvi
            )
        )
        if ndvi is not None
        and np.isfinite(ndvi).any()
        else None
    )

    mean_ndwi = (
        float(
            np.nanmean(
                ndwi
            )
        )
        if ndwi is not None
        and np.isfinite(ndwi).any()
        else None
    )

    vegetation_count = counts[
        "vegetation"
    ]

    dense_count = counts[
        "dense_vegetation"
    ]

    sparse_count = counts[
        "sparse_vegetation"
    ]

    water_count = counts[
        "open_water"
    ]

    built_count = counts[
        "built_up_candidate"
    ]

    bare_count = counts[
        "bare_soil_candidate"
    ]

    return LandCoverMetrics(
        aoi_total_area_km2=(
            round(
                total_area_km2,
                6,
            )
            if total_area_km2 is not None
            else None
        ),
        valid_cloud_free_area_km2=(
            round(
                total_area_km2,
                6,
            )
            if total_area_km2 is not None
            else None
        ),
        built_up_area_km2=area_km2(
            built_count
        ),
        built_up_pct=percentage(
            built_count
        ),
        vegetation_area_km2=area_km2(
            vegetation_count
        ),
        vegetation_pct=percentage(
            vegetation_count
        ),
        dense_vegetation_km2=area_km2(
            dense_count
        ),
        dense_vegetation_pct=percentage(
            dense_count
        ),
        sparse_vegetation_km2=area_km2(
            sparse_count
        ),
        sparse_vegetation_pct=percentage(
            sparse_count
        ),
        open_water_area_km2=area_km2(
            water_count
        ),
        open_water_pct=percentage(
            water_count
        ),
        salt_pan_area_km2=None,
        salt_pan_pct=None,
        bare_soil_area_km2=area_km2(
            bare_count
        ),
        bare_soil_pct=percentage(
            bare_count
        ),
        mean_ndvi=(
            round(
                mean_ndvi,
                5,
            )
            if mean_ndvi is not None
            else None
        ),
        mean_ndwi=(
            round(
                mean_ndwi,
                5,
            )
            if mean_ndwi is not None
            else None
        ),
        pixel_counts=counts,
        warnings=warnings,
    )


def _normalize_visible(
    values: np.ndarray,
) -> np.ndarray:
    finite = values[
        np.isfinite(values)
    ]

    if finite.size == 0:
        return np.zeros_like(
            values,
            dtype=np.float32,
        )

    low, high = np.percentile(
        finite,
        (
            2.0,
            98.0,
        ),
    )

    if high <= low:
        return np.zeros_like(
            values,
            dtype=np.float32,
        )

    return np.clip(
        (
            values
            - low
        )
        / (
            high
            - low
        ),
        0.0,
        1.0,
    )