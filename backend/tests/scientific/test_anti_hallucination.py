import pytest
from apps.agent.georeason import GeoReasonAgent


def test_no_change_detected_honest_narrative():
    """Verify system emits honest 'none above threshold' narrative instead of 'stable landcover'."""
    agent = GeoReasonAgent()
    result = agent.synthesize(
        query_text="What is changing around Coimbatore?",
        aoi_name="Coimbatore Industrial Basin",
        satellite_scenes=[
            {"platform": "Sentinel-2", "external_id": "S2_COIMBATORE_2023", "cloud_cover": 4.2},
            {"platform": "Sentinel-2", "external_id": "S2_COIMBATORE_2024", "cloud_cover": 3.8},
        ],
        measurements={},
        change_events=[],  # Zero change detected
        external_evidence=[],
    )

    # Narrative must not contain the banned generic text
    assert "stable landcover distribution with nominal seasonal" not in result.synthesized_answer
    # Narrative must explicitly state no change exceeding threshold
    assert "none above threshold" in result.synthesized_answer.lower() or "detected no surface reflectance transitions" in result.synthesized_answer.lower()


def test_dynamic_confidence_calculation():
    """Verify confidence is dynamically calibrated and includes machine-readable factors."""
    agent = GeoReasonAgent()

    # Low cloud, dual overpass
    res_high = agent.synthesize(
        query_text="Assess vegetation health",
        aoi_name="Pollachi",
        satellite_scenes=[
            {"platform": "Sentinel-2", "external_id": "S2_1", "cloud_cover": 1.5},
            {"platform": "Sentinel-2", "external_id": "S2_2", "cloud_cover": 2.0},
        ],
        measurements={"ndvi_mean": 0.68},
        change_events=[],
        external_evidence=[],
    )

    # High cloud, single overpass
    res_low = agent.synthesize(
        query_text="Assess vegetation health",
        aoi_name="Pollachi",
        satellite_scenes=[
            {"platform": "Sentinel-2", "external_id": "S2_CLOUDY", "cloud_cover": 65.0},
        ],
        measurements={},
        change_events=[],
        external_evidence=[],
    )

    # High quality scenes must produce higher confidence than cloudy single scenes
    assert res_high.calibrated_confidence > res_low.calibrated_confidence
    assert res_high.calibrated_confidence != 0.82  # Must not be static 0.82!

    # Machine-readable factors must exist
    factors = res_high.confidence_factors
    assert len(factors) == 4
    factor_names = {f["name"] for f in factors}
    assert "cloud_quality" in factor_names
    assert "spatial_registration" in factor_names
    assert "model_agreement" in factor_names
    assert "evidence_coverage" in factor_names
