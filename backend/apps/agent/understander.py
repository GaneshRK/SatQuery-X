"""Understander component per §8.1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryIntent:
    intent: str  # vqa, caption, grounding, change_detection, change_vqa, optical_sar_fusion, mission
    target: str  # e.g., "built_up", "water", "vegetation", "general"
    operation: str  # "describe", "highlight", "change_assessment", "joint_extraction", "increase_check"
    temporal: bool = False
    cross_modal: bool = False
    spatial_scope: str = "entire_aoi"
    requested_output: list[str] = field(default_factory=lambda: ["answer", "confidence"])
    raw_text: str = ""


def understand_query(text: str, session_context: dict[str, Any] | None = None) -> QueryIntent:
    session_context = session_context or {}
    q = text.lower().strip()
    pair_type = session_context.get("pair_type")
    image_count = session_context.get("image_count", 1)

    # 1. Mission Mode check (comprehensive regional intelligence analysis)
    if "analyze this region" in q or "urban expansion" in q or "comprehensive analysis" in q or "mission" in q:
        return QueryIntent(
            intent="mission",
            target="urban_expansion",
            operation="mission_intelligence_workflow",
            temporal=(pair_type == "BI_TEMPORAL" or image_count >= 2),
            cross_modal=(pair_type == "CROSS_MODAL"),
            requested_output=["answer", "change_map", "geojson", "area_km2", "report", "confidence"],
            raw_text=text,
        )

    # 2. Cross-Modal Optical + SAR joint extraction
    # "Use the optical and SAR images together to identify built-up and water-covered regions."
    if (
        ("optical" in q and "sar" in q)
        or "cross-modal" in q
        or pair_type == "CROSS_MODAL"
        or ("radar" in q and "optical" in q)
    ):
        target = "built_up_and_water" if ("water" in q or "built-up" in q) else "general"
        return QueryIntent(
            intent="optical_sar_fusion",
            target=target,
            operation="joint_extraction",
            temporal=False,
            cross_modal=True,
            requested_output=["answer", "class_regions", "confidence"],
            raw_text=text,
        )

    # 3. Bi-Temporal Change-based VQA
    # "Has the built-up area increased, decreased, or remained unchanged?"
    # "What changed between these two dates, and where did the change occur?"
    if (
        "increased" in q
        or "decreased" in q
        or "what changed" in q
        or "between these two dates" in q
        or "remained unchanged" in q
        or (pair_type == "BI_TEMPORAL" and ("change" in q or "where" in q or "?" in q))
    ):
        target = "built_up" if "built-up" in q or "urban" in q else ("water" if "water" in q else "surface_change")
        operation = "increase_check" if ("increased" in q or "decreased" in q) else "change_assessment"
        return QueryIntent(
            intent="change_vqa",
            target=target,
            operation=operation,
            temporal=True,
            cross_modal=False,
            requested_output=["answer", "change_map", "area_km2", "confidence"],
            raw_text=text,
        )

    # 4. Pure Change Detection
    if "change map" in q or "detect change" in q or "highlight change" in q or pair_type == "BI_TEMPORAL":
        return QueryIntent(
            intent="change_detection",
            target="surface_change",
            operation="change_map",
            temporal=True,
            cross_modal=False,
            requested_output=["change_map", "geojson", "area_km2", "confidence"],
            raw_text=text,
        )

    # 5. Text-Guided Grounding
    # "Highlight the water body referred to in the query."
    # "Find the buildings/vegetation in this image."
    if "highlight" in q or "locate" in q or "ground" in q or "find the" in q or "box" in q:
        target = "water" if "water" in q else ("built_up" if "built-up" in q or "building" in q else "vegetation")
        return QueryIntent(
            intent="grounding",
            target=target,
            operation="highlight",
            temporal=False,
            cross_modal=False,
            requested_output=["boxes", "overlay", "geojson", "confidence"],
            raw_text=text,
        )

    # 6. Scene Captioning / Description
    # "Describe the land-cover and major objects visible in this image."
    if "describe" in q or "caption" in q or "summarize" in q or "overview" in q:
        return QueryIntent(
            intent="caption",
            target="land_cover",
            operation="describe",
            temporal=False,
            cross_modal=False,
            requested_output=["caption", "confidence"],
            raw_text=text,
        )

    # 7. Default Single-Image VQA
    target = "water" if "water" in q else ("vegetation" if "vegetation" in q else "general")
    return QueryIntent(
        intent="vqa",
        target=target,
        operation="visual_qa",
        temporal=False,
        cross_modal=False,
        requested_output=["answer", "confidence"],
        raw_text=text,
    )
