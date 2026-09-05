import pytest
import numpy as np
from apps.geospatial.indices import compute_ndvi, compute_ndwi, compute_ndbi, compute_nbr, compute_spectral_index_from_raster
from apps.geospatial.sensor_profiles import get_sensor_profile, SensorProfile


def test_compute_ndvi_math():
    """Verify NDVI = (NIR - Red) / (NIR + Red) within [-1, 1]."""
    # High vegetation: NIR high (0.8), Red low (0.1) -> (0.8 - 0.1) / (0.8 + 0.1) = 0.7 / 0.9 = 0.777
    red = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    nir = np.array([[0.8, 0.7], [0.6, 0.5]], dtype=np.float32)
    ndvi = compute_ndvi(red, nir)

    assert ndvi.shape == (2, 2)
    assert np.all(ndvi >= -1.0) and np.all(ndvi <= 1.0)
    expected_00 = (0.8 - 0.1) / (0.8 + 0.1)
    assert pytest.approx(float(ndvi[0, 0]), rel=1e-3) == expected_00


def test_compute_ndwi_math():
    """Verify NDWI = (Green - NIR) / (Green + NIR) within [-1, 1]."""
    # Water: Green high (0.4), NIR low (0.05) -> positive NDWI
    green = np.array([[0.4]], dtype=np.float32)
    nir = np.array([[0.05]], dtype=np.float32)
    ndwi = compute_ndwi(green, nir)
    assert float(ndwi[0, 0]) > 0.5


def test_compute_ndbi_math():
    """Verify NDBI = (SWIR - NIR) / (SWIR + NIR) within [-1, 1]."""
    swir = np.array([[0.6]], dtype=np.float32)
    nir = np.array([[0.2]], dtype=np.float32)
    ndbi = compute_ndbi(swir, nir)
    assert float(ndbi[0, 0]) > 0.0


def test_compute_nbr_math():
    """Verify NBR = (NIR - SWIR2) / (NIR + SWIR2) within [-1, 1]."""
    nir = np.array([[0.7]], dtype=np.float32)
    swir2 = np.array([[0.1]], dtype=np.float32)
    nbr = compute_nbr(nir, swir2)
    assert float(nbr[0, 0]) > 0.0


def test_spectral_index_sensor_profiles():
    """Verify SensorProfile band mapping prevents hardcoded band indices."""
    s2 = get_sensor_profile("Sentinel-2")
    assert isinstance(s2, SensorProfile)
    # In 13-band Sentinel-2 L2A: B04 (Red) is index 3, B08 (NIR) is index 7
    assert s2.get_band_index("red", 13) == 3
    assert s2.get_band_index("nir", 13) == 7

    l8 = get_sensor_profile("Landsat-8")
    assert isinstance(l8, SensorProfile)
    # In 11-band Landsat-8: B4 (Red) is index 3, B5 (NIR) is index 4
    assert l8.get_band_index("red", 11) == 3
    assert l8.get_band_index("nir", 11) == 4


def test_spectral_index_missing_bands_error():
    """Verify compute_spectral_index_from_raster raises error when bands are missing."""
    # 2-band raster cannot compute SWIR-based indices like NDBI
    arr = np.zeros((2, 64, 64), dtype=np.float32)
    with pytest.raises(ValueError) as exc:
        compute_spectral_index_from_raster(arr, "NDBI", sensor_name="Sentinel-2")
    assert "lacks required SWIR" in str(exc.value)
