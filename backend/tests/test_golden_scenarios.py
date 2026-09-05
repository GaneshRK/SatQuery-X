"""
Test Suite for the 7 Golden SIH 2026 Test Scenarios per Phase 11.

Scenarios:
1. Single-Image Scene Captioning
2. Single-Image Remote-Sensing VQA
3. Single-Image Visual Grounding
4. Bi-temporal Change Detection & Area Quantification
5. Bi-temporal Change VQA
6. Optical + SAR Cross-Modal Fusion
7. Multi-Turn Interactive Conversational Follow-Up
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_demo_scenarios_discovery_api(client):
    """Verifies that the demo scenarios catalog endpoint returns all 7 scenarios."""
    res = client.get("/api/v1/demo-scenarios/")
    assert res.status_code == 200
    data = res.json()
    assert data["sih_problem_statement"] == "26167"
    assert data["count"] == 7
    keys = [s["key"] for s in data["scenarios"]]
    assert "scenario_1_caption" in keys
    assert "scenario_4_change_detection" in keys
    assert "scenario_6_optical_sar_fusion" in keys
    assert "scenario_7_multiturn" in keys


@pytest.mark.django_db
def test_golden_scenario_1_single_image_captioning(auth_client):
    """Scenario 1: Single-Image Scene Captioning via demo bootstrap."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_1_caption/")
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "bootstrapped"
    assert data["query_status"] == "COMPLETED"
    assert len(data["answer"]) > 15
    assert data["confidence"] > 0.0


@pytest.mark.django_db
def test_golden_scenario_2_single_image_vqa(auth_client):
    """Scenario 2: Single-Image Remote-Sensing VQA via demo bootstrap."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_2_vqa/")
    assert res.status_code == 201
    data = res.json()
    assert data["query_status"] == "COMPLETED"
    assert data["confidence"] > 0.0


@pytest.mark.django_db
def test_golden_scenario_3_visual_grounding(auth_client):
    """Scenario 3: Single-Image Visual Grounding with candidate bounding boxes."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_3_grounding/")
    assert res.status_code == 201
    data = res.json()
    assert data["query_status"] == "COMPLETED"
    assert data["answer"] is not None


@pytest.mark.django_db
def test_golden_scenario_4_bitemporal_change_detection_and_area(auth_client):
    """Scenario 4: Bi-temporal change detection with metric area quantification."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_4_change_detection/")
    assert res.status_code == 201
    data = res.json()
    assert data["query_status"] == "COMPLETED"
    assert "pair_id" in data
    # Verify answer describes surface alteration or metric area
    assert "change" in data["answer"].lower() or "surface" in data["answer"].lower() or "ha" in data["answer"]


@pytest.mark.django_db
def test_golden_scenario_5_bitemporal_change_vqa(auth_client):
    """Scenario 5: Bi-temporal Change VQA answering qualitative questions over temporal pair."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_5_change_vqa/")
    assert res.status_code == 201
    data = res.json()
    assert data["query_status"] == "COMPLETED"
    assert data["answer"] is not None


@pytest.mark.django_db
def test_golden_scenario_6_optical_sar_cross_modal_fusion(auth_client):
    """Scenario 6: Optical + SAR cross-modal fusion with joint analysis."""
    res = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_6_optical_sar_fusion/")
    assert res.status_code == 201
    data = res.json()
    assert data["query_status"] == "COMPLETED"
    assert "pair_id" in data
    assert data["confidence"] > 0.5


@pytest.mark.django_db
def test_golden_scenario_7_multiturn_conversational_follow_up(auth_client):
    """Scenario 7: Multi-turn conversational follow-up ('Where?' -> 'How much?')."""
    # Turn 1: Bootstrap initial query
    res1 = auth_client.post("/api/v1/demo-scenarios/bootstrap/scenario_7_multiturn/")
    assert res1.status_code == 201
    data1 = res1.json()
    session_id = data1["session_id"]
    pair_id = data1["pair_id"]

    # Turn 2: Follow-up query in same session referencing prior context
    res2 = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {
            "text": "How much total metric area does this change represent in hectares and square kilometers?",
            "pair_id": pair_id,
        },
        format="json",
    )
    assert res2.status_code == 202
    q2_id = res2.json()["query_id"]

    # Verify Turn 2 completed and maintains conversation context
    detail2 = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{q2_id}/").json()
    assert detail2["status"] == "COMPLETED"
    assert "ha" in detail2["answer"].lower() or "km²" in detail2["answer"].lower() or "area" in detail2["answer"].lower()


