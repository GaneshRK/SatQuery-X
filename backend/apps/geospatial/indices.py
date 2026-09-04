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
