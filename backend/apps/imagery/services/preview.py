"""
Satellite imagery visualization and derivative generation.

Important design rules
----------------------
1. Never fabricate satellite pixels.
2. Never fabricate geographic coordinates.
3. Never fabricate scientific measurements.
4. Browser previews are derived only from the supplied raster/image.
5. Scientific GeoTIFFs remain the source of truth.
6. Unsupported imagery must fail clearly instead of receiving a synthetic
   fallback image.
7. Change artifacts must be generated from an actual change mask produced by
   an analysis engine. This module does NOT invent change detections.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional rasterio support
# ---------------------------------------------------------------------------

try:
    import rasterio
    from rasterio.features import shapes
    from rasterio.warp import transform_bounds

    HAS_RASTERIO = True
except ImportError:
    rasterio = None
    shapes = None
    transform_bounds = None
    HAS_RASTERIO = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PREVIEW_MAX_DIM = 1024
DEFAULT_THUMBNAIL_MAX_DIM = 256

SUPPORTED_VISUAL_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _ensure_parent_directory(path: str) -> None:
    """
    Create the parent directory for an output file.
    """

    parent = os.path.dirname(
        os.path.abspath(path)
    )

    if parent:
        os.makedirs(
            parent,
            exist_ok=True,
        )


def _safe_float(
    value: Any,
) -> Optional[float]:
    """
    Convert a value to finite float.

    Returns None instead of inventing a value.
    """

    if value is None:
        return None

    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(result):
        return None

    return result


def _safe_int(
    value: Any,
) -> Optional[int]:
    """
    Convert a value to integer where possible.
    """

    if value is None:
        return None

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _contrast_stretch_band(
    band: np.ndarray,
    lower_pct: float = 2.0,
    upper_pct: float = 98.0,
) -> np.ndarray:
    """
    Convert a real raster band to an 8-bit display band.

    This is a visualization transformation only. It does not modify the
    scientific source raster.

    Invalid / nodata pixels are excluded from percentile estimation.
    """

    array = np.asarray(
        band
    )

    if array.size == 0:
        raise ValueError(
            "Raster band is empty."
        )

    numeric = array.astype(
        np.float32,
        copy=False,
    )

    valid = numeric[
        np.isfinite(numeric)
    ]

    if valid.size == 0:
        raise ValueError(
            "Raster band contains no finite pixels."
        )

    # Prefer positive values when possible for reflectance-style imagery.
    positive = valid[
        valid > 0
    ]

    if positive.size > 0:
        valid_for_percentiles = positive
    else:
        valid_for_percentiles = valid

    p_low = float(
        np.percentile(
            valid_for_percentiles,
            lower_pct,
        )
    )

    p_high = float(
        np.percentile(
            valid_for_percentiles,
            upper_pct,
        )
    )

    if not math.isfinite(
        p_low
    ) or not math.isfinite(
        p_high
    ):
        raise ValueError(
            "Unable to determine display range from raster band."
        )

    if p_high <= p_low:
        p_low = float(
            np.min(
                valid_for_percentiles
            )
        )
        p_high = float(
            np.max(
                valid_for_percentiles
            )
        )

    if p_high <= p_low:
        # Constant real imagery is still valid imagery.
        return np.full(
            numeric.shape,
            128,
            dtype=np.uint8,
        )

    stretched = (
        (
            numeric - p_low
        )
        / (
            p_high - p_low
        )
    )

    stretched = np.clip(
        stretched,
        0.0,
        1.0,
    )

    result = (
        stretched * 255.0
    ).astype(
        np.uint8
    )

    # Make non-finite values black in the display derivative.
    invalid = ~np.isfinite(
        numeric
    )

    if np.any(invalid):
        result[invalid] = 0

    return result


def _normalize_array_layout(
    array: np.ndarray,
) -> np.ndarray:
    """
    Normalize common image/raster layouts into:

        height x width x channels

    Supported:
        H x W
        H x W x C
        C x H x W
    """

    arr = np.asarray(
        array
    )

    if arr.ndim == 2:
        return arr

    if arr.ndim != 3:
        raise ValueError(
            "Expected a 2D or 3D raster array."
        )

    # Rasterio convention: C x H x W.
    if (
        arr.shape[0] <= 32
        and arr.shape[1] > 32
        and arr.shape[2] > 32
    ):
        return np.transpose(
            arr,
            (1, 2, 0),
        )

    # Image convention: H x W x C.
    return arr


def _save_display_image(
    rgb_array: np.ndarray,
    output_path: str,
    quality: int = 90,
) -> None:
    """
    Save an RGB/RGBA display array.
    """

    _ensure_parent_directory(
        output_path
    )

    arr = np.asarray(
        rgb_array
    )

    if arr.dtype != np.uint8:
        arr = np.clip(
            arr,
            0,
            255,
        ).astype(
            np.uint8
        )

    if arr.ndim != 3:
        raise ValueError(
            "Display image must have three dimensions."
        )

    if arr.shape[2] == 3:
        image = Image.fromarray(
            arr,
            mode="RGB",
        )

    elif arr.shape[2] == 4:
        image = Image.fromarray(
            arr,
            mode="RGBA",
        )

    else:
        raise ValueError(
            "Display image must contain 3 or 4 channels."
        )

    extension = (
        Path(output_path)
        .suffix
        .lower()
    )

    if extension == ".webp":
        image.save(
            output_path,
            format="WEBP",
            quality=quality,
            method=6,
        )

    elif extension in {
        ".jpg",
        ".jpeg",
    }:
        if image.mode == "RGBA":
            image = image.convert(
                "RGB"
            )

        image.save(
            output_path,
            format="JPEG",
            quality=quality,
            optimize=True,
        )

    else:
        image.save(
            output_path,
            format="PNG",
            optimize=True,
        )


def _resize_for_display(
    image: Image.Image,
    max_dim: int,
) -> Image.Image:
    """
    Resize only when necessary while preserving aspect ratio.
    """

    if max_dim <= 0:
        raise ValueError(
            "max_dim must be positive."
        )

    if max(
        image.width,
        image.height,
    ) <= max_dim:
        return image

    resized = image.copy()

    resized.thumbnail(
        (
            max_dim,
            max_dim,
        ),
        Image.Resampling.LANCZOS,
    )

    return resized


# ---------------------------------------------------------------------------
# Raster preview generation
# ---------------------------------------------------------------------------

def _select_display_bands(
    src: Any,
) -> Tuple[int, int, int, str]:
    """
    Determine which real raster bands should be displayed.

    Strategy:
        1. Use explicit band descriptions when they identify common
           Sentinel-2 B02/B03/B04 channels.
        2. For exactly three bands, use bands 1/2/3.
        3. For two-band data, produce a grayscale display from band 1.
        4. For one-band data, produce grayscale from band 1.
        5. For >3 bands without reliable descriptions, use the first three
           actual bands rather than pretending they are known RGB bands.

    Returns:
        (red_band, green_band, blue_band, mapping_description)
    """

    count = int(
        src.count
    )

    if count <= 0:
        raise ValueError(
            "Raster contains no bands."
        )

    descriptions = list(
        getattr(
            src,
            "descriptions",
            None,
        )
        or []
    )

    normalized = [
        str(description).upper()
        if description
        else ""
        for description in descriptions
    ]

    # Look for explicit Sentinel-style band labels.
    red_candidates = {
        "B04",
        "RED",
        "RED BAND",
    }

    green_candidates = {
        "B03",
        "GREEN",
        "GREEN BAND",
    }

    blue_candidates = {
        "B02",
        "BLUE",
        "BLUE BAND",
    }

    red_idx = None
    green_idx = None
    blue_idx = None

    for index, description in enumerate(
        normalized,
        start=1,
    ):
        if description in red_candidates:
            red_idx = index

        if description in green_candidates:
            green_idx = index

        if description in blue_candidates:
            blue_idx = index

    if (
        red_idx
        and green_idx
        and blue_idx
    ):
        return (
            red_idx,
            green_idx,
            blue_idx,
            (
                "Explicit band descriptions "
                "(red/green/blue)"
            ),
        )

    if count >= 3:
        return (
            1,
            2,
            3,
            (
                "First three raster bands "
                "(band semantics not explicitly identified)"
            ),
        )

    if count == 2:
        return (
            1,
            1,
            1,
            (
                "Single-band display derived from "
                "first available band of a two-band raster"
            ),
        )

    return (
        1,
        1,
        1,
        "Single-band display",
    )


def _generate_rasterio_preview(
    raster_source: str,
    max_dim: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Generate a display image from an actual raster using rasterio.

    No synthetic pixels are generated.
    """

    if not HAS_RASTERIO:
        raise RuntimeError(
            "rasterio is required to preview raster imagery."
        )

    if not os.path.isfile(
        raster_source
    ):
        raise FileNotFoundError(
            f"Raster file not found: {raster_source}"
        )

    with rasterio.open(
        raster_source
    ) as src:

        if src.width <= 0 or src.height <= 0:
            raise ValueError(
                "Raster has invalid dimensions."
            )

        red_band, green_band, blue_band, mapping = (
            _select_display_bands(
                src
            )
        )

        # Use overview/downsampling where available to avoid loading huge
        # satellite scenes into memory unnecessarily.
        scale = max(
            src.width / max_dim,
            src.height / max_dim,
            1.0,
        )

        if scale > 1:
            out_width = max(
                1,
                int(
                    round(
                        src.width / scale
                    )
                ),
            )

            out_height = max(
                1,
                int(
                    round(
                        src.height / scale
                    )
                ),
            )

            r = src.read(
                red_band,
                out_shape=(
                    out_height,
                    out_width,
                ),
                resampling=rasterio.enums.Resampling.bilinear,
            )

            g = src.read(
                green_band,
                out_shape=(
                    out_height,
                    out_width,
                ),
                resampling=rasterio.enums.Resampling.bilinear,
            )

            b = src.read(
                blue_band,
                out_shape=(
                    out_height,
                    out_width,
                ),
                resampling=rasterio.enums.Resampling.bilinear,
            )

        else:
            r = src.read(
                red_band
            )

            g = src.read(
                green_band
            )

            b = src.read(
                blue_band
            )

        r_norm = _contrast_stretch_band(
            r
        )

        g_norm = _contrast_stretch_band(
            g
        )

        b_norm = _contrast_stretch_band(
            b
        )

        rgb = np.stack(
            [
                r_norm,
                g_norm,
                b_norm,
            ],
            axis=-1,
        )

        metadata = {
            "source_type":
            "rasterio",

            "width":
            int(src.width),

            "height":
            int(src.height),

            "band_count":
            int(src.count),

            "dtype":
            str(src.dtypes[0])
            if src.dtypes
            else None,

            "crs":
            str(src.crs)
            if src.crs
            else None,

            "is_georeferenced":
            bool(
                src.crs
                and src.transform
            ),

            "band_mapping":
            mapping,

            "display_bands":
            {
                "red":
                red_band,
                "green":
                green_band,
                "blue":
                blue_band,
            },

            "nodata":
            (
                _safe_float(
                    src.nodata
                )
                if src.nodata is not None
                else None
            ),
        }

    return rgb, metadata


