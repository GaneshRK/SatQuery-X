"""Spectral indices calculations for remote sensing (NDVI, NDWI, NDBI)."""

from __future__ import annotations

import numpy as np


def compute_ndvi(red_band: np.ndarray, nir_band: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)."""
    red = red_band.astype(np.float32)
    nir = nir_band.astype(np.float32)
    denominator = nir + red
    # Avoid zero division
    denominator[denominator == 0] = 1e-6
    ndvi = (nir - red) / denominator
    return np.clip(ndvi, -1.0, 1.0)


def compute_ndwi(green_band: np.ndarray, nir_band: np.ndarray) -> np.ndarray:
    """Normalized Difference Water Index: (Green - NIR) / (Green + NIR)."""
    green = green_band.astype(np.float32)
    nir = nir_band.astype(np.float32)
    denominator = green + nir
    denominator[denominator == 0] = 1e-6
    ndwi = (green - nir) / denominator
    return np.clip(ndwi, -1.0, 1.0)


def compute_ndbi(swir_band: np.ndarray, nir_band: np.ndarray) -> np.ndarray:
    """Normalized Difference Built-up Index: (SWIR - NIR) / (SWIR + NIR)."""
    swir = swir_band.astype(np.float32)
    nir = nir_band.astype(np.float32)
    denominator = swir + nir
    denominator[denominator == 0] = 1e-6
    ndbi = (swir - nir) / denominator
    return np.clip(ndbi, -1.0, 1.0)


def compute_nbr(nir_band: np.ndarray, swir2_band: np.ndarray) -> np.ndarray:
    """Normalized Burn Ratio: (NIR - SWIR2) / (NIR + SWIR2)."""
    nir = nir_band.astype(np.float32)
    swir2 = swir2_band.astype(np.float32)
    denominator = nir + swir2
    denominator[denominator == 0] = 1e-6
    nbr = (nir - swir2) / denominator
    return np.clip(nbr, -1.0, 1.0)


def compute_spectral_index_from_raster(
    raster_bands: np.ndarray,
    index_name: str,
    sensor_name: str | None = None,
    modality: str = "MULTISPECTRAL",
) -> np.ndarray:
    """
    Computes a spectral index (NDVI, NDWI, NDBI, NBR) from a multi-band raster array (shape: [C, H, W] or [H, W, C]),
    resolving the exact spectral bands via SensorProfile band mapping.
    Raises ValueError if required bands are missing.
    """
    from apps.geospatial.sensor_profiles import get_sensor_profile

    profile = get_sensor_profile(sensor_name, modality)

    # Ensure shape is [C, H, W]
    arr = raster_bands
    if arr.ndim == 2:
        # Single band: cannot compute multi-spectral indices
        raise ValueError(f"Single-band raster cannot compute multi-spectral index '{index_name}'. At least 2 bands required.")
    if arr.ndim == 3 and arr.shape[2] in (1, 2, 3, 4, 8, 12, 13) and arr.shape[0] > 16:
        # Format is [H, W, C] -> transpose to [C, H, W]
        arr = np.transpose(arr, (2, 0, 1))

    total_bands = arr.shape[0]
    idx_upper = index_name.upper().strip()

    if idx_upper == "NDVI":
        red_idx = profile.get_band_index("red", total_bands)
        nir_idx = profile.get_band_index("nir", total_bands)
        if red_idx is None or nir_idx is None:
            # Fallback for 3-band RGB: assume band 0 is Red, band 1 is Green (NDVI cannot be properly calculated without NIR)
            raise ValueError(f"Sensor '{profile.name}' with {total_bands} bands lacks required Red and NIR bands for NDVI.")
        return compute_ndvi(arr[red_idx], arr[nir_idx])

    elif idx_upper == "NDWI":
        green_idx = profile.get_band_index("green", total_bands)
        nir_idx = profile.get_band_index("nir", total_bands)
        if green_idx is None or nir_idx is None:
            raise ValueError(f"Sensor '{profile.name}' with {total_bands} bands lacks required Green and NIR bands for NDWI.")
        return compute_ndwi(arr[green_idx], arr[nir_idx])

    elif idx_upper == "NDBI":
        swir_idx = profile.get_band_index("swir", total_bands)
        nir_idx = profile.get_band_index("nir", total_bands)
        if swir_idx is None or nir_idx is None:
            raise ValueError(f"Sensor '{profile.name}' with {total_bands} bands lacks required SWIR and NIR bands for NDBI.")
        return compute_ndbi(arr[swir_idx], arr[nir_idx])

    elif idx_upper == "NBR":
        nir_idx = profile.get_band_index("nir", total_bands)
        swir2_idx = profile.get_band_index("swir2", total_bands)
        if nir_idx is None or swir2_idx is None:
            raise ValueError(f"Sensor '{profile.name}' with {total_bands} bands lacks required NIR and SWIR2 bands for NBR.")
        return compute_nbr(arr[nir_idx], arr[swir2_idx])

    raise ValueError(f"Unsupported spectral index '{index_name}'. Supported: NDVI, NDWI, NDBI, NBR.")


