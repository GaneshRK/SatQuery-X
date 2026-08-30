"""Unit tests for AgenticPlanner and PlanValidator."""

import pytest
from backend.planner.planner import AgenticPlanner
from backend.planner.schemas import PlanStep
from backend.planner.understander import classify_query
from backend.planner.validator import PlanValidationError, validate_plan
from backend.registry.loader import ModelRegistry


def test_classify_query_modes():
    assert classify_query("What type of airplane is here?", "single_image", 1) == "vqa"
    assert classify_query("Describe this satellite scene", "single_image", 1) == "caption"
    assert classify_query("Locate solar panels", "single_image", 1) == "grounding"
    assert classify_query("Analyze optical and SAR fusion data", "cross_modal_pair", 2) == "fusion"
    assert classify_query("Has built-up area increased?", "bi_temporal", 2) == "change_vqa"
    assert classify_query("What changed between these dates?", "bi_temporal", 2) == "change_vqa"
    assert classify_query("Mission: Urban expansion assessment", "bi_temporal", 2) == "mission_mode"


def test_agentic_planner_rules():
    planner = AgenticPlanner()

    # Single Image VQA
    plan, task = planner.create_plan("What is in this image?", "single_image", 1)
    assert task == "vqa"
    assert len(plan) == 1
    assert plan[0].tool == "RS_VQA"

    # Cross-Modal Fusion
    plan, task = planner.create_plan("Analyze SAR backscatter and optical signature", "cross_modal_pair", 2)
    assert task == "fusion"
    assert plan[0].tool == "OPTICAL_SAR_FUSION"

    # Bi-Temporal Multi-step Chain
    plan, task = planner.create_plan("Has built-up area increased?", "bi_temporal", 2)
    assert task == "change_vqa"
    assert len(plan) == 2
    assert plan[0].tool == "CHANGE_DETECTION"
    assert plan[1].tool == "CHANGE_VQA"


def test_plan_validator_guardrails():
    registry = ModelRegistry()

    # Valid bi-temporal plan
    valid_plan = [
        PlanStep(step=1, tool="CHANGE_DETECTION", version="v0.1-baseline", params={}),
        PlanStep(step=2, tool="CHANGE_VQA", version="v0.1-baseline", params={"question": "trend"}),
    ]
    validate_plan(valid_plan, "bi_temporal", 2, registry)

    # Invalid: change detection with only 1 image
    with pytest.raises(PlanValidationError):
        validate_plan(valid_plan, "single_image", 1, registry)
