"""API endpoint tests covering health, models, and sessions per §7."""

import pytest


@pytest.mark.django_db
def test_models_registry_endpoint(api_client):
    res = api_client.get("/api/v1/models/")
    assert res.status_code == 200
    assert len(res.data) >= 6
    ids = [m["id"] for m in res.data]
    assert "RS_VQA" in ids
    assert "CHANGE_DETECTION" in ids
    assert "OPTICAL_SAR_FUSION" in ids


@pytest.mark.django_db
def test_model_detail_endpoint(api_client):
    res = api_client.get("/api/v1/models/RS_VQA/")
    assert res.status_code == 200
    assert res.data["id"] == "RS_VQA"
    assert res.data["task"] == "visual_question_answering"


@pytest.mark.django_db
def test_sessions_crud(auth_client):
    # 1. Create session
    c_res = auth_client.post("/api/v1/sessions/", {"name": "Test Cartosat Session"}, format="json")
    assert c_res.status_code == 201
    session_id = c_res.data["id"]

    # 2. List sessions
    l_res = auth_client.get("/api/v1/sessions/")
    assert l_res.status_code == 200
    assert any(s["id"] == session_id for s in l_res.data["results"])

    # 3. Retrieve session
    r_res = auth_client.get(f"/api/v1/sessions/{session_id}/")
    assert r_res.status_code == 200
    assert r_res.data["name"] == "Test Cartosat Session"

    # 4. Delete session
    d_res = auth_client.delete(f"/api/v1/sessions/{session_id}/")
    assert d_res.status_code == 204
