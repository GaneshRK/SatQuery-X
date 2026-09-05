import pytest
from apps.agent.query_optimizer import QueryOptimizer
from apps.agent.georeason import GeoReasonAgent


def test_coimbatore_does_not_contain_chennai():
    """Verify Coimbatore query resolves Coimbatore AOI and never bleeds Chennai context."""
    optimizer = QueryOptimizer()
    plan = optimizer.optimize("What is changing around Coimbatore?", session_context={})

    assert plan.aoi["name"] == "Coimbatore Industrial Basin"
    bbox = plan.aoi["bbox"]
    # Coimbatore bbox is around [76.90, 10.95, 77.05, 11.08]
    assert 76.8 < bbox[0] < 77.0
    assert 10.8 < bbox[1] < 11.1
    # Must NOT be Chennai coords (80.2, 13.0)
    assert bbox[0] < 78.0

    agent = GeoReasonAgent()
    res = agent.synthesize(
        query_text="What is changing around Coimbatore?",
        aoi_name=plan.aoi["name"],
        satellite_scenes=[],
        measurements={},
        change_events=[],
        external_evidence=[],
        aoi_coords=plan.aoi.get("coords"),
    )
    assert "Chennai" not in res.synthesized_answer
    assert "Coimbatore" in res.synthesized_answer


def test_chennai_does_not_contain_coimbatore():
    """Verify Chennai query resolves Chennai Metropolitan Region without Coimbatore pollution."""
    optimizer = QueryOptimizer()
    plan = optimizer.optimize("What is changing around Chennai?", session_context={})

    assert plan.aoi["name"] == "Chennai Metropolitan Region"
    bbox = plan.aoi["bbox"]
    # Chennai bbox is around [80.15, 12.95, 80.35, 13.15]
    assert 80.0 < bbox[0] < 80.4
    assert 12.8 < bbox[1] < 13.3

    agent = GeoReasonAgent()
    res = agent.synthesize(
        query_text="What is changing around Chennai?",
        aoi_name=plan.aoi["name"],
        satellite_scenes=[],
        measurements={},
        change_events=[],
        external_evidence=[],
        aoi_coords=plan.aoi.get("coords"),
    )
    assert "Coimbatore" not in res.synthesized_answer
    assert "Chennai" in res.synthesized_answer
