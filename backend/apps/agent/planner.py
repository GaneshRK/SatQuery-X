"""Planner component creating ordered execution plans per §8.2 & §8.5."""

from __future__ import annotations

from typing import Any


def create_execution_plan(intent: Any, mode: str) -> dict[str, Any]:
    task = intent.intent
    steps = []

    # 1. Mission Mode (comprehensive 6-step workflow)
    if task == "mission":
        steps = [
            {"step": 1, "tool": "RS_CAPTION", "parameters": {}, "description": "Scene overview & land-cover description"},
            {"step": 2, "tool": "RS_GROUNDING", "parameters": {"target": "built_up"}, "description": "Localize key structural regions"},
            {"step": 3, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Generate bi-temporal surface change map"},
            {"step": 4, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Metric area quantification (km²)"},
            {"step": 5, "tool": "CHANGE_VQA", "parameters": {"target": intent.target}, "description": "Temporal-fusion change reasoning"},
        ]
        return {
            "mode": mode,
            "task": "MISSION",
            "steps": steps,
        }

    # 2. Change-Based VQA (Compound Plan: change detection -> change vqa -> area quantifier)
    if task == "change_vqa":
        steps = [
            {"step": 1, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Generate difference mask & change clusters"},
            {"step": 2, "tool": "CHANGE_VQA", "parameters": {"target": intent.target}, "description": "Reasoning over detected change regions"},
            {"step": 3, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify area of change in km²"},
        ]
        return {
            "mode": "BI_TEMPORAL",
            "task": "CHANGE_VQA",
            "steps": steps,
        }

    # 3. Pure Change Detection
    if task == "change_detection":
        steps = [
            {"step": 1, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Generate surface change mask"},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify altered area in km²"},
        ]
        return {
            "mode": "BI_TEMPORAL",
            "task": "CHANGE_DETECTION",
            "steps": steps,
        }

    # 4. Cross-Modal Optical + SAR Fusion
    if task == "optical_sar_fusion":
        steps = [
            {"step": 1, "tool": "OPTICAL_SAR_FUSION", "parameters": {"target": intent.target}, "description": "Joint optical-SAR extraction"},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify segmented class area in km²"},
        ]
        return {
            "mode": "CROSS_MODAL",
            "task": "OPTICAL_SAR_FUSION",
            "steps": steps,
        }

    # 5. Text-Guided Grounding
    if task == "grounding":
        steps = [
            {"step": 1, "tool": "RS_GROUNDING", "parameters": {"prompt": intent.raw_text}, "description": "Propose bounding boxes & overlay"},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify grounded region area in km²"},
        ]
        return {
            "mode": "SINGLE_IMAGE",
            "task": "GROUNDING",
            "steps": steps,
        }

    # 6. Scene Captioning
    if task == "caption":
        steps = [
            {"step": 1, "tool": "RS_CAPTION", "parameters": {}, "description": "Generate remote-sensing scene description"},
        ]
        return {
            "mode": "SINGLE_IMAGE",
            "task": "CAPTION",
            "steps": steps,
        }

    # 7. Single-Image VQA (default)
    steps = [
        {"step": 1, "tool": "RS_VQA", "parameters": {"question": intent.raw_text}, "description": "Answer visual question"},
    ]
    return {
        "mode": "SINGLE_IMAGE",
        "task": "VQA",
        "steps": steps,
    }