@pytest.mark.django_db
def test_golden_scenario_mode_a_location_change(auth_client):
    """
    Mode A: User has NO image, asks 'What is changing around Pollachi?'
    System autonomously resolves Pollachi location, queries satellite catalog,
    ingests Sentinel-2 observation pair, runs bi-temporal change detection,
    and returns answer with visual evidence and provenance.
    """
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Mode A Pollachi Session"}, format="json")
    assert s_res.status_code == 201
    session_id = s_res.data["id"]

    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "What is changing around Pollachi?"},
        format="json",
    )
    assert q_res.status_code == 202
    query_id = q_res.data["query_id"]

    detail = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{query_id}/").json()
    assert detail["status"] == "COMPLETED"
    assert "pollachi" in detail["answer"].lower() or "surface" in detail["answer"].lower() or "dynamics" in detail["answer"].lower()
    assert detail["confidence"] > 0.5
    # Verify autonomous satellite ingestion took place
    images = auth_client.get(f"/api/v1/sessions/{session_id}/images/").json()
    assert len(images) >= 2
    from apps.imagery.models import ImagePair
    assert ImagePair.objects.filter(session_id=session_id).count() >= 1


@pytest.mark.django_db
def test_golden_scenario_mode_a_latest_observation(auth_client):
    """
    Mode A: User has NO image, asks 'Show me the latest satellite observation of Chennai'.
    System resolves Chennai, searches latest available observation, and returns scene assessment.
    """
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Mode A Chennai Session"}, format="json")
    assert s_res.status_code == 201
    session_id = s_res.data["id"]

    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "Show me the latest satellite observation of Chennai"},
        format="json",
    )
    assert q_res.status_code == 202
    query_id = q_res.data["query_id"]

    detail = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{query_id}/").json()
    assert detail["status"] == "COMPLETED"
    assert detail["confidence"] > 0.5
    # Verify satellite scene was acquired
    images = auth_client.get(f"/api/v1/sessions/{session_id}/images/").json()
    assert len(images) >= 1
    sensor = images[0]["sensor"]
    assert sensor in ("SENTINEL-2", "SENTINEL-1")


@pytest.mark.django_db
def test_golden_scenario_ambiguous_clarification(auth_client):
    """
    Scenario: Ambiguous query ('What is changing here?') with NO image, NO AOI, NO location.
    System must NOT hallucinate; it returns a polite clarification request per §57.
    """
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Ambiguous Session"}, format="json")
    assert s_res.status_code == 201
    session_id = s_res.data["id"]

    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "What is changing here?"},
        format="json",
    )
    assert q_res.status_code == 202
    query_id = q_res.data["query_id"]

    detail = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{query_id}/").json()
    assert detail["status"] == "COMPLETED"
    assert "where you mean" in detail["answer"].lower() or "place name" in detail["answer"].lower()
    assert detail["clarification"] is not None
    assert len(detail["clarification"]["options"]) >= 2


@pytest.mark.django_db
def test_golden_scenario_mode_b_image_satellite_matching(auth_client, synthetic_optical_png):
    """
    Mode B: User uploads a single georeferenced image, asks 'What changed here?'
    System resolves its footprint, discovers matching satellite observations,
    aligns them, and executes comparative change detection per §14.
    """
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Mode B Session"}, format="json")
    assert s_res.status_code == 201
    session_id = s_res.data["id"]

    file_upload = SimpleUploadedFile("farm.png", synthetic_optical_png, content_type="image/png")
    up_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/images/",
        {"file": file_upload},
        format="multipart",
    )
    assert up_res.status_code == 202
    image_id = up_res.data["image_id"]

    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "What changed here?", "image_id": image_id},
        format="json",
    )
    assert q_res.status_code == 202
    query_id = q_res.data["query_id"]

    detail = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{query_id}/").json()
    assert detail["status"] == "COMPLETED"
    assert detail["confidence"] > 0.5
    # Verify satellite image was paired with uploaded image
    images = auth_client.get(f"/api/v1/sessions/{session_id}/images/").json()
    assert len(images) >= 2
    from apps.imagery.models import ImagePair
    assert ImagePair.objects.filter(session_id=session_id).count() >= 1



def test_spectral_index_safety_missing_bands():
    """
    Index Safety (§19): Attempting NDVI on an array lacking Red/NIR bands
    strictly raises ValueError rather than fabricating NDVI values.
    """
    import numpy as np
    from apps.geospatial.indices import compute_spectral_index_from_raster

    # 1-band raster
    single_band = np.ones((512, 512), dtype=np.float32)
    with pytest.raises(ValueError, match="cannot compute multi-spectral index"):
        compute_spectral_index_from_raster(single_band, "NDVI")

    # 2-band SAR raster (VV, VH) cannot compute optical NDVI
    sar_bands = np.ones((2, 512, 512), dtype=np.float32)
    with pytest.raises(ValueError, match="lacks required"):
        compute_spectral_index_from_raster(sar_bands, "NDVI", sensor_name="SENTINEL-1", modality="SAR")

