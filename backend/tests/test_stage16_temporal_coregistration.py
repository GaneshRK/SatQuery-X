from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _write(path, *, crs="EPSG:4326", transform=None, value=1.0):
    import rasterio
    from rasterio.transform import from_origin
    if transform is None:
        transform = from_origin(0, 1, 0.01, 0.01)
    profile = {
        "driver": "GTiff", "height": 100, "width": 100, "count": 1,
        "dtype": "float32", "crs": crs, "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.full((1, 100, 100), value, dtype=np.float32))


def test_temporal_coregistration_pairs_and_aligns(tmp_path):
    from apps.geospatial.temporal_coregistration import prepare_temporal_optical_sar

    paths = []
    records = []
    specs = [
        ("o1.tif", "OPTICAL", "2026-01-01T10:00:00+00:00"),
        ("s1.tif", "SAR", "2026-01-01T12:00:00+00:00"),
        ("o2.tif", "OPTICAL", "2026-02-01T10:00:00+00:00"),
        ("s2.tif", "SAR", "2026-02-01T13:00:00+00:00"),
    ]
    for name, modality, dt in specs:
        path = tmp_path / name
        _write(path, value=2.0 if modality == "SAR" else 1.0)
        paths.append(str(path))
        records.append({"modality": modality, "acquisition_date": dt})

    result = prepare_temporal_optical_sar(records, paths, max_pair_delta_hours=6, output_root=str(tmp_path / "derived"))
    assert result["status"] == "completed"
    assert result["stream_order"] == ["optical_t1", "sar_t1", "optical_t2", "sar_t2"]
    assert len(result["pairs"]) == 2
    assert all(Path(p).is_file() for p in result["ordered_paths"][1::2])


def test_temporal_coregistration_rejects_unknown_modality(tmp_path):
    from apps.geospatial.temporal_coregistration import prepare_temporal_optical_sar
    p = tmp_path / "x.tif"
    _write(p)
    records = [{"modality": "UNKNOWN", "acquisition_date": "2026-01-01"}] * 4
    paths = [str(p)] * 4
    try:
        prepare_temporal_optical_sar(records, paths, output_root=str(tmp_path / "d"))
    except ValueError as exc:
        assert "unknown modality" in str(exc).lower()
    else:
        raise AssertionError("Unknown modality must be rejected")
