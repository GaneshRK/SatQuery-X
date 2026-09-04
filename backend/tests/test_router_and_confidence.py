import pytest
from apps.ai_providers.base import AIRequest
from apps.ai_providers.router import ModelRouter
from apps.agent.confidence import ConfidenceEngine


def test_model_router_fallback():
    router = ModelRouter()
    req = AIRequest(task="REASONING", prompt="Analyze vegetation in the agricultural parcel")
    resp = router.route(req)
    assert resp.status == "ok"
    assert resp.provider in ("local", "openai")
    assert resp.confidence > 0.70
    assert len(resp.text) > 10


def test_confidence_engine_scoring():
    # Ideal image
    ideal = ConfidenceEngine.evaluate_raster_quality(
        cloud_cover_pct=2.0,
        resolution_m=10.0,
        nodata_pct=0.0,
        crs="EPSG:4326",
        band_count=4,
    )
    assert ideal.data_quality_score >= 95.0
    assert ideal.confidence_level == "HIGH"
    assert len(ideal.uncertainty_reasons) == 0

    # Degraded image with high cloud cover and coarse resolution
    degraded = ConfidenceEngine.evaluate_raster_quality(
        cloud_cover_pct=35.0,
        resolution_m=30.0,
        nodata_pct=5.0,
        crs="EPSG:4326",
        band_count=2,
    )
    assert degraded.data_quality_score < 75.0
    assert degraded.confidence_level in ("MEDIUM", "LOW")
    assert len(degraded.uncertainty_reasons) >= 2


def test_calibrated_confidence():
    metrics = ConfidenceEngine.evaluate_raster_quality(cloud_cover_pct=20.0, resolution_m=10.0)
    calibrated = ConfidenceEngine.calibrate_answer_confidence(0.90, metrics)
    assert 0.50 <= calibrated <= 0.95
