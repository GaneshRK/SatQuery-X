import pytest
from datetime import datetime
from apps.agent.query_optimizer import QueryOptimizer
from apps.agent.georeason import GeoReasonAgent
from apps.agent.followup_generator import FollowUpGenerator
from apps.agent.web_research import ExternalEvidenceDTO


def test_query_optimizer_flood_query():
    optimizer = QueryOptimizer()
    query = "Quantify flood water extent in Chennai between 2020 and 2023"
    plan = optimizer.optimize(query)

    assert "water" in plan.target or "water" in plan.intent or "flood" in plan.intent
    assert "chennai" in plan.aoi.get("name", "").lower()

    # Temporal scope verification
    assert "2020" in plan.time_range.get("start_date", "")
    assert "2023" in plan.time_range.get("end_date", "")

    # Analysis operations must include water masking or SAR thresholding
    assert len(plan.analysis) > 0
    assert any("water" in a or "masking" in a or "thresholding" in a or "sar" in a or "change" in a for a in plan.analysis)

    # External evidence flag is enabled for flood/disaster queries
    assert plan.external_evidence_required is True


def test_query_optimizer_relative_temporal_resolution():
    optimizer = QueryOptimizer()
    current_year = datetime.utcnow().year

    # "over the last 5 years"
    plan = optimizer.optimize("How has vegetation canopy changed in Kaziranga over the last 5 years?")
    assert str(current_year - 5) in plan.time_range.get("start_date", "")

    # "since 2018"
    plan2 = optimizer.optimize("Urban expansion in Pollachi since 2018")
    assert "2018-01-01" in plan2.time_range.get("start_date", "")


def test_query_optimizer_vegetation_query():
    optimizer = QueryOptimizer()
    plan = optimizer.optimize("Assess coconut canopy vigor and NDVI health in Pollachi")

    assert plan.target == "vegetation"
    assert "pollachi" in plan.aoi.get("name", "").lower()
    assert any("spectral" in a or "ndvi" in a or "canopy" in a for a in plan.analysis)


def test_georeason_agent_narrative_and_confidence():
    agent = GeoReasonAgent()

    satellite_scenes = [
        {
            "platform": "Sentinel-2",
            "external_id": "S2A_MSIL2A_20201115",
            "acquisition_date": "2020-11-15",
            "cloud_cover": 4.5,
        },
        {
            "platform": "Sentinel-2",
            "external_id": "S2B_MSIL2A_20231205",
            "acquisition_date": "2023-12-05",
            "cloud_cover": 6.2,
        },
    ]
    measurements = {
        "changed_area_km2": 42.5,
        "changed_area_hectares": 4250.0,
        "change_percentage": 28.4,
    }
    change_events = [
        {
            "change_type": "SURFACE_WATER_EXPANSION",
            "area_hectares": 4250.0,
        }
    ]
    external_evidence = [
        ExternalEvidenceDTO(
            source_url="https://tnsdma.tn.gov.in/bulletin/2023",
            source_domain="tnsdma.tn.gov.in",
            publisher="Tamil Nadu State Disaster Management Authority (TNSDMA)",
            title="Chennai Flood Inundation Assessment",
            trust_tier="TIER_1_GOV_AGENCY",
            trust_score=0.95,
            summary_facts=["Severe cyclone Michaung induced 4000+ ha inundation along Ennore and Adyar drainage basins."],
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            retrieved_at=datetime.utcnow().isoformat(),
            ttl_expires_at=(datetime.utcnow()).isoformat(),
        )
    ]

    result = agent.synthesize(
        query_text="What caused the flood extent in Chennai during Dec 2023?",
        aoi_name="Chennai Metropolitan Region",
        satellite_scenes=satellite_scenes,
        measurements=measurements,
        change_events=change_events,
        external_evidence=external_evidence,
    )

    assert result.synthesized_answer is not None
    assert len(result.synthesized_answer) > 50
    assert "Chennai" in result.synthesized_answer

    # Calibrated confidence should be high due to 2 overpasses + Tier 1 external corroboration
    assert result.calibrated_confidence >= 0.85
    assert result.calibrated_confidence <= 0.99
    assert result.confidence_level == "HIGH"

    # Check evidence graph nodes and edges
    assert len(result.evidence_graph["nodes"]) >= 3
    assert len(result.evidence_graph["edges"]) >= 2

    # Citations must be populated
    assert len(result.external_citations) == 1
    assert result.external_citations[0]["publisher"] == "Tamil Nadu State Disaster Management Authority (TNSDMA)"


def test_georeason_confidence_penalizes_high_cloud():
    agent = GeoReasonAgent()

    satellite_scenes = [
        {
            "platform": "Sentinel-2",
            "external_id": "S2A_MSIL2A_CLOUDY",
            "acquisition_date": "2023-07-10",
            "cloud_cover": 75.0,  # High cloud
        }
    ]

    result = agent.synthesize(
        query_text="Check water bodies",
        aoi_name="Unknown AOI",
        satellite_scenes=satellite_scenes,
        measurements={},
        change_events=[],
        external_evidence=[],
    )

    assert result.calibrated_confidence < 0.80
    assert any("cloud" in u.lower() for u in result.uncertainties)


def test_followup_generator():
    generator = FollowUpGenerator()

    # Change detection follow-ups
    questions = generator.generate(
        intent="urban_expansion",
        aoi_name="Chennai Metropolitan Region",
        has_changes=True,
    )
    assert len(questions) == 4
    for q in questions:
        assert isinstance(q, str)
        assert len(q) > 10

    # Vegetation health follow-ups
    veg_questions = generator.generate(
        intent="vegetation_monitoring",
        aoi_name="Pollachi Agricultural Belt",
        has_changes=False,
    )
    assert len(veg_questions) == 4
    assert any("ndvi" in q.lower() or "canopy" in q.lower() or "crop" in q.lower() for q in veg_questions)
