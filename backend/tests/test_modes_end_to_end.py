"""End-to-End Integration Tests for all Modes against Django REST API per §7 & §18."""

import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_mode_1_single_image_vqa_and_caption(auth_client, synthetic_optical_png):
    # 1. Create Session
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Mode 1 Session"}, format="json")
    assert s_res.status_code == 201
    session_id = s_res.data["id"]

    # 2. Upload Single Optical Image
    file_upload = SimpleUploadedFile("sentinel2_optical.png", synthetic_optical_png, content_type="image/png")
    up_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/images/",
        {"file": file_upload},
        format="multipart",
    )
    assert up_res.status_code == 202
    image_id = up_res.data["image_id"]

    # Verify extracted metadata
    img_res = auth_client.get(f"/api/v1/sessions/{session_id}/images/{image_id}/")
    assert img_res.status_code == 200
    assert img_res.data["processing_status"] == "VALIDATED"
    assert img_res.data["sensor"] == "SENTINEL-2"

    # 3. Query RS-VQA
    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "What is visible in this remote sensing image?", "image_id": image_id},
        format="json",
    )
    assert q_res.status_code == 202
    query_id = q_res.data["query_id"]

    # Check Query Detail
    detail_res = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{query_id}/")
    assert detail_res.status_code == 200
    assert detail_res.data["status"] == "COMPLETED"
    assert detail_res.data["answer"] is not None
    assert detail_res.data["confidence"] > 0.0
    assert len(detail_res.data["execution_steps"]) >= 1


@pytest.mark.django_db
def test_mode_2_cross_modal_fusion(auth_client, synthetic_optical_png, synthetic_sar_png):
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Cross-Modal Session"}, format="json")
    session_id = s_res.data["id"]

    # Upload Optical
    f_opt = SimpleUploadedFile("optical_s2.png", synthetic_optical_png, content_type="image/png")
    res_opt = auth_client.post(f"/api/v1/sessions/{session_id}/images/", {"file": f_opt}, format="multipart")
    opt_id = res_opt.data["image_id"]

    # Upload SAR
    f_sar = SimpleUploadedFile("sar_risat.png", synthetic_sar_png, content_type="image/png")
    res_sar = auth_client.post(f"/api/v1/sessions/{session_id}/images/", {"file": f_sar}, format="multipart")
    sar_id = res_sar.data["image_id"]

    # Create Pair
    pair_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/pairs/",
        {"image_a_id": opt_id, "image_b_id": sar_id, "pair_type": "CROSS_MODAL"},
        format="json",
    )
    assert pair_res.status_code == 202
    pair_id = pair_res.data["pair_id"]

    # Query Optical + SAR
    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {
            "text": "Use the optical and SAR images together to identify built-up and water-covered regions.",
            "pair_id": pair_id,
        },
        format="json",
    )
    assert q_res.status_code == 202
    q_data = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{q_res.data['query_id']}/").data
    assert q_data["status"] == "COMPLETED"
    assert "optical-sar" in q_data["answer"].lower() or "built-up" in q_data["answer"].lower()
    assert q_data["detected_mode"] == "CROSS_MODAL"


@pytest.mark.django_db
def test_mode_3_bitemporal_change_detection_and_quantification(auth_client, synthetic_optical_png):
    s_res = auth_client.post("/api/v1/sessions/", {"name": "Change Session"}, format="json")
    session_id = s_res.data["id"]

    f_t1 = SimpleUploadedFile("time1.png", synthetic_optical_png, content_type="image/png")
    t1_id = auth_client.post(f"/api/v1/sessions/{session_id}/images/", {"file": f_t1}, format="multipart").data["image_id"]

    # Different image for T2
    t2_bytes = bytearray(synthetic_optical_png)
    t2_bytes[50:150] = b"\xff" * 100  # inject changes
    f_t2 = SimpleUploadedFile("time2.png", bytes(t2_bytes), content_type="image/png")
    t2_id = auth_client.post(f"/api/v1/sessions/{session_id}/images/", {"file": f_t2}, format="multipart").data["image_id"]

    pair_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/pairs/",
        {"image_a_id": t1_id, "image_b_id": t2_id, "pair_type": "BI_TEMPORAL"},
        format="json",
    )
    pair_id = pair_res.data["pair_id"]

    # Query Change Detection
    q_res = auth_client.post(
        f"/api/v1/sessions/{session_id}/queries/",
        {"text": "What changed between these two dates, and where did the change occur?", "pair_id": pair_id},
        format="json",
    )
    assert q_res.status_code == 202
    q_data = auth_client.get(f"/api/v1/sessions/{session_id}/queries/{q_res.data['query_id']}/").data
    assert q_data["status"] == "COMPLETED"
    assert q_data["detected_mode"] == "BI_TEMPORAL"
    assert len(q_data["execution_steps"]) >= 2


@pytest.mark.django_db
def test_satellite_search_and_intelligence_report(auth_client):
    # 1. Satellite candidate search
    sat_res = auth_client.post(
        "/api/v1/satellite/search/",
        {
            "aoi_geometry": {"type": "Polygon", "coordinates": [[[77.1, 28.5], [77.3, 28.5], [77.3, 28.7], [77.1, 28.7], [77.1, 28.5]]]},
            "sensor": "SENTINEL-2",
            "date_start": "2026-08-01",
            "date_end": "2026-08-30",
            "max_cloud_cover": 15.0,
        },
        format="json",
    )
    assert sat_res.status_code == 201
    req_id = sat_res.data["request_id"]

    # 2. Get candidates
    cand_res = auth_client.get(f"/api/v1/satellite/search/{req_id}/candidates/")
    assert cand_res.status_code == 200
    assert len(cand_res.data) > 0
    stac_id = cand_res.data[0]["stac_item_id"]

    # 3. Select candidate
    sel_res = auth_client.post(f"/api/v1/satellite/search/{req_id}/select/", {"stac_item_id": stac_id}, format="json")
    assert sel_res.status_code == 202

    # 4. Generate Session Report
    sess_res = auth_client.post("/api/v1/sessions/", {"name": "Report Session"}, format="json")
    session_id = sess_res.data["id"]

    rep_res = auth_client.post(f"/api/v1/sessions/{session_id}/reports/", {"format": "PDF"}, format="json")
    assert rep_res.status_code == 202
    report_id = rep_res.data["report_id"]

    rep_detail = auth_client.get(f"/api/v1/sessions/{session_id}/reports/{report_id}/")
    assert rep_detail.status_code == 200
    assert rep_detail.data["status"] == "READY"
    assert rep_detail.data["has_file"] is True

    # Download report
    dl_res = auth_client.get(f"/api/v1/sessions/{session_id}/reports/{report_id}/download/")
    assert dl_res.status_code == 200
    assert dl_res["content-type"] == "application/pdf"
