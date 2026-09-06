"""Unit tests for SatQuery-AI-frontend-starter API contract endpoints at /api/."""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_contract_auth_register_and_login():
    client = APIClient()

    # 1. Register
    reg_res = client.post(
        "/api/auth/register/",
        {
            "full_name": "Ganesh K",
            "email": "ganesh.tester@example.com",
            "password": "StrongPassword123!",
        },
        format="json",
    )
    assert reg_res.status_code == 201
    assert "access" in reg_res.data
    assert "refresh" in reg_res.data
    assert "user" in reg_res.data
    assert reg_res.data["user"]["email"] == "ganesh.tester@example.com"
    assert reg_res.data["user"]["full_name"] == "Ganesh K"

    # 2. Login
    login_res = client.post(
        "/api/auth/login/",
        {
            "email": "ganesh.tester@example.com",
            "password": "StrongPassword123!",
        },
        format="json",
    )
    assert login_res.status_code == 200
    assert "access" in login_res.data
    assert "user" in login_res.data

    # 3. Me
    token = login_res.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    me_res = client.get("/api/auth/me/")
    assert me_res.status_code == 200
    assert me_res.data["email"] == "ganesh.tester@example.com"


@pytest.mark.django_db
def test_contract_analysis_query_and_history():
    client = APIClient()

    # Query without auth should succeed using default analyst session
    res = client.post(
        "/api/analysis/query/",
        {
            "query": "What is the vegetation cover around Coimbatore?",
            "location": "Coimbatore, Tamil Nadu",
            "source": "sentinel-2",
            "bbox": [76.9, 10.9, 77.1, 11.1],
        },
        format="json",
    )
    assert res.status_code == 200
    assert "analysis_id" in res.data
    assert "answer" in res.data
    assert "confidence" in res.data
    assert "metrics" in res.data
    assert "result_image_url" in res.data
    assert len(res.data["answer"]) > 10

    # Test history
    hist_res = client.get("/api/analysis/history/")
    assert hist_res.status_code == 200
    assert isinstance(hist_res.data, list)
    assert len(hist_res.data) >= 1
    assert hist_res.data[0]["analysis_id"] == res.data["analysis_id"]


@pytest.mark.django_db
def test_contract_projects():
    client = APIClient()

    post_res = client.post(
        "/api/projects/",
        {"name": "Tamil Nadu Agricultural Monitoring", "description": "Vegetation tracking"},
        format="json",
    )
    assert post_res.status_code == 201
    assert post_res.data["name"] == "Tamil Nadu Agricultural Monitoring"

    get_res = client.get("/api/projects/")
    assert get_res.status_code == 200
    assert any(p["name"] == "Tamil Nadu Agricultural Monitoring" for p in get_res.data)


@pytest.mark.django_db
def test_contract_ambiguous_query_clarification():
    client = APIClient()

    # User asks "what is changing here" without an image and without location
    res = client.post(
        "/api/analysis/query/",
        {
            "query": "what is changing here",
        },
        format="json",
    )
    assert res.status_code == 200
    assert res.data["clarification_required"] is True
    assert "clarification_options" in res.data
    assert len(res.data["clarification_options"]) > 0
    assert "clarification_prompt" in res.data
    assert "where you mean" in res.data["clarification_prompt"].lower() or "place name" in res.data["clarification_prompt"].lower()


@pytest.mark.django_db
def test_contract_multipart_image_uploads():
    import io
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    client = APIClient()

    # Create dummy RGB test images
    img1_io = io.BytesIO()
    Image.new("RGB", (64, 64), color=(34, 139, 34)).save(img1_io, format="PNG")
    img1_io.seek(0)
    file_before = SimpleUploadedFile("t1_before.png", img1_io.getvalue(), content_type="image/png")

    img2_io = io.BytesIO()
    Image.new("RGB", (64, 64), color=(139, 69, 19)).save(img2_io, format="PNG")
    img2_io.seek(0)
    file_after = SimpleUploadedFile("t2_after.png", img2_io.getvalue(), content_type="image/png")

    # Post bi-temporal before & after images with change query
    res = client.post(
        "/api/analysis/query/",
        {
            "query": "What has changed between these two dates?",
            "before_image": file_before,
            "after_image": file_after,
        },
        format="multipart",
    )
    assert res.status_code == 200
    assert "analysis_id" in res.data
    assert "answer" in res.data
    assert res.data["workflow"] in ("BI_TEMPORAL", "CHANGE_DETECTION", "CHANGE_VQA")
    assert "before_image_url" in res.data
    assert "after_image_url" in res.data
    assert len(res.data["agent_steps"]) > 0

