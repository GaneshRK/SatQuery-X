import os
import tempfile
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from apps.geospatial.raster_engine import RasterEngine


@pytest.fixture
def sample_4band_geotiff():
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        path = tmp.name

    width, height = 128, 128
    transform = from_bounds(93.0, 26.5, 93.2, 26.7, width, height)
    crs = "EPSG:4326"

    # Blue, Green, Red, NIR
    blue = np.full((height, width), 1000, dtype=np.uint16)
    green = np.full((height, width), 1200, dtype=np.uint16)
    red = np.full((height, width), 1100, dtype=np.uint16)
    nir = np.full((height, width), 3500, dtype=np.uint16)
    data = np.stack([blue, green, red, nir])

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=4,
        dtype=np.uint16,
        crs=crs,
        transform=transform,
    ) as dst:
        for i in range(4):
            dst.write(data[i], i + 1)

    yield path

    if os.path.exists(path):
        os.remove(path)


def test_raster_engine_inspect(sample_4band_geotiff):
    meta = RasterEngine.inspect(sample_4band_geotiff)
    assert meta["width"] == 128
    assert meta["height"] == 128
    assert meta["band_count"] == 4
    assert "4326" in str(meta["crs"])
    assert meta["bounds"]["west"] == 93.0


def test_raster_engine_validation(sample_4band_geotiff):
    valid, msg = RasterEngine.validate_raster(sample_4band_geotiff)
    assert valid is True
    assert "valid" in msg.lower()

    valid_fake, msg_fake = RasterEngine.validate_raster("non_existent_file.tif")
    assert valid_fake is False


def test_raster_engine_windowed_read(sample_4band_geotiff):
    chunk = RasterEngine.read_window(sample_4band_geotiff, col_off=10, row_off=10, width=32, height=32)
    assert chunk.shape == (4, 32, 32)


def test_raster_engine_indices(sample_4band_geotiff):
    ndvi_res = RasterEngine.compute_index(sample_4band_geotiff, "NDVI")
    assert ndvi_res["index"] == "NDVI"
    assert ndvi_res["mean"] > 0.4  # (3500 - 1100)/(3500 + 1100) = 2400 / 4600 ~= 0.52
    assert ndvi_res["valid_pct"] > 90.0

    ndwi_res = RasterEngine.compute_index(sample_4band_geotiff, "NDWI")
    assert ndwi_res["index"] == "NDWI"
    assert ndwi_res["mean"] < 0.0  # (1200 - 3500)/(1200 + 3500) < 0

    savi_res = RasterEngine.compute_index(sample_4band_geotiff, "SAVI")
    assert savi_res["index"] == "SAVI"


def test_raster_engine_tile_rendering(sample_4band_geotiff):
    # Tile around 26.6 Lat, 93.1 Lon at zoom 10
    png_bytes = RasterEngine.render_tile_png(sample_4band_geotiff, z=10, x=776, y=458, layer="rgb")
    assert len(png_bytes) > 50
    assert png_bytes.startswith(b"\x89PNG")