def _generate_pil_preview(
    raster_source: Union[
        str,
        bytes,
    ],
    max_dim: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Decode a browser-native image using Pillow.

    This is only intended for PNG/JPEG/WebP-style inputs.
    """

    if isinstance(
        raster_source,
        bytes,
    ):
        image = Image.open(
            io.BytesIO(
                raster_source
            )
        )

    elif isinstance(
        raster_source,
        str,
    ):
        if not os.path.isfile(
            raster_source
        ):
            raise FileNotFoundError(
                f"Image file not found: {raster_source}"
            )

        image = Image.open(
            raster_source
        )

    else:
        raise TypeError(
            "Pillow preview source must be a file path or bytes."
        )

    image.load()

    image = _resize_for_display(
        image,
        max_dim,
    )

    if image.mode not in {
        "RGB",
        "RGBA",
    }:
        image = image.convert(
            "RGB"
        )

    array = np.asarray(
        image
    )

    if array.ndim == 2:
        array = np.stack(
            [
                array,
                array,
                array,
            ],
            axis=-1,
        )

    metadata = {
        "source_type":
        "pillow",

        "width":
        int(image.width),

        "height":
        int(image.height),

        "band_count":
        4
        if image.mode == "RGBA"
        else 3,

        "dtype":
        str(array.dtype),

        "crs":
        None,

        "is_georeferenced":
        False,

        "band_mapping":
        "Browser-native image channels",
    }

    return array, metadata


def _generate_numpy_preview(
    raster_source: np.ndarray,
    max_dim: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Generate a display image from an actual supplied numpy raster.

    No pixels are invented.
    """

    arr = _normalize_array_layout(
        raster_source
    )

    if arr.ndim == 2:
        band = _contrast_stretch_band(
            arr
        )

        rgb = np.stack(
            [
                band,
                band,
                band,
            ],
            axis=-1,
        )

        mapping = (
            "Single-band grayscale display"
        )

    else:
        channels = arr.shape[2]

        if channels >= 3:
            r = _contrast_stretch_band(
                arr[:, :, 0]
            )

            g = _contrast_stretch_band(
                arr[:, :, 1]
            )

            b = _contrast_stretch_band(
                arr[:, :, 2]
            )

            rgb = np.stack(
                [
                    r,
                    g,
                    b,
                ],
                axis=-1,
            )

            mapping = (
                "First three supplied array channels"
            )

        elif channels == 2:
            band = _contrast_stretch_band(
                arr[:, :, 0]
            )

            rgb = np.stack(
                [
                    band,
                    band,
                    band,
                ],
                axis=-1,
            )

            mapping = (
                "First supplied channel displayed as grayscale"
            )

        else:
            band = _contrast_stretch_band(
                arr[:, :, 0]
            )

            rgb = np.stack(
                [
                    band,
                    band,
                    band,
                ],
                axis=-1,
            )

            mapping = (
                "Single supplied channel displayed as grayscale"
            )

    image = Image.fromarray(
        rgb,
        mode="RGB",
    )

    image = _resize_for_display(
        image,
        max_dim,
    )

    rgb = np.asarray(
        image
    )

    metadata = {
        "source_type":
        "numpy",

        "width":
        int(image.width),

        "height":
        int(image.height),

        "band_count":
        int(
            arr.shape[2]
        )
        if arr.ndim == 3
        else 1,

        "dtype":
        str(arr.dtype),

        "crs":
        None,

        "is_georeferenced":
        False,

        "band_mapping":
        mapping,
    }

    return rgb, metadata


# ---------------------------------------------------------------------------
# Public RGB/display preview API
# ---------------------------------------------------------------------------

def generate_rgb_preview(
    raster_source: Union[
        str,
        bytes,
        np.ndarray,
    ],
    output_preview_path: str,
    output_thumb_path: Optional[str] = None,
    max_dim: int = DEFAULT_PREVIEW_MAX_DIM,
) -> Dict[str, Any]:
    """
    Generate a browser-native preview from actual imagery.

    Parameters
    ----------
    raster_source:
        Actual raster path, image bytes, or numpy raster array.

    output_preview_path:
        Destination path for WebP/PNG/JPEG preview.

    output_thumb_path:
        Optional thumbnail path.

    max_dim:
        Maximum display dimension.

    Returns
    -------
    dict
        Metadata describing the generated derivative.

    Raises
    ------
    ValueError / RuntimeError / FileNotFoundError
        When the supplied source cannot be genuinely decoded.

    Important:
        There is deliberately NO synthetic fallback.
    """

    if max_dim <= 0:
        raise ValueError(
            "max_dim must be positive."
        )

    _ensure_parent_directory(
        output_preview_path
    )

    if output_thumb_path:
        _ensure_parent_directory(
            output_thumb_path
        )

    preview_metadata: Dict[str, Any]

    # ------------------------------------------------------------------
    # Raster file
    # ------------------------------------------------------------------

    if isinstance(
        raster_source,
        str,
    ):
        extension = (
            Path(raster_source)
            .suffix
            .lower()
        )

        if (
            HAS_RASTERIO
            and extension not in SUPPORTED_VISUAL_IMAGE_EXTENSIONS
        ):
            rgb_array, preview_metadata = (
                _generate_rasterio_preview(
                    raster_source,
                    max_dim,
                )
            )

        elif (
            extension in SUPPORTED_VISUAL_IMAGE_EXTENSIONS
        ):
            rgb_array, preview_metadata = (
                _generate_pil_preview(
                    raster_source,
                    max_dim,
                )
            )

        elif HAS_RASTERIO:
            rgb_array, preview_metadata = (
                _generate_rasterio_preview(
                    raster_source,
                    max_dim,
                )
            )

        else:
            raise RuntimeError(
                "rasterio is required to decode this raster source."
            )

    # ------------------------------------------------------------------
    # Raw browser image bytes
    # ------------------------------------------------------------------

    elif isinstance(
        raster_source,
        bytes,
    ):
        rgb_array, preview_metadata = (
            _generate_pil_preview(
                raster_source,
                max_dim,
            )
        )

    # ------------------------------------------------------------------
    # Actual numpy raster
    # ------------------------------------------------------------------

    elif isinstance(
        raster_source,
        np.ndarray,
    ):
        rgb_array, preview_metadata = (
            _generate_numpy_preview(
                raster_source,
                max_dim,
            )
        )

    else:
        raise TypeError(
            "Unsupported raster_source type."
        )

    # ------------------------------------------------------------------
    # Save main preview
    # ------------------------------------------------------------------

    _save_display_image(
        rgb_array,
        output_preview_path,
    )

    # ------------------------------------------------------------------
    # Save thumbnail
    # ------------------------------------------------------------------

    thumbnail_path = None

    if output_thumb_path:
        preview_image = Image.fromarray(
            rgb_array,
            mode="RGB",
        )

        thumbnail = _resize_for_display(
            preview_image,
            DEFAULT_THUMBNAIL_MAX_DIM,
        )

        thumbnail_array = np.asarray(
            thumbnail
        )

        _save_display_image(
            thumbnail_array,
            output_thumb_path,
            quality=85,
        )

        thumbnail_path = (
            output_thumb_path
        )

    # ------------------------------------------------------------------
    # Optional alternate format
    # ------------------------------------------------------------------

    base_path, extension = os.path.splitext(
        output_preview_path
    )

    if extension.lower() == ".webp":
        alternate_path = (
            base_path + ".png"
        )
    elif extension.lower() == ".png":
        alternate_path = (
            base_path + ".webp"
        )
    else:
        alternate_path = None

    if alternate_path:
        try:
            _save_display_image(
                rgb_array,
                alternate_path,
                quality=90,
            )
        except Exception as exc:
            logger.warning(
                "Unable to create alternate preview format: %s",
                exc,
            )

    preview_metadata.update(
        {
            "preview_path":
            output_preview_path,

            "thumbnail_path":
            thumbnail_path,

            "alternate_path":
            alternate_path,

            "preview_width":
            int(rgb_array.shape[1]),

            "preview_height":
            int(rgb_array.shape[0]),

            "generated_from_real_source":
            True,
        }
    )

    return preview_metadata


# ---------------------------------------------------------------------------
# Change artifact generation
# ---------------------------------------------------------------------------

def _require_real_change_mask(
    change_mask: Any,
) -> np.ndarray:
    """
    Validate a change mask supplied by an actual analysis engine.

    Accepted:
        2D numpy boolean/integer/float array.

    The mask must contain actual analysis output. This function deliberately
    does not create a mask.
    """

    if change_mask is None:
        raise ValueError(
            "A real change_mask is required. "
            "This service does not generate synthetic change detections."
        )

    mask = np.asarray(
        change_mask
    )

    if mask.ndim != 2:
        raise ValueError(
            "change_mask must be a 2D raster."
        )

    if mask.size == 0:
        raise ValueError(
            "change_mask is empty."
        )

    if mask.dtype == bool:
        return mask

    numeric = mask.astype(
        np.float32,
        copy=False,
    )

    finite = np.isfinite(
        numeric
    )

    if not np.any(finite):
        raise ValueError(
            "change_mask contains no finite values."
        )

    return (
        numeric > 0
    )


def _mask_to_rgba(
    mask: np.ndarray,
) -> np.ndarray:
    """
    Convert an actual binary change mask to a transparent visualization.

    The visualization color has no scientific meaning.
    """

    height, width = mask.shape

    rgba = np.zeros(
        (
            height,
            width,
            4,
        ),
        dtype=np.uint8,
    )

    # Display-only highlight.
    rgba[mask] = (
        239,
        68,
        68,
        220,
    )

    return rgba


def _write_change_geojson(
    mask: np.ndarray,
    transform: Any,
    output_path: str,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert an actual raster change mask into GeoJSON polygons.

    Polygon geometry comes directly from the supplied raster transform.
    """

    if not HAS_RASTERIO:
        raise RuntimeError(
            "rasterio is required to vectorize a change mask."
        )

    if shapes is None:
        raise RuntimeError(
            "rasterio.features.shapes is unavailable."
        )

    features = []

    mask_uint8 = (
        mask.astype(
            np.uint8
        )
    )

    for geometry, value in shapes(
        mask_uint8,
        mask=mask,
        transform=transform,
    ):
        if int(value) != 1:
            continue

        feature_properties = dict(
            properties or {}
        )

        feature_properties[
            "change_mask_value"
        ] = 1

        features.append(
            {
                "type":
                "Feature",

                "geometry":
                geometry,

                "properties":
                feature_properties,
            }
        )

    collection = {
        "type":
        "FeatureCollection",

        "features":
        features,
    }

    _ensure_parent_directory(
        output_path
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            collection,
            handle,
            indent=2,
        )

    return collection


def _calculate_change_area(
    mask: np.ndarray,
    raster_path: str,
) -> Optional[float]:
    """
    Calculate change area in square meters only when the raster CRS and
    transform support a defensible metric calculation.

    Returns None when a trustworthy metric area cannot be established.
    """

    if not HAS_RASTERIO:
        return None

    try:
        with rasterio.open(
            raster_path
        ) as src:

            if src.crs is None:
                return None

            pixel_width = abs(
                float(
                    src.transform.a
                )
            )

            pixel_height = abs(
                float(
                    src.transform.e
                )
            )

            if (
                not math.isfinite(
                    pixel_width
                )
                or not math.isfinite(
                    pixel_height
                )
                or pixel_width <= 0
                or pixel_height <= 0
            ):
                return None

            # Only treat projected metre-based CRS as direct m².
            try:
                is_projected = bool(
                    src.crs.is_projected
                )
                linear_units = getattr(
                    src.crs,
                    "linear_units",
                    None,
                )
            except Exception:
                is_projected = False
                linear_units = None

            if not is_projected:
                return None

            if linear_units not in {
                "metre",
                "meter",
                "metres",
                "meters",
            }:
                return None

            changed_pixels = int(
                np.count_nonzero(
                    mask
                )
            )

            return float(
                changed_pixels
                * pixel_width
                * pixel_height
            )

    except Exception as exc:
        logger.warning(
            "Unable to calculate change area: %s",
            exc,
        )

    return None


def generate_change_mask_artifact(
    query_id: str,
    bounds_dict: Optional[Dict[str, float]] = None,
    change_type: Optional[str] = None,
    area_km2: Optional[float] = None,
    media_root: Optional[str] = None,
    change_mask: Optional[np.ndarray] = None,
    source_raster_path: Optional[str] = None,
    source_transform: Any = None,
    source_crs: Any = None,
    evidence_properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate change artifacts from an ACTUAL change mask.

    This function intentionally refuses to generate a change result when no
    actual analysis mask is supplied.

    Parameters
    ----------
    query_id:
        Identifier used for output filenames.

    change_mask:
        Actual 2D mask produced by a change-detection model/algorithm.

    source_raster_path:
        Optional source raster used to obtain CRS, transform and metric
        information.

    source_transform:
        Transform of the raster from which change_mask was generated.

    source_crs:
        CRS of the raster from which change_mask was generated.

    bounds_dict:
        Optional real WGS84 bounds. Used only as metadata when supplied.

    change_type:
        Optional label produced by the analysis layer.

    area_km2:
        Optional measured area supplied by the analysis layer. This value is
        never invented here.

    Returns
    -------
    dict
        Paths to actual generated derivatives and evidence metadata.

    Raises
    ------
    ValueError
        If an actual change mask and trustworthy spatial reference are not
        supplied.
    """

    if not query_id:
        raise ValueError(
            "query_id is required."
        )

    mask = _require_real_change_mask(
        change_mask
    )

    if media_root is None:
        from django.conf import settings

        media_root = settings.MEDIA_ROOT

    if not media_root:
        raise ValueError(
            "MEDIA_ROOT is not configured."
        )

    results_dir = os.path.join(
        media_root,
        "results",
    )

    os.makedirs(
        results_dir,
        exist_ok=True,
    )

    # ---------------------------------------------------------------
    # Resolve actual transform / CRS.
    # ---------------------------------------------------------------

    transform = source_transform
    crs = source_crs

    if source_raster_path:
        if not HAS_RASTERIO:
            raise RuntimeError(
                "rasterio is required for source raster change artifacts."
            )

        if not os.path.isfile(
            source_raster_path
        ):
            raise FileNotFoundError(
                source_raster_path
            )

        with rasterio.open(
            source_raster_path
        ) as src:

            if transform is None:
                transform = src.transform

            if crs is None:
                crs = src.crs

            source_width = int(
                src.width
            )

            source_height = int(
                src.height
            )

        if (
            mask.shape[1] != source_width
            or mask.shape[0] != source_height
        ):
            raise ValueError(
                (
                    "Change mask dimensions do not match "
                    "the source raster dimensions."
                )
            )

    if transform is None:
        raise ValueError(
            (
                "A real raster transform is required to generate "
                "geospatial change artifacts."
            )
        )

    if crs is None:
        raise ValueError(
            (
                "A real CRS is required to generate "
                "geospatial change artifacts."
            )
        )

    # ---------------------------------------------------------------
    # Output paths
    # ---------------------------------------------------------------

    mask_png_path = os.path.join(
        results_dir,
        f"{query_id}_mask.png",
    )

    mask_webp_path = os.path.join(
        results_dir,
        f"{query_id}_mask.webp",
    )

    mask_tif_path = os.path.join(
        results_dir,
        f"{query_id}_mask.tif",
    )

    geojson_path = os.path.join(
        results_dir,
        f"{query_id}_polygons.geojson",
    )

    # ---------------------------------------------------------------
    # Visual mask
    # ---------------------------------------------------------------

    rgba = _mask_to_rgba(
        mask
    )

    mask_image = Image.fromarray(
        rgba,
        mode="RGBA",
    )

    _ensure_parent_directory(
        mask_png_path
    )

    mask_image.save(
        mask_png_path,
        format="PNG",
        optimize=True,
    )

    try:
        mask_image.save(
            mask_webp_path,
            format="WEBP",
            quality=90,
            method=6,
        )
    except Exception as exc:
        logger.warning(
            "Unable to create WebP change mask: %s",
            exc,
        )

    # ---------------------------------------------------------------
    # Scientific GeoTIFF mask
    # ---------------------------------------------------------------

    if not HAS_RASTERIO:
        raise RuntimeError(
            "rasterio is required to create a scientific change GeoTIFF."
        )

    with rasterio.open(
        mask_tif_path,
        "w",
        driver="GTiff",
        height=int(mask.shape[0]),
        width=int(mask.shape[1]),
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        compress="deflate",
        tiled=True,
    ) as dst:
        dst.write(
            mask.astype(
                np.uint8
            ),
            1,
        )

        dst.set_band_description(
            1,
            "Change mask",
        )

    # ---------------------------------------------------------------
    # GeoJSON
    # ---------------------------------------------------------------

    properties = dict(
        evidence_properties or {}
    )

    if change_type is not None:
        properties[
            "change_type"
        ] = change_type

    geojson = _write_change_geojson(
        mask,
        transform,
        geojson_path,
        properties=properties,
    )

    # ---------------------------------------------------------------
    # Actual measured area
    # ---------------------------------------------------------------

    measured_area_m2 = None
    measured_area_km2 = None

    if source_raster_path:
        measured_area_m2 = _calculate_change_area(
            mask,
            source_raster_path,
        )

        if measured_area_m2 is not None:
            measured_area_km2 = (
                measured_area_m2
                / 1_000_000.0
            )

    # If the analysis engine explicitly supplied an area, preserve it as
    # supplied evidence. Otherwise leave it absent.
    supplied_area_km2 = _safe_float(
        area_km2
    )

    evidence_chain = {
        "generated_from_real_change_mask":
        True,

        "change_mask_shape":
        [
            int(mask.shape[0]),
            int(mask.shape[1]),
        ],

        "changed_pixel_count":
        int(
            np.count_nonzero(
                mask
            )
        ),

        "source_crs":
        str(crs),

        "source_transform":
        list(transform)
        if hasattr(
            transform,
            "__iter__",
        )
        else str(transform),

        "bounds_wgs84":
        bounds_dict,

        "change_type":
        change_type,

        "supplied_area_km2":
        supplied_area_km2,

        "measured_area_m2":
        measured_area_m2,

        "measured_area_km2":
        measured_area_km2,

        "geojson_feature_count":
        len(
            geojson.get(
                "features",
                [],
            )
        ),
    }

    return {
        "mask_png_path":
        mask_png_path,

        "mask_webp_path":
        mask_webp_path,

        "mask_tif_path":
        mask_tif_path,

        "geojson_path":
        geojson_path,

        "mask_png_fname":
        os.path.basename(
            mask_png_path
        ),

        "mask_webp_fname":
        os.path.basename(
            mask_webp_path
        ),

        "mask_tif_fname":
        os.path.basename(
            mask_tif_path
        ),

        "geojson_fname":
        os.path.basename(
            geojson_path
        ),

        "evidence_chain":
        evidence_chain,

        "feature_count":
        len(
            geojson.get(
                "features",
                [],
            )
        ),

        "generated_from_real_data":
        True,
    }


# ---------------------------------------------------------------------------
# Thumbnail helper
# ---------------------------------------------------------------------------

def generate_thumbnail_image(
    data: bytes,
    max_size: int = DEFAULT_THUMBNAIL_MAX_DIM,
) -> bytes:
    """
    Generate a thumbnail from actual browser-readable image bytes.

    This function does NOT create a placeholder if decoding fails.
    """

    if not data:
        raise ValueError(
            "Image data is empty."
        )

    if max_size <= 0:
        raise ValueError(
            "max_size must be positive."
        )

    try:
        image = Image.open(
            io.BytesIO(
                data
            )
        )

        image.load()

    except Exception as exc:
        raise ValueError(
            "Unable to decode supplied image bytes."
        ) from exc

    image = _resize_for_display(
        image,
        max_size,
    )

    if image.mode not in {
        "RGB",
        "RGBA",
    }:
        image = image.convert(
            "RGB"
        )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="WEBP",
        quality=85,
        method=6,
    )

    return buffer.getvalue()