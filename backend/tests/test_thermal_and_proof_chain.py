"""Tests for Thermal Hotspot Intent, Sensor Reality Disclaimers, and Deterministic Evidence Proof Chain."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.agent.agent import Agent
from apps.agent.intent_ontology import GeoIntent, classify_geo_intent, INTENT_METADATA_REGISTRY
from apps.agent.understander import understand_query
from apps.queries.models import Query
from apps.sessions.models import Session

User = get_user_model()


def test_thermal_hotspot_intent_classification():
    """Verify that heat and thermal coordinate queries classify as THERMAL_HOTSPOT."""
    query_1 = "visualize the heat cordinates"
    intent_1, target_1, extra_1 = classify_geo_intent(query_1)
    assert intent_1 == GeoIntent.THERMAL_HOTSPOT
    assert "sensor_reality_note" in extra_1

    query_2 = "visualize the heat coordinates in Coimbatore"
    intent_2, _, _ = classify_geo_intent(query_2)
    assert intent_2 == GeoIntent.THERMAL_HOTSPOT

    # Test understand_query directly
    understood = understand_query("visualize the heat cordinates")
    assert understood.intent == "THERMAL_HOTSPOT"
    assert understood.geo_intent == GeoIntent.THERMAL_HOTSPOT


def test_thermal_intent_metadata_and_sensor_reality():
    """Verify intent metadata explicitly registers the Sentinel-2 TIR absence and Landsat requirement."""
    meta = INTENT_METADATA_REGISTRY.get(GeoIntent.THERMAL_HOTSPOT)
    assert meta is not None
    assert meta.sensor_reality_note is not None
    assert "Sentinel-2 MSI is an optical VNIR/SWIR instrument and lacks a thermal infrared" in meta.sensor_reality_note
    assert "Landsat-8/9 TIRS" in meta.sensor_reality_note


@pytest.mark.django_db
def test_agent_thermal_hotspot_execution():
    """Verify Agent.run executes THERMAL_HOTSPOT query with sensor disclaimer, centroid table, and evidence chain."""
    user = User.objects.create(username="analyst_test", email="test@satquery.ai")
    session = Session.objects.create(user=user)
    query = Query.objects.create(session=session, user=user, text="visualize the heat cordinates")

    session_context = {
        "active_aoi": {"name": "Coimbatore, Tamil Nadu", "bbox": [76.85, 10.95, 77.10, 11.15]},
        "current_viewport": {"west": 76.85, "south": 10.95, "east": 77.10, "north": 11.15},
    }

    result = Agent.run(query, session_context=session_context)

    assert result["status"] == "COMPLETED"
    assert result["workflow"] == "THERMAL_HOTSPOT"

    # 1. Thermal sensor disclaimer
    assert "Sensor Grounding & Thermal Reality Check" in query.answer
    assert "thermal infrared" in query.answer.lower()
    assert "Landsat-8/9 TIRS" in query.answer

    # 2. Centroid coordinates table
    assert "Centroid Coordinates" in query.answer
    assert "11." in query.answer and "76." in query.answer
    assert "HOTSPOT-01" in query.answer
    assert "cluster" in query.answer.lower()

    # 3. Hotspots in metrics
    metrics = result.get("metrics", {})
    hotspots = metrics.get("hotspots", [])
    assert len(hotspots) >= 3
    assert "lat" in hotspots[0] and "lng" in hotspots[0]
    assert "centroid_lat" in hotspots[0] and "centroid_lng" in hotspots[0]
    assert "intensity" in hotspots[0]

    # 4. Evidence Chain in metrics
    evidence_chain = metrics.get("evidence_chain", {})
    assert evidence_chain.get("pixel_count") == 184000
    assert evidence_chain.get("pixel_ground_area_m2") == 100.0
    assert evidence_chain.get("source_crs") == "EPSG:4326"
    assert evidence_chain.get("analysis_crs") == "EPSG:6933"

    # 5. Agent Steps (11-stage trace)
    agent_steps = result.get("agent_steps", [])
    assert len(agent_steps) == 11
    assert any("Sensor Reality Verification" in s.get("tool", "") for s in agent_steps)
    assert any("Centroid Geodetic Derivation" in s.get("tool", "") for s in agent_steps)


@pytest.mark.django_db
def test_contract_api_thermal_hotspots_and_proof_chain():
    """Verify /api/analysis/query/ returns evidence chain, independent confidence, and hotspot centroids."""
    client = APIClient()

    res = client.post(
        "/api/analysis/query/",
        {
            "query": "visualize the heat cordinates",
            "location": "Coimbatore, Tamil Nadu",
            "bbox": [76.90, 10.95, 77.05, 11.10],
        },
        format="json",
    )

    assert res.status_code == 200
    data = res.data

    # Check evidence chain
    assert "evidence_chain" in data
    chain = data["evidence_chain"]
    assert chain["pixel_count"] == 184000
    assert chain["pixel_ground_area_m2"] == 100.0
    assert chain["total_area_km2"] == 18.40
    assert chain["source_crs"] == "EPSG:4326"
    assert chain["analysis_crs"] == "EPSG:6933"

    # Check independent confidence breakdown
    assert "confidence_breakdown" in data
    breakdown = data["confidence_breakdown"]
    assert "data_quality_pct" in breakdown
    assert "result_confidence_pct" in breakdown
    assert "model_confidence_pct" in breakdown
    # Result confidence should NOT blindly equal model confidence
    assert breakdown["result_confidence_pct"] != breakdown["model_confidence_pct"]

    # Check hotspots centroid list
    assert "hotspots" in data
    assert len(data["hotspots"]) >= 3
    h0 = data["hotspots"][0]
    assert "lat" in h0 and "lng" in h0 and "cluster_id" in h0 and "intensity" in h0
    assert "centroid_lat" in h0 and "centroid_lng" in h0

    # Check CRS fields
    assert "EPSG:4326" in data["source_crs"]
    assert "EPSG:6933" in data["analysis_crs"]
    assert "heatmap_geojson_url" in data
