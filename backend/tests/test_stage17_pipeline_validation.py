from pathlib import Path
import numpy as np


def _write(path):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", height=16, width=16, count=1,
                       dtype="float32", crs="EPSG:4326", transform=from_origin(0, 1, .01, .01)) as dst:
        dst.write(np.ones((1, 16, 16), dtype=np.float32))


def test_stage17_four_stream_contract_requires_coregistration(tmp_path):
    from apps.agent.pipeline_validation import PipelineValidationError, validate_pipeline_contract
    paths = []
    records = []
    for i, (mod, dt) in enumerate([
        ("OPTICAL", "2026-01-01T10:00:00+00:00"),
        ("SAR", "2026-01-01T11:00:00+00:00"),
        ("OPTICAL", "2026-02-01T10:00:00+00:00"),
        ("SAR", "2026-02-01T11:00:00+00:00"),
    ]):
        p = tmp_path / f"{i}.tif"; _write(p); paths.append(str(p))
        records.append({"modality": mod, "acquisition_date": dt})
    try:
        validate_pipeline_contract(records=records, paths=paths, requested_relationship="TEMPORAL_CROSS_MODAL")
    except PipelineValidationError as exc:
        assert exc.code == "COREGISTRATION_MISSING"
    else:
        raise AssertionError("Four-stream route must require coregistration")


def test_stage17_single_image_preflight_passes(tmp_path):
    from apps.agent.pipeline_validation import validate_pipeline_contract
    p = tmp_path / "image.tif"; _write(p)
    result = validate_pipeline_contract(
        records=[{"modality": "OPTICAL", "acquisition_date": "2026-01-01"}],
        paths=[str(p)], requested_relationship="SINGLE_IMAGE")
    assert result["status"] == "pending"
    assert result["route"]["route"] == "SINGLE_IMAGE"
