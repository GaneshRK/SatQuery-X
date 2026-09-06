"""
Remote-sensing preprocessing and artifact-quality assessment.

The preprocessing layer is intentionally conservative.

Optical:
- cloud screening
- shadow screening
- optional haze correction

SAR:
- speckle filtering

Important:
Thermal/SAR signal is never classified as "noise" merely because it is
unusual. Scientific preprocessing must respect modality and product metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ArtifactQualityReport:
    cloud_cover_pct: float | None
    shadow_cover_pct: float | None

    haze_detected: bool
    sar_speckle_reduced: bool

    usable_clear_data_pct: float | None

    cleaning_methods_applied: list[str] = field(
        default_factory=list
    )

    scene_cloud_cover_pct: float | None = None
    aoi_cloud_cover_pct: float | None = None

    haze_pct: float | None = None
    nodata_pct: float | None = None

    valid_pixels_count: int = 0
    total_pixels_count: int = 0

    warnings: list[str] = field(
        default_factory=list
    )

    metrics: dict[str, Any] = field(
        default_factory=dict
    )


def _to_hwc(
    raster: np.ndarray,
) -> np.ndarray:
    """
    Convert raster to HWC layout.

    For preprocessing this function only accepts arrays where one dimension
    is plausibly a small band dimension.
    """

    arr = np.asarray(raster)

    if arr.ndim == 2:
        return arr[:, :, None]

    if arr.ndim != 3:
        raise ValueError(
            "Raster must be 2D or 3D."
        )

    if arr.shape[0] <= 16 and arr.shape[1] > 16:
        return np.transpose(
            arr,
            (1, 2, 0),
        )

    if arr.shape[2] <= 16:
        return arr

    raise ValueError(
        "Unable to safely determine raster band layout."
    )


def _normalize_for_screening(
    raster: np.ndarray,
) -> np.ndarray:
    """
    Normalize only for artifact screening.

    This does not modify the scientific raster.
    """

    arr = np.asarray(
        raster,
        dtype=np.float32,
    )

    finite = arr[
        np.isfinite(arr)
    ]

    if finite.size == 0:
        return np.zeros_like(
            arr,
            dtype=np.float32,
        )

    low = float(
        np.percentile(
            finite,
            1.0,
        )
    )

    high = float(
        np.percentile(
            finite,
            99.0,
        )
    )

    if high <= low:
        return np.zeros_like(
            arr,
            dtype=np.float32,
        )

    return np.clip(
        (arr - low) / (high - low),
        0.0,
        1.0,
    )


def detect_clouds(
    raster: np.ndarray,
    sensor: str | None = None,
    brightness_threshold: float = 0.75,
) -> np.ndarray:
    """
    Conservative optical cloud screening.

    This is a heuristic screening method, not a replacement for a
    sensor-specific cloud-probability product.

    Returns:
        Boolean array [height,width].
    """

    if brightness_threshold <= 0:
        raise ValueError(
            "brightness_threshold must be positive."
        )

    hwc = _to_hwc(
        raster
    )

    normalized = _normalize_for_screening(
        hwc
    )

    height, width, bands = normalized.shape

    if bands >= 3:
        blue = normalized[:, :, 0]
        green = normalized[:, :, 1]
        red = normalized[:, :, 2]

        brightness = (
            blue
            + green
            + red
        ) / 3.0

        chromaticity = np.maximum.reduce(
            [
                blue,
                green,
                red,
            ]
        ) - np.minimum.reduce(
            [
                blue,
                green,
                red,
            ]
        )

        return (
            (brightness >= brightness_threshold)
            & (chromaticity <= 0.20)
        )

    if bands == 1:
        return (
            normalized[:, :, 0]
            >= brightness_threshold
        )

    return np.zeros(
        (height, width),
        dtype=bool,
    )


def detect_cloud_shadows(
    raster: np.ndarray,
    cloud_mask: np.ndarray,
    shadow_threshold: float = 0.12,
) -> np.ndarray:
    """
    Screen likely dark optical shadow regions.

    This does not claim that every dark pixel is a cloud shadow.
    """

    hwc = _to_hwc(
        raster
    )

    normalized = _normalize_for_screening(
        hwc
    )

    if cloud_mask.shape != normalized.shape[:2]:
        raise ValueError(
            "cloud_mask shape does not match raster."
        )

    if normalized.shape[2] >= 3:
        luminance = np.mean(
            normalized[:, :, :3],
            axis=2,
        )
    else:
        luminance = normalized[:, :, 0]

    shadow = (
        luminance <= shadow_threshold
    ) & (~cloud_mask)

    return shadow.astype(bool)


def reduce_haze_dos(
    raster: np.ndarray,
    dark_percentile: float = 1.0,
    correction_fraction: float = 1.0,
) -> tuple[np.ndarray, bool]:
    """
    Dark Object Subtraction-style correction.

    This function returns the corrected array and whether a non-zero
    dark-object offset was detected.

    It should be applied only when the input is compatible with this
    type of optical correction.
    """

    if not 0 <= dark_percentile <= 100:
        raise ValueError(
            "dark_percentile must be between 0 and 100."
        )

    if not 0 <= correction_fraction <= 1:
        raise ValueError(
            "correction_fraction must be between 0 and 1."
        )

    arr = np.asarray(
        raster,
        dtype=np.float32,
    ).copy()

    if arr.ndim not in {
        2,
        3,
    }:
        raise ValueError(
            "Raster must be 2D or 3D."
        )

    detected = False

    if arr.ndim == 2:
        valid = arr[
            np.isfinite(arr)
            & (arr > 0)
        ]

        if valid.size == 0:
            return arr, False

        dark_value = float(
            np.percentile(
                valid,
                dark_percentile,
            )
        )

        if dark_value > 0:
            detected = True
            arr = np.maximum(
                0.0,
                arr
                - (
                    dark_value
                    * correction_fraction
                ),
            )

        return arr, detected

    # CHW assumed for scientific raster arrays.
    for band_index in range(
        arr.shape[0]
    ):
        band = arr[
            band_index
        ]

        valid = band[
            np.isfinite(band)
            & (band > 0)
        ]

        if valid.size == 0:
            continue

        dark_value = float(
            np.percentile(
                valid,
                dark_percentile,
            )
        )

        if dark_value > 0:
            detected = True

            arr[
                band_index
            ] = np.maximum(
                0.0,
                band
                - (
                    dark_value
                    * correction_fraction
                ),
            )

    return arr, detected


def apply_lee_filter(
    sar_image: np.ndarray,
    window_size: int = 5,
) -> np.ndarray:
    """
    Lee-style local-statistics speckle reduction.

    The function preserves the input numeric domain and does not clip
    the result to [0,255].
    """

    if window_size < 3:
        raise ValueError(
            "window_size must be >= 3."
        )

    if window_size % 2 == 0:
        raise ValueError(
            "window_size must be odd."
        )

    try:
        from scipy import ndimage
    except ImportError as exc:
        raise RuntimeError(
            "scipy is required for Lee filtering."
        ) from exc

    arr = np.asarray(
        sar_image,
        dtype=np.float32,
    )

    if arr.ndim != 2:
        raise ValueError(
            "apply_lee_filter expects a single 2D SAR band."
        )

    if not np.isfinite(arr).any():
        return arr.copy()

    local_mean = ndimage.uniform_filter(
        arr,
        size=window_size,
        mode="reflect",
    )

    local_sq_mean = ndimage.uniform_filter(
        arr * arr,
        size=window_size,
        mode="reflect",
    )

    local_variance = np.maximum(
        local_sq_mean
        - local_mean * local_mean,
        0.0,
    )

    global_variance = float(
        np.nanvar(arr)
    )

    if global_variance <= 0:
        return arr.copy()

    noise_variance = min(
        global_variance,
        float(
            np.nanmedian(
                local_variance
            )
        ),
    )

    weight = np.maximum(
        local_variance - noise_variance,
        0.0,
    ) / np.maximum(
        local_variance,
        np.finfo(np.float32).eps,
    )

    weight = np.clip(
        weight,
        0.0,
        1.0,
    )

    result = (
        local_mean
        + weight
        * (
            arr
            - local_mean
        )
    )

    return result.astype(
        np.float32
    )


def _nodata_mask(
    raster: np.ndarray,
) -> np.ndarray:
    """
    Detect pixels where all channels are exactly zero.

    Actual nodata masks from raster metadata should be preferred when
    available.
    """

    arr = np.asarray(
        raster
    )

    if arr.ndim == 2:
        return arr == 0

    hwc = _to_hwc(
        arr
    )

    return np.all(
        hwc == 0,
        axis=2,
    )


def clean_satellite_imagery(
    raster: np.ndarray,
    sensor: str | None = None,
    modality: str = "OPTICAL",
    scene_cloud_cover_pct: float | None = None,
    apply_haze_correction: bool = False,
    sar_speckle_filter_size: int = 5,
) -> tuple[np.ndarray, ArtifactQualityReport]:
    """
    Master preprocessing entry point.

    The function reports actual detected percentages rather than fabricated
    values.
    """

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

    modality_upper = (
        modality or ""
    ).strip().upper()

    methods: list[str] = []
    warnings: list[str] = []

    hwc = _to_hwc(
        arr
    )

    total_pixels = int(
        hwc.shape[0]
        * hwc.shape[1]
    )

    nodata = _nodata_mask(
        arr
    )

    nodata_count = int(
        np.count_nonzero(
            nodata
        )
    )

    nodata_pct = (
        nodata_count
        / total_pixels
        * 100.0
        if total_pixels
        else None
    )

    # ------------------------------------------------------------------
    # SAR
    # ------------------------------------------------------------------

    if modality_upper == "SAR":
        from scipy import ndimage

        if arr.ndim == 2:
            cleaned = apply_lee_filter(
                arr,
                window_size=sar_speckle_filter_size,
            )

        else:
            # Convert to CHW if needed.
            if arr.shape[0] <= 16 and arr.shape[1] > 16:
                chw = arr.copy()
            else:
                chw = np.transpose(
                    arr,
                    (2, 0, 1),
                ).copy()

            for index in range(
                chw.shape[0]
            ):
                chw[index] = apply_lee_filter(
                    chw[index],
                    window_size=sar_speckle_filter_size,
                )

            cleaned = (
                chw
                if arr.shape[0] <= 16
                and arr.shape[1] > 16
                else np.transpose(
                    chw,
                    (1, 2, 0),
                )
            )

        methods.append(
            "SAR speckle reduction"
        )

        valid_count = int(
            total_pixels
            - nodata_count
        )

        usable_pct = (
            valid_count
            / total_pixels
            * 100.0
            if total_pixels
            else None
        )

        report = ArtifactQualityReport(
            cloud_cover_pct=None,
            shadow_cover_pct=None,
            haze_detected=False,
            sar_speckle_reduced=True,
            usable_clear_data_pct=usable_pct,
            cleaning_methods_applied=methods,
            scene_cloud_cover_pct=scene_cloud_cover_pct,
            aoi_cloud_cover_pct=None,
            haze_pct=None,
            nodata_pct=round(
                nodata_pct,
                4,
            )
            if nodata_pct is not None
            else None,
            valid_pixels_count=valid_count,
            total_pixels_count=total_pixels,
            warnings=warnings,
            metrics={
                "modality": "SAR",
                "nodata_pixels": nodata_count,
            },
        )

        return cleaned, report

    # ------------------------------------------------------------------
    # Optical / multispectral
    # ------------------------------------------------------------------

    if modality_upper not in {
        "OPTICAL",
        "MULTISPECTRAL",
    }:
        warnings.append(
            f"No modality-specific preprocessing pipeline exists "
            f"for '{modality}'."
        )

        report = ArtifactQualityReport(
            cloud_cover_pct=None,
            shadow_cover_pct=None,
            haze_detected=False,
            sar_speckle_reduced=False,
            usable_clear_data_pct=None,
            cleaning_methods_applied=[],
            scene_cloud_cover_pct=scene_cloud_cover_pct,
            nodata_pct=(
                round(
                    nodata_pct,
                    4,
                )
                if nodata_pct is not None
                else None
            ),
            valid_pixels_count=(
                total_pixels
                - nodata_count
            ),
            total_pixels_count=total_pixels,
            warnings=warnings,
        )

        return arr.copy(), report

    cloud_mask = detect_clouds(
        arr,
        sensor=sensor,
    )

    shadow_mask = detect_cloud_shadows(
        arr,
        cloud_mask,
    )

    cloud_count = int(
        np.count_nonzero(
            cloud_mask
        )
    )

    shadow_count = int(
        np.count_nonzero(
            shadow_mask
        )
    )

    cloud_pct = (
        cloud_count
        / total_pixels
        * 100.0
        if total_pixels
        else None
    )

    shadow_pct = (
        shadow_count
        / total_pixels
        * 100.0
        if total_pixels
        else None
    )

    cleaned = arr.copy()

    if cloud_count:
        methods.append(
            "Optical cloud screening"
        )

    if shadow_count:
        methods.append(
            "Optical shadow screening"
        )

    haze_detected = False
    haze_pct = None

    if apply_haze_correction:
        cleaned, haze_detected = reduce_haze_dos(
            cleaned
        )

        if haze_detected:
            methods.append(
                "Dark Object Subtraction haze correction"
            )

        # Haze percentage is intentionally not fabricated.
        haze_pct = None

    contaminated = (
        cloud_mask
        | shadow_mask
        | nodata
    )

    valid_count = int(
        total_pixels
        - np.count_nonzero(
            contaminated
        )
    )

    usable_pct = (
        valid_count
        / total_pixels
        * 100.0
        if total_pixels
        else None
    )

    if scene_cloud_cover_pct is not None:
        if not 0 <= scene_cloud_cover_pct <= 100:
            warnings.append(
                "Provided scene cloud percentage is outside 0-100."
            )

    report = ArtifactQualityReport(
        cloud_cover_pct=(
            round(
                cloud_pct,
                4,
            )
            if cloud_pct is not None
            else None
        ),
        shadow_cover_pct=(
            round(
                shadow_pct,
                4,
            )
            if shadow_pct is not None
            else None
        ),
        haze_detected=haze_detected,
        sar_speckle_reduced=False,
        usable_clear_data_pct=(
            round(
                usable_pct,
                4,
            )
            if usable_pct is not None
            else None
        ),
        cleaning_methods_applied=methods,
        scene_cloud_cover_pct=scene_cloud_cover_pct,
        aoi_cloud_cover_pct=(
            round(
                cloud_pct,
                4,
            )
            if cloud_pct is not None
            else None
        ),
        haze_pct=haze_pct,
        nodata_pct=(
            round(
                nodata_pct,
                4,
            )
            if nodata_pct is not None
            else None
        ),
        valid_pixels_count=valid_count,
        total_pixels_count=total_pixels,
        warnings=warnings,
        metrics={
            "modality": modality_upper,
            "cloud_pixels": cloud_count,
            "shadow_pixels": shadow_count,
            "nodata_pixels": nodata_count,
        },
    )

    return cleaned, report