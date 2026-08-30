"""API endpoint tests covering health, models, auth, and report export."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    res = await client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["components"]["api_gateway"] is True


@pytest.mark.asyncio
async def test_models_registry_endpoint(client):
    res = await client.get("/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 6
    ids = [m["id"] for m in data["models"]]
    assert "RS_VQA" in ids
    assert "RS_CAPTION" in ids
    assert "RS_GROUNDING" in ids
    assert "CHANGE_DETECTION" in ids
    assert "CHANGE_VQA" in ids
    assert "OPTICAL_SAR_FUSION" in ids

    # Test /registry alias
    reg_res = await client.get("/v1/models/registry")
    assert reg_res.status_code == 200
    assert reg_res.json()["count"] == data["count"]

    # Test single model lookup
    single_res = await client.get("/v1/models/RS_VQA")
    assert single_res.status_code == 200
    assert single_res.json()["id"] == "RS_VQA"

    # Test unknown model returns 404
    unknown_res = await client.get("/v1/models/non_existent_model")
    assert unknown_res.status_code == 404


@pytest.mark.asyncio
async def test_auth_token_generation(client):
    res = await client.post("/v1/auth/token", json={"username": "isro_lead_evaluator", "password": "secure"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "isro_evaluator"


@pytest.mark.asyncio
async def test_report_generation(client, clean_store, synthetic_optical_png):
    # 1. Create session + image + query
    sess_res = await client.post("/v1/sessions")
    session_id = sess_res.json()["session_id"]

    files = [("files", ("image.png", synthetic_optical_png, "image/png"))]
    await client.post(f"/v1/sessions/{session_id}/images", files=files)

    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "Summarize and describe scene features"},
    )
    query_id = q_res.json()["query_id"]

    # 2. Generate Report
    rep_res = await client.post(
        f"/v1/sessions/{session_id}/report",
        json={
            "query_id": query_id,
            "title": "ISRO Evaluation Intelligence Report",
            "format": "html",
            "analyst_notes": "All bounding coordinates and classifications verified.",
        },
    )
    assert rep_res.status_code == 201
    rep_data = rep_res.json()
    assert "report_id" in rep_data
    assert "download_url" in rep_data

    # 3. View Report HTML
    view_res = await client.get(f"/v1/sessions/{session_id}/report/{rep_data['report_id']}/view")
    assert view_res.status_code == 200
    assert "ISRO Evaluation Intelligence Report" in view_res.text
