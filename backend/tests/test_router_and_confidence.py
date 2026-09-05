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


def test_slm_query_router():
    from apps.agent.router_slm import router_slm

    # Test single-image VQA query
    plan_vqa = router_slm.route_query("Is there water in this image?")
    assert plan_vqa.required_images == 1
    assert "vqa" in plan_vqa.tools_sequence or "detect_water" in plan_vqa.tools_sequence

    # Test bi-temporal change detection query
    plan_cd = router_slm.route_query(
        "Has the built-up area increased between these two dates?",
        session_context={"image_count": 2, "pair_type": "BI_TEMPORAL"},
    )
    assert plan_cd.required_images == 2
    assert plan_cd.requires_change_detection is True
    assert "change_detection" in plan_cd.tools_sequence
    assert plan_cd.requires_area_estimation is True

    # Test Optical+SAR multimodal query
    plan_fusion = router_slm.route_query(
        "Use optical and SAR radar imagery to identify structures",
        session_context={"image_count": 2, "pair_type": "CROSS_MODAL"},
    )
    assert plan_fusion.required_images == 2
    assert "optical_sar_fusion" in plan_fusion.tools_sequence


def test_model_disagreement_detection():
    # Model A says water present, Model B says no water
    res_a = {"detected": True, "count": 3}
    res_b = {"detected": False, "count": 0}

    eval_result = ConfidenceEngine.evaluate_model_disagreement(res_a, res_b, target_class="water")
    assert eval_result["status"] == "DISAGREEMENT"
    assert eval_result["confidence_level"] == "LOW"
    assert "conflicting model evidence" in eval_result["message"].lower()

    # Concordant models
    concordant = ConfidenceEngine.evaluate_model_disagreement(res_a, res_a, target_class="water")
    assert concordant["status"] == "AGREEMENT"
    assert concordant["confidence_level"] == "HIGH"

