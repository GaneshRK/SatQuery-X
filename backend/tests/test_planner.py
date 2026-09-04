"""Unit tests for Agent planner, understander, and validator per §8."""

import pytest
from apps.agent.planner import create_execution_plan
from apps.agent.understander import understand_query
from apps.agent.validator import validate_agent_inputs


def test_planner_rules():
    # 1. Single-Image VQA Plan
    i_vqa = understand_query("What is the resolution of this image?")
    p_vqa = create_execution_plan(i_vqa, "SINGLE_IMAGE")
    assert p_vqa["task"] == "VQA"
    assert len(p_vqa["steps"]) == 1
    assert p_vqa["steps"][0]["tool"] == "RS_VQA"

    # 2. Change-Based VQA Plan (Compound: CD -> Change_VQA -> Area_Quantifier)
    i_cd_vqa = understand_query("Has the built-up area increased, decreased, or remained unchanged?")
    p_cd_vqa = create_execution_plan(i_cd_vqa, "BI_TEMPORAL")
    assert p_cd_vqa["task"] == "CHANGE_VQA"
    assert len(p_cd_vqa["steps"]) == 3
    tools = [s["tool"] for s in p_cd_vqa["steps"]]
    assert tools == ["CHANGE_DETECTION", "CHANGE_VQA", "AREA_QUANTIFIER"]

    # 3. Mission Mode Plan (6-step comprehensive workflow)
    i_mission = understand_query("Analyze this region for urban expansion")
    p_mission = create_execution_plan(i_mission, "BI_TEMPORAL")
    assert p_mission["task"] == "MISSION"
    assert len(p_mission["steps"]) >= 5


def test_validator_rules():
    # Missing images for bi-temporal
    i_temp = understand_query("What changed between these two dates?")
    val_fail = validate_agent_inputs(i_temp, image_assets=[])
    assert val_fail["valid"] is False
    assert any("requires 2 images" in r for r in val_fail["reasons"])
