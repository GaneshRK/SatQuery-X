"""Unit tests for geospatial ingestion, CRS handling, and pair validation."""

import numpy as np
from backend.geospatial.ingestion import (
    RasterMetadata,
    detect_input_mode,
    detect_sensor_type,
    parse_raster,
    pixel_bbox_to_geojson,
    validate_pair,
)


def test_detect_sensor_type():
    assert detect_sensor_type("sentinel1_sar_scene.tif", 1) == "sar"
    assert detect_sensor_type("risat_sar_band.tif", 1) == "sar"
    assert detect_sensor_type("cartosat_optical_rgb.png", 3) == "optical"
    assert detect_sensor_type("sentinel2_l2a.png", 4) == "optical"


def test_parse_plain_png(synthetic_optical_png):
    meta = parse_raster(synthetic_optical_png, "test_optical.png", "image/png")
    assert meta.width == 256
    assert meta.height == 256
    assert meta.band_count == 3
    assert meta.sensor_type == "optical"
    assert meta.geo_referenced is False


def test_detect_input_mode(synthetic_optical_png, synthetic_sar_png):
    meta_opt = parse_raster(synthetic_optical_png, "cartosat_optical.png", "image/png")
    meta_sar = parse_raster(synthetic_sar_png, "risat_sar.png", "image/png")

    assert detect_input_mode([meta_opt]) == "single_image"
    assert detect_input_mode([meta_opt, meta_sar]) == "cross_modal_pair"

    meta_opt2 = parse_raster(synthetic_optical_png, "optical_t2.png", "image/png")
    assert detect_input_mode([meta_opt, meta_opt2]) == "bi_temporal"


def test_validate_pair(synthetic_optical_png, synthetic_sar_png):
    meta_opt = parse_raster(synthetic_optical_png, "opt.png", "image/png")
    meta_sar = parse_raster(synthetic_sar_png, "sar.png", "image/png")

    result = validate_pair(meta_opt, meta_sar)
    assert result.valid is True
    assert "matching dimensions" in result.message


def test_pixel_bbox_to_geojson():
    bbox = [10.0, 20.0, 50.0, 60.0]
    geojson = pixel_bbox_to_geojson(
        bbox=bbox,
        affine=[10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0],
        crs="EPSG:32643",
        bounds_wgs84={"west": 72.5, "south": 23.0, "east": 72.6, "north": 23.1},
    )
    assert geojson["type"] == "Polygon"
    assert len(geojson["coordinates"]) == 1
    assert len(geojson["coordinates"][0]) >= 4
