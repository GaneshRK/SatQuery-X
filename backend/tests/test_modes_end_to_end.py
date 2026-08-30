"""End-to-End Integration Tests for all 4 Input Modes (§2 & §14).

Mode 1: Single-image RS-VQA & Captioning & Grounding
Mode 2: Cross-modal optical + SAR paired-image fusion
Mode 3: Bi-temporal change detection & change map evidence
Mode 4: Change-based VQA with quantified reasoned response
"""

import pytest


@pytest.mark.asyncio
async def test_mode_1_single_image_vqa(client, clean_store, synthetic_optical_png):
    # 1. Create session
    sess_res = await client.post("/v1/sessions")
    assert sess_res.status_code == 201
    session_id = sess_res.json()["session_id"]

    # 2. Upload single optical image
    files = [("files", ("cartosat_scene.png", synthetic_optical_png, "image/png"))]
    up_res = await client.post(f"/v1/sessions/{session_id}/images", files=files)
    assert up_res.status_code == 201
    up_data = up_res.json()
    assert up_data["detected_mode"] == "single_image"
    assert len(up_data["images"]) == 1

    # 3. Query: RS-VQA
    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "What are the primary terrain features in this scene?"},
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["detected_mode"] == "single_image"
    assert q_data["task_classification"] == "vqa"
    assert q_data["confidence"] > 0.0
    assert q_data["timings_ms"]["total"] > 0.0
    assert len(q_data["plan"]) >= 1


@pytest.mark.asyncio
async def test_mode_1_single_image_grounding(client, clean_store, synthetic_optical_png):
    sess_res = await client.post("/v1/sessions")
    session_id = sess_res.json()["session_id"]

    files = [("files", ("scene.png", synthetic_optical_png, "image/png"))]
    await client.post(f"/v1/sessions/{session_id}/images", files=files)

    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "Locate vegetation and forest regions"},
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["task_classification"] == "grounding"
    assert len(q_data["evidence"]["bboxes"]) > 0
    assert len(q_data["evidence"]["geojson"]) > 0


@pytest.mark.asyncio
async def test_mode_2_cross_modal_fusion(client, clean_store, synthetic_optical_png, synthetic_sar_png):
    sess_res = await client.post("/v1/sessions")
    session_id = sess_res.json()["session_id"]

    # Upload co-registered Optical + SAR pair
    files = [
        ("files", ("cartosat_optical.png", synthetic_optical_png, "image/png")),
        ("files", ("risat_sar.png", synthetic_sar_png, "image/png")),
    ]
    up_res = await client.post(f"/v1/sessions/{session_id}/images", files=files)
    assert up_res.status_code == 201
    up_data = up_res.json()
    assert up_data["detected_mode"] == "cross_modal_pair"
    assert up_data["co_registration_valid"] is True

    # Query: Cross-Modal Joint Analysis
    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "Perform fused optical and SAR cross-modal land cover analysis"},
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["detected_mode"] == "cross_modal_pair"
    assert q_data["task_classification"] == "fusion"
    assert "Fused optical+SAR analysis" in q_data["answer"]
    assert q_data["confidence"] > 0.5


@pytest.mark.asyncio
async def test_mode_3_bitemporal_change_detection(client, clean_store, synthetic_bitemporal_pngs):
    t1_bytes, t2_bytes = synthetic_bitemporal_pngs
    sess_res = await client.post("/v1/sessions")
    session_id = sess_res.json()["session_id"]

    files = [
        ("files", ("time1_pre.png", t1_bytes, "image/png")),
        ("files", ("time2_post.png", t2_bytes, "image/png")),
    ]
    up_res = await client.post(f"/v1/sessions/{session_id}/images", files=files)
    assert up_res.status_code == 201
    assert up_res.json()["detected_mode"] == "bi_temporal"

    # Query: Change Detection
    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "Detect spatial change and generate change mask"},
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["detected_mode"] == "bi_temporal"
    assert q_data["evidence"]["change_mask_url"] is not None
    assert q_data["evidence"]["quantified_area_km2"] is not None
    assert q_data["evidence"]["change_percentage"] is not None


@pytest.mark.asyncio
async def test_mode_4_change_vqa(client, clean_store, synthetic_bitemporal_pngs):
    t1_bytes, t2_bytes = synthetic_bitemporal_pngs
    sess_res = await client.post("/v1/sessions")
    session_id = sess_res.json()["session_id"]

    files = [
        ("files", ("time1.png", t1_bytes, "image/png")),
        ("files", ("time2.png", t2_bytes, "image/png")),
    ]
    await client.post(f"/v1/sessions/{session_id}/images", files=files)

    # Query: Specific reasoned change question
    q_res = await client.post(
        f"/v1/sessions/{session_id}/query",
        json={"text": "Has built-up area increased significantly between these two dates?"},
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["task_classification"] == "change_vqa"
    assert "Yes" in q_data["answer"] or "increased" in q_data["answer"].lower()
    assert q_data["confidence"] > 0.6
    assert len(q_data["plan"]) == 2  # CHANGE_DETECTION -> CHANGE_VQA
