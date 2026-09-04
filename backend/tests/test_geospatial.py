import numpy as np
import pytest

from apps.geospatial.indices import compute_ndbi, compute_ndvi, compute_ndwi
from apps.geospatial.ingestion import detect_sensor_and_modality
from apps.geospatial.math import calculate_pixel_area_m2, polygonize_mask_to_geojson, quantify_mask_area


def test_sensor_and_modality_detection():
    sensor, mod = detect_sensor_and_modality("S2A_MSIL2A_20260815.tif", 12)
    assert sensor == "SENTINEL-2"
    assert mod == "MULTISPECTRAL"

    sensor, mod = detect_sensor_and_modality("S1A_IW_GRDH_1SDV.tif", 1)
    assert sensor == "SENTINEL-1"
    assert mod == "SAR"

    sensor, mod = detect_sensor_and_modality("Cartosat2S_optical.tif", 4)
    assert sensor == "CARTOSAT-2S"
    assert mod == "OPTICAL"


def test_projection_aware_area_calculation():
    # Projected CRS: 10m x 10m pixel = 100 m²
    affine_utm = [10.0, 0.0, 500000.0, 0.0, -10.0, 4000000.0]
    area_m2 = calculate_pixel_area_m2(affine_utm, "EPSG:32643")
    assert abs(area_m2 - 100.0) < 1e-4

    # Binary mask of 100 pixels
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[5:15, 5:15] = 255  # 10x10 = 100 pixels

    quant = quantify_mask_area(mask, affine_utm, "EPSG:32643")
    assert quant["valid_pixel_count"] == 100
    assert quant["area_m2"] == 10000.0  # 100 * 100m² = 10,000 m²
    assert quant["area_ha"] == 1.0       # 1 hectare
    assert quant["area_km2"] == 0.01     # 0.01 km²


def test_spectral_indices():
    red = np.array([[0.1, 0.2], [0.3, 0.4]])
    nir = np.array([[0.5, 0.6], [0.7, 0.8]])
    ndvi = compute_ndvi(red, nir)
    assert ndvi.shape == (2, 2)
    assert (ndvi > 0).all()

    green = np.array([[0.4, 0.5], [0.2, 0.3]])
    ndwi = compute_ndwi(green, nir)
    assert ndwi.shape == (2, 2)


def test_polygonization_to_geojson():
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:30, 10:30] = 255
    affine = [10.0, 0.0, 1000.0, 0.0, -10.0, 5000.0]

    features = polygonize_mask_to_geojson(mask, affine, "EPSG:32643", class_label="change")
    assert len(features) > 0
    assert features[0]["type"] == "Feature"
    assert features[0]["properties"]["label"] == "change"
    assert "area_km2" in features[0]["properties"]
