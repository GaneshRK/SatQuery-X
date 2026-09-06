"""
Remote-sensing spectral index calculations.

Supported:
- NDVI
- NDWI
- MNDWI
- NDBI
- NBR
"""

from __future__ import annotations

from typing import Callable

import numpy as np


EPSILON = np.finfo(np.float32).eps


def _prepare_pair(
    first: np.ndarray,
    second: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(first, dtype=np.float32)
    b = np.asarray(second, dtype=np.float32)

    if a.shape != b.shape:
        raise ValueError(
            f"Band shapes must match. Got {a.shape} and {b.shape}."
        )

    return a, b


def _normalized_difference(
    numerator_a: np.ndarray,
    numerator_b: np.ndarray,
) -> np.ndarray:
    a, b = _prepare_pair(
        numerator_a,
        numerator_b,
    )

    denominator = a + b

    result = np.divide(
        a - b,
        denominator,
        out=np.full_like(a, np.nan, dtype=np.float32),
        where=np.abs(denominator) > EPSILON,
    )

    return np.clip(
        result,
        -1.0,
        1.0,
    )


def compute_ndvi(
    red_band: np.ndarray,
    nir_band: np.ndarray,
) -> np.ndarray:
    """
    NDVI = (NIR - Red) / (NIR + Red)
    """
    return _normalized_difference(
        np.asarray(nir_band, dtype=np.float32),
        np.asarray(red_band, dtype=np.float32),
    )


def compute_ndwi(
    green_band: np.ndarray,
    nir_band: np.ndarray,
) -> np.ndarray:
    """
    McFeeters-style NDWI:
        (Green - NIR) / (Green + NIR)
    """
    return _normalized_difference(
        np.asarray(green_band, dtype=np.float32),
        np.asarray(nir_band, dtype=np.float32),
    )


def compute_mndwi(
    green_band: np.ndarray,
    swir_band: np.ndarray,
) -> np.ndarray:
    """
    Modified NDWI:
        (Green - SWIR) / (Green + SWIR)
    """
    return _normalized_difference(
        np.asarray(green_band, dtype=np.float32),
        np.asarray(swir_band, dtype=np.float32),
    )


def compute_ndbi(
    swir_band: np.ndarray,
    nir_band: np.ndarray,
) -> np.ndarray:
    """
    NDBI:
        (SWIR - NIR) / (SWIR + NIR)
    """
    return _normalized_difference(
        np.asarray(swir_band, dtype=np.float32),
        np.asarray(nir_band, dtype=np.float32),
    )


def compute_nbr(
    nir_band: np.ndarray,
    swir2_band: np.ndarray,
) -> np.ndarray:
    """
    NBR:
        (NIR - SWIR2) / (NIR + SWIR2)
    """
    return _normalized_difference(
        np.asarray(nir_band, dtype=np.float32),
        np.asarray(swir2_band, dtype=np.float32),
    )


INDEX_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "NDVI": ("red", "nir"),
    "NDWI": ("green", "nir"),
    "MNDWI": ("green", "swir"),
    "NDBI": ("swir", "nir"),
    "NBR": ("nir", "swir2"),
}


INDEX_FUNCTIONS: dict[str, Callable[..., np.ndarray]] = {
    "NDVI": compute_ndvi,
    "NDWI": compute_ndwi,
    "MNDWI": compute_mndwi,
    "NDBI": compute_ndbi,
    "NBR": compute_nbr,
}


def compute_spectral_index_from_raster(
    raster_bands: np.ndarray,
    index_name: str,
    sensor_name: str | None = None,
    modality: str = "MULTISPECTRAL",
) -> np.ndarray:
    """
    Compute a spectral index from a raster array.

    Supported input layouts:
        [bands, height, width]
        [height, width, bands]

    Band mappings come from the sensor profile.
    Unknown sensors do not receive guessed mappings.
    """

    from apps.geospatial.sensor_profiles import get_sensor_profile

    arr = np.asarray(raster_bands)

    if arr.ndim != 3:
        raise ValueError(
            "Spectral-index computation requires a 3D raster array."
        )

    profile = get_sensor_profile(
        sensor_name,
        modality,
    )

    index = index_name.strip().upper()

    if index not in INDEX_REQUIREMENTS:
        supported = ", ".join(sorted(INDEX_REQUIREMENTS))
        raise ValueError(
            f"Unsupported spectral index '{index_name}'. "
            f"Supported indices: {supported}."
        )

    required_bands = INDEX_REQUIREMENTS[index]

    # Determine layout using the known sensor profile when possible.
    #
    # For ambiguous small dimensions, prefer CHW because rasterio
    # conventionally returns [bands, height, width].
    if arr.shape[0] <= len(profile.bands) and arr.shape[1] > 32:
        chw = arr
    elif arr.shape[2] <= len(profile.bands) and arr.shape[0] > 32:
        chw = np.transpose(
            arr,
            (2, 0, 1),
        )
    elif arr.shape[0] <= 16 and arr.shape[1] > arr.shape[0]:
        chw = arr
    elif arr.shape[2] <= 16:
        chw = np.transpose(
            arr,
            (2, 0, 1),
        )
    else:
        raise ValueError(
            "Unable to determine raster band layout safely. "
            "Provide an array in [bands,H,W] or [H,W,bands] format."
        )

    band_count = chw.shape[0]

    indices: dict[str, np.ndarray] = {}

    for semantic_band in required_bands:
        band_index = profile.get_band_index(
            semantic_band,
            band_count,
        )

        if band_index is None:
            raise ValueError(
                f"Cannot compute {index}: the supplied raster does not "
                f"provide a verified '{semantic_band}' band for sensor "
                f"'{profile.sensor_id}'."
            )

        indices[semantic_band] = chw[band_index]

    if index == "NDVI":
        return compute_ndvi(
            indices["red"],
            indices["nir"],
        )

    if index == "NDWI":
        return compute_ndwi(
            indices["green"],
            indices["nir"],
        )

    if index == "MNDWI":
        return compute_mndwi(
            indices["green"],
            indices["swir"],
        )

    if index == "NDBI":
        return compute_ndbi(
            indices["swir"],
            indices["nir"],
        )

    if index == "NBR":
        return compute_nbr(
            indices["nir"],
            indices["swir2"],
        )

    raise RuntimeError(
        f"Unhandled index implementation: {index}"
    )