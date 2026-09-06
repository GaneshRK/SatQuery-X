"""Unit tests for SatQuery-X Layer 3 ToolRegistry and Layer 4 Specialist AI Adapters."""

import numpy as np
import pytest
from PIL import Image

from ai.adapters import (
    GeoChatVQAAdapter,
    ChangeFormerAdapter,
    GroundingDINOAdapter,
    OpticalSARAdapter,
    RemoteCLIPAdapter,
    QwenSLMAdapter,
)
from apps.agent.tool_registry import ToolRegistry, ToolDefinition


def test_geochat_adapter_vqa_and_caption():
    adapter = GeoChatVQAAdapter()
    assert adapter.model_id == "GeoChat"
    assert adapter.task == "visual_question_answering"

    # Create dummy RGB image
    img = Image.new("RGB", (100, 100), color=(30, 120, 40))

    # Test VQA
    out_vqa = adapter.answer(img, "Is there vegetation in this scene?")
    assert out_vqa.status == "ok"
    assert out_vqa.confidence > 0.5
    assert len(out_vqa.answer) > 5

    # Test Caption
    out_cap = adapter.caption(img)
    assert out_cap.status == "ok"
    assert out_cap.caption is not None
    assert len(out_cap.caption) > 5

    health = adapter.health()
    assert health["status"] == "healthy"
    assert health["model_id"] == "GeoChat"


def test_changeformer_adapter_change_detection_and_vqa():
    adapter = ChangeFormerAdapter()
    assert adapter.model_id == "ChangeFormer"
    assert adapter.task == "bi_temporal_change_map"

    # Create dummy T1 and T2 images with differences
    img1 = Image.new("RGB", (64, 64), color=(50, 100, 50))
    img2 = Image.new("RGB", (64, 64), color=(180, 180, 180))

    out_cd = adapter.detect_change(img1, img2)
    assert out_cd.status == "ok"
    assert out_cd.change_mask is not None
    assert "area_ha" in out_cd.raw
    assert out_cd.raw["change_detected"] is True

    # Test Change VQA
    out_vqa = adapter.answer_change(img1, img2, change_mask=out_cd.change_mask, question="Has the built-up area increased?")
    assert out_vqa.status == "ok"
    assert out_vqa.answer is not None
    assert "increased" in out_vqa.answer or "Yes" in out_vqa.answer


def test_grounding_adapter():
    adapter = GroundingDINOAdapter()
    assert adapter.model_id == "GroundingDINO/SAM"

    img = Image.new("RGB", (128, 128), color=(20, 40, 150))
    out = adapter.ground(img, text_prompt="locate the water body")
    assert out.status == "ok"
    assert out.boxes is not None
    assert len(out.boxes) >= 0


def test_optical_sar_adapter():
    adapter = OpticalSARAdapter()
    assert adapter.model_id == "OpticalSARFusion"
    assert adapter.task == "cross_modal_fusion_analysis"

    img_opt = Image.new("RGB", (64, 64), color=(40, 140, 50))
    img_sar = Image.new("L", (64, 64), color=180)

    out = adapter.fuse(img_opt, img_sar)
    assert out.status == "ok"
    assert out.confidence > 0.6
    assert "built_up_percent" in out.raw


def test_remoteclip_adapter():
    adapter = RemoteCLIPAdapter()
    assert adapter.model_id == "RemoteCLIP"

    # Water-dominated image
    img = Image.new("RGB", (80, 80), color=(10, 30, 160))
    classes = ["water body", "agricultural area", "built-up area", "dense forest"]

    scores = adapter.score_similarity(img, classes)
    assert "water body" in scores
    assert scores["water body"] >= scores["built-up area"]

    ranked = adapter.classify_region(img, classes)
    assert len(ranked) == 4
    assert ranked[0]["class"] == "water body"


def test_qwen_slm_adapter():
    adapter = QwenSLMAdapter()
    assert adapter.model_id == "Qwen-SLM"

    plan = adapter.plan_query("What changed between 2022 and 2024?", session_context={"image_count": 2, "pair_type": "BI_TEMPORAL"})
    assert plan["status"] == "ok"
    assert plan["requires_change_detection"] is True
    assert "change_detection" in plan["tools_sequence"]


def test_tool_registry_formal_metadata():
    registry = ToolRegistry.get_instance()
    tools = registry.list_tools()
    assert len(tools) >= 26

    # Verify every tool declares the formal attributes
    for t in tools:
        assert "name" in t
        assert "task" in t
        assert "required_images" in t
        assert "required_relationship" in t
        assert "model" in t
        assert "gpu_requirement" in t
        assert t["gpu_requirement"] in ("CPU_ONLY", "OPTIONAL", "REQUIRED")
        assert t["required_relationship"] in ("SINGLE_IMAGE", "BI_TEMPORAL", "OPTICAL_SAR_PAIR", "NONE")


def test_tool_registry_discovery_and_compatibility():
    registry = ToolRegistry.get_instance()

    # Find VQA tools
    vqa_tools = registry.find_tools_for_task("VQA")
    assert len(vqa_tools) >= 1
    assert any(t.name == "vqa" for t in vqa_tools)

    # Find Change detection tools requiring 2 bi-temporal images
    change_tools = registry.find_tools_for_task("CHANGE_DETECTION", image_count=2, relationship="BI_TEMPORAL")
    assert len(change_tools) >= 1
    assert any(t.name == "change_detection" for t in change_tools)

    # Incompatible count should filter out change tools
    change_tools_single = registry.find_tools_for_task("CHANGE_DETECTION", image_count=1, relationship="SINGLE_IMAGE")
    assert len(change_tools_single) == 0

    # Compatibility check method (can_solve)
    can_solve, msg = registry.can_solve("change_detection", "CHANGE_DETECTION", image_count=2, relationship="BI_TEMPORAL")
    assert can_solve is True

    cannot_solve_count, msg = registry.can_solve("change_detection", "CHANGE_DETECTION", image_count=1, relationship="SINGLE_IMAGE")
    assert cannot_solve_count is False
    assert "requires 2 image(s)" in msg

    cannot_solve_rel, msg = registry.can_solve("optical_sar_fusion", "OPTICAL_SAR_ANALYSIS", image_count=2, relationship="BI_TEMPORAL")
    assert cannot_solve_rel is False
    assert "OPTICAL_SAR_PAIR" in msg


def test_tool_registry_remoteclip_execution():
    registry = ToolRegistry.get_instance()
    tool = registry.get_tool("remoteclip_semantic_retrieval")
    assert tool is not None
    assert tool.model == "RemoteCLIP"

    img = Image.new("RGB", (64, 64), color=(30, 160, 40))
    res = registry.execute("remoteclip_semantic_retrieval", image_paths=[], image_bytes=[], text_queries=["vegetation", "water body"])
    assert res["status"] == "ok"
    assert "similarity_scores" in res
    assert "top_class" in res
