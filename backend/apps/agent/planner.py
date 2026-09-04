"""Planner component creating structured tool execution sequences per §8.2."""

from __future__ import annotations
from typing import Any
from .understander import QueryIntent


def create_execution_plan(intent: Any, mode: str) -> dict[str, Any]:
    task = getattr(intent, "intent", "IMAGE_DESCRIPTION")
    target = getattr(intent, "target", "general")
    steps = []

    # 1. VQA
    if task in ("vqa", "VQA"):
        steps = [
            {"step": 1, "tool": "RS_VQA", "parameters": {}, "description": "Visual Question Answering over satellite imagery"},
        ]
        return {"mode": mode, "task": "VQA", "steps": steps}

    # 2. CHANGE_VQA
    if task in ("change_vqa", "CHANGE_VQA"):
        steps = [
            {"step": 1, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Detect temporal changes between images"},
            {"step": 2, "tool": "CHANGE_VQA", "parameters": {"target": target}, "description": "Reasoning over temporal differences"},
            {"step": 3, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify surface change area in km²"},
        ]
        return {"mode": "BI_TEMPORAL", "task": "CHANGE_VQA", "steps": steps}

    # 3. MISSION MODE
    if task in ("mission", "MISSION"):
        steps = [
            {"step": 1, "tool": "validate_inputs", "parameters": {}, "description": "Validate GSD and CRS alignment"},
            {"step": 2, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Compute temporal surface difference mask"},
            {"step": 3, "tool": "CHANGE_VQA", "parameters": {"target": target}, "description": "Assess severity and extent"},
            {"step": 4, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Derive metric area in km² and hectares"},
            {"step": 5, "tool": "generate_report", "parameters": {}, "description": "Compile comprehensive intelligence dossier"},
        ]
        return {"mode": mode, "task": "MISSION", "steps": steps}

    # 4. OBJECT_COUNTING
    if task == "OBJECT_COUNTING":
        steps = [
            {"step": 1, "tool": "validate_inputs", "parameters": {}, "description": "Validate GSD and spatial resolution"},
            {"step": 2, "tool": "detect_and_count_structures", "parameters": {"target": target}, "description": "Deterministic edge & contour structure detection"},
            {"step": 3, "tool": "calculate_area", "parameters": {}, "description": "Compute structural footprint surface area in km²"},
        ]
        return {"mode": mode, "task": "OBJECT_COUNTING", "steps": steps}

    # 5. WATER_DETECTION
    if task in ("WATER_DETECTION", "water_detection"):
        steps = [
            {"step": 1, "tool": "calculate_ndwi", "parameters": {}, "description": "Compute Normalized Difference Water Index (Green - NIR)"},
            {"step": 2, "tool": "detect_water", "parameters": {}, "description": "Otsu thresholding & water polygon extraction"},
            {"step": 3, "tool": "calculate_area", "parameters": {}, "description": "Calculate total water surface area in km²"},
        ]
        return {"mode": mode, "task": "WATER_DETECTION", "steps": steps}

    # 6. VEGETATION_ANALYSIS / AGRICULTURE
    if task in ("VEGETATION_ANALYSIS", "AGRICULTURE_ANALYSIS"):
        steps = [
            {"step": 1, "tool": "calculate_ndvi", "parameters": {}, "description": "Compute Normalized Difference Vegetation Index (NIR - Red)"},
            {"step": 2, "tool": "detect_vegetation", "parameters": {}, "description": "Canopy segmentation & polygonization"},
            {"step": 3, "tool": "calculate_area", "parameters": {}, "description": "Calculate vegetative surface area in km²"},
        ]
        return {"mode": mode, "task": "VEGETATION_ANALYSIS", "steps": steps}

    # 7. BUILDING_ANALYSIS / URBAN_ANALYSIS
    if task in ("BUILDING_ANALYSIS", "URBAN_ANALYSIS", "ROAD_ANALYSIS"):
        steps = [
            {"step": 1, "tool": "detect_and_count_structures", "parameters": {"target": target}, "description": "Extract built-up infrastructure candidates"},
            {"step": 2, "tool": "calculate_area", "parameters": {}, "description": "Quantify urban footprint in km²"},
        ]
        return {"mode": mode, "task": "BUILDING_ANALYSIS", "steps": steps}

    # 8. SATELLITE_SEARCH
    if task == "SATELLITE_SEARCH":
        steps = [
            {"step": 1, "tool": "search_satellite_imagery", "parameters": {"sensor": target}, "description": "Search Copernicus STAC catalog"},
        ]
        return {"mode": mode, "task": "SATELLITE_SEARCH", "steps": steps}

    # 9. Bi-Temporal Change Detection
    if task in ("CHANGE_DETECTION", "change_detection") or mode == "BI_TEMPORAL":
        steps = [
            {"step": 1, "tool": "CHANGE_DETECTION", "parameters": {}, "description": "Generate bi-temporal surface change difference mask"},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Quantify altered surface area in km²"},
            {"step": 3, "tool": "CHANGE_VQA", "parameters": {"target": target}, "description": "Reasoning over temporal change regions"},
        ]
        return {"mode": "BI_TEMPORAL", "task": "CHANGE_DETECTION", "steps": steps}

    # 7. Cross-Modal Optical + SAR
    if task == "OPTICAL_SAR_COMPARISON" or mode == "CROSS_MODAL":
        steps = [
            {"step": 1, "tool": "OPTICAL_SAR_FUSION", "parameters": {"target": target}, "description": "Joint optical-SAR cross-modal extraction"},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}, "description": "Metric area quantification (km²)"},
        ]
        return {"mode": "CROSS_MODAL", "task": "OPTICAL_SAR_COMPARISON", "steps": steps}

    # 8. Default: Scene Caption / VQA
    steps = [
        {"step": 1, "tool": "RS_CAPTION", "parameters": {}, "description": "Remote sensing scene captioning & land cover analysis"},
        {"step": 2, "tool": "RS_VQA", "parameters": {}, "description": "Visual Question Answering over computed spectral features"},
    ]
    return {"mode": "SINGLE_IMAGE", "task": "IMAGE_DESCRIPTION", "steps": steps}
