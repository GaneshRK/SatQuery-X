from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from apps.agent.integration_pipeline import run_integrated_pipeline
from apps.agent.modality_router import resolve_analysis_route
from apps.geospatial.temporal_coregistration import prepare_temporal_optical_sar
from apps.satellite.providers.base import SatelliteCandidateDTO, SatelliteProviderRequestError
from apps.satellite.providers.boundary import SatelliteProviderBoundary


class FakeProvider:
    slug = "TEST_EXTERNAL_BOUNDARY"
    name = "Injected provider test double"

    def __init__(self, fail=False):
        self.fail = fail

    def search_scenes(self, **kwargs):
        if self.fail:
            raise SatelliteProviderRequestError("simulated provider outage")
        return [
            SatelliteCandidateDTO(
                stac_item_id="T1-O", collection="test", sensor="OPTICAL",
                acquisition_date="2026-01-01T10:00:00Z", cloud_cover_pct=1,
                footprint_geom={}, provider=self.slug, is_synthetic=True,
            ),
            SatelliteCandidateDTO(
                stac_item_id="T1-S", collection="test", sensor="SENTINEL-1",
                acquisition_date="2026-01-01T11:00:00Z", cloud_cover_pct=0,
                footprint_geom={}, provider=self.slug, is_synthetic=True,
            ),
            SatelliteCandidateDTO(
                stac_item_id="T2-O", collection="test", sensor="OPTICAL",
                acquisition_date="2026-02-01T10:00:00Z", cloud_cover_pct=1,
                footprint_geom={}, provider=self.slug, is_synthetic=True,
            ),
            SatelliteCandidateDTO(
                stac_item_id="T2-S", collection="test", sensor="SENTINEL-1",
                acquisition_date="2026-02-01T11:00:00Z", cloud_cover_pct=0,
                footprint_geom={}, provider=self.slug, is_synthetic=True,
            ),
        ]


def _raster(path: Path, value: float, *, crs="EPSG:4326"):
    transform = from_origin(0, 10, 1, 1)
    with rasterio.open(path, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32", crs=crs, transform=transform) as dst:
        dst.write(np.full((10, 10), value, dtype=np.float32), 1)


def test_provider_failure_is_structured():
    result = SatelliteProviderBoundary(FakeProvider(fail=True), test_double=True).call("search", FakeProvider(fail=True).search_scenes)
    assert result.status == "failed"
    assert result.error_code == "PROVIDER_REQUEST_FAILED"
    assert result.test_double is True


def test_full_pipeline_with_injected_provider_and_real_coregistration(tmp_path):
    provider = FakeProvider()
    files = []
    for i, name in enumerate(("o1.tif", "s1.tif", "o2.tif", "s2.tif")):
        p = tmp_path / name
        _raster(p, i + 1)
        files.append(str(p))

    def acquire(candidates):
        records = [
            {"modality": "optical", "acquisition_date": "2026-01-01T10:00:00Z"},
            {"modality": "sar", "acquisition_date": "2026-01-01T11:00:00Z"},
            {"modality": "optical", "acquisition_date": "2026-02-01T10:00:00Z"},
            {"modality": "sar", "acquisition_date": "2026-02-01T11:00:00Z"},
        ]
        return {"status": "downloaded", "records": records, "paths": files}

    def infer(payload):
        assert payload["routing"]["route"] == "BI_TEMPORAL_OPTICAL_SAR"
        assert payload["coregistration"]["stream_order"] == ["optical_t1", "sar_t1", "optical_t2", "sar_t2"]
        return {"status": "ok", "answer": "change detected", "confidence": None}

    def evidence(model, payload):
        return {"status": "ok", "evidence": {"model_answer": model["answer"], "route": payload["routing"]["route"]}}

    def provenance(evidence):
        return {"status": "verified", "valid": True}

    result = run_integrated_pipeline(
        provider=provider,
        search_kwargs={"aoi_geometry": {"type": "Polygon", "coordinates": []}, "date_start": "2026-01-01", "date_end": "2026-02-01"},
        acquire=acquire,
        route=resolve_analysis_route,
        prepare=lambda r, p: prepare_temporal_optical_sar(r, p, output_root=str(tmp_path)),
        infer=infer,
        build_evidence=evidence,
        verify_provenance=provenance,
        requested_relationship="TEMPORAL_CROSS_MODAL",
        test_double=True,
    )
    assert result["status"] == "passed"
    assert result["provider"]["test_double"] is True
    assert result["provenance"]["valid"] is True
