from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

from apps.geospatial.coregistration import align_to_reference, grids_are_aligned


def _write(path: Path, crs: str, transform, value: float):
    with rasterio.open(path, "w", driver="GTiff", width=8, height=8, count=1,
                       dtype="float32", crs=crs, transform=transform) as dst:
        dst.write(np.full((8, 8), value, dtype="float32"), 1)


def test_alignment_reprojects_to_reference_grid():
    with tempfile.TemporaryDirectory() as d:
        ref = Path(d) / "optical.tif"
        sar = Path(d) / "sar.tif"
        _write(ref, "EPSG:4326", from_origin(10, 20, 0.01, 0.01), 1)
        _write(sar, "EPSG:4326", from_origin(10, 20, 0.02, 0.02), 2)
        arr, meta = align_to_reference(str(sar), str(ref))
        assert arr.shape == (1, 8, 8)
        assert meta["coregistered"] is True


def test_missing_crs_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        ref = Path(d) / "optical.tif"
        sar = Path(d) / "sar.tif"
        _write(ref, "EPSG:4326", from_origin(10, 20, 0.01, 0.01), 1)
        with rasterio.open(sar, "w", driver="GTiff", width=8, height=8, count=1, dtype="float32",
                           transform=from_origin(10, 20, 0.01, 0.01)) as dst:
            dst.write(np.ones((8, 8), dtype="float32"), 1)
        with pytest.raises(ValueError):
            align_to_reference(str(sar), str(ref))
