"""Unit tests for Sensor Profiles, optical/SAR preprocessing, and spectral indices."""

import numpy as np
import pytest

from apps.geospatial.sensor_profiles import (
    get_sensor_profile,
    preprocess_optical_raster,
    preprocess_sar_raster,
    SENTINEL_2_PROFILE,
    LANDSAT_OLI_PROFILE,
    CARTOSAT_PROFILE,
    RISAT_PROFILE,
    SENTINEL_1_PROFILE,
)
from apps.geospatial.indices import (
    compute_ndvi,
    compute_ndwi,
    compute_ndbi,
    compute_nbr,
    compute_spectral_index_from_raster,
)


def test_sensor_profile_retrieval():
    s2 = get_sensor_profile("SENTINEL-2")
    assert s2.sensor_id == "SENTINEL-2"
    assert len(s2.bands) == 13
    assert s2.get_band_index("red", 13) == 3   # B04
    assert s2.get_band_index("nir", 13) == 7   # B08
    assert s2.get_band_index("swir", 13) == 11 # B11

    landsat = get_sensor_profile("LANDSAT-OLI")
    assert landsat.sensor_id == "LANDSAT-OLI"
    assert landsat.get_band_index("red", 8) == 3  # B4
    assert landsat.get_band_index("nir", 8) == 4  # B5

    cartosat = get_sensor_profile("CARTOSAT-2S")
    assert cartosat.sensor_id == "CARTOSAT-2S"
    assert cartosat.typical_resolution_m == 0.65

    sar_s1 = get_sensor_profile("SENTINEL-1", modality="SAR")
    assert sar_s1.sensor_id == "SENTINEL-1"
    assert sar_s1.modality == "SAR"


def test_optical_preprocessing():
    # 8-bit synthetic array
    raw_8bit = np.array([[[0, 128, 255]]], dtype=np.uint8)
    norm = preprocess_optical_raster(raw_8bit)
    assert norm.max() <= 1.0
    assert norm.min() >= 0.0
    assert norm.dtype == np.float32

    # 16-bit satellite digital numbers
    raw_16bit = np.ones((10, 10, 3), dtype=np.float32) * 5000.0
    norm_16 = preprocess_optical_raster(raw_16bit)
    assert norm_16.max() <= 1.0
    assert norm_16.min() >= 0.0


def test_sar_preprocessing():
    # Synthetic SAR backscatter with speckle noise
    np.random.seed(42)
    raw_sar = np.random.exponential(scale=100.0, size=(50, 50)).astype(np.float32)
    norm_sar = preprocess_sar_raster(raw_sar, speckle_filter_size=3, apply_log_transform=True)
    assert norm_sar.shape == (50, 50)
    assert norm_sar.max() <= 1.0
    assert norm_sar.min() >= 0.0


def test_spectral_index_from_raster():
    # Create synthetic 13-band Sentinel-2 array [13, 30, 30]
    np.random.seed(123)
    bands = np.zeros((13, 30, 30), dtype=np.float32)
    bands[3] = 0.1  # Red (B04)
    bands[7] = 0.6  # NIR (B08)
    bands[11] = 0.2 # SWIR1 (B11)

    ndvi = compute_spectral_index_from_raster(bands, "NDVI", sensor_name="SENTINEL-2")
    assert ndvi.shape == (30, 30)
    expected_ndvi = (0.6 - 0.1) / (0.6 + 0.1)
    np.testing.assert_allclose(ndvi[0, 0], expected_ndvi, atol=1e-4)

    ndbi = compute_spectral_index_from_raster(bands, "NDBI", sensor_name="SENTINEL-2")
    assert ndbi.shape == (30, 30)
    expected_ndbi = (0.2 - 0.6) / (0.2 + 0.6)
    np.testing.assert_allclose(ndbi[0, 0], expected_ndbi, atol=1e-4)


def test_spectral_index_missing_bands_error():
    # 3-band RGB image lacks NIR and SWIR
    rgb = np.random.rand(3, 20, 20).astype(np.float32)
    with pytest.raises(ValueError, match="lacks required"):
        compute_spectral_index_from_raster(rgb, "NDBI", sensor_name="GENERIC-OPTICAL")
