"""Agent Query Understander supporting 17 intents and conversational follow-ups per §7 & §24."""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryIntent:
    intent: str  # One of 17 standard intents
    target: str  # e.g., "water", "vegetation", "buildings", "infrastructure", "general"
    operation: str  # "detect", "count", "segment", "change_map", "describe", "filter_previous"
    temporal: bool = False
    cross_modal: bool = False
    spatial_filter: dict[str, Any] = field(default_factory=dict)
    requested_output: list[str] = field(default_factory=lambda: ["answer", "confidence", "evidence"])
    raw_text: str = ""
    is_follow_up: bool = False


def understand_query(text: str, session_context: dict[str, Any] | None = None) -> QueryIntent:
    session_context = session_context or {}
    q = text.lower().strip()
    pair_type = session_context.get("pair_type")
    image_count = session_context.get("image_count", 1)
    history = session_context.get("conversation_history", [])

    # Check for conversational follow-up keywords ("only show", "how many", "zoom in", "which of these")
    is_follow_up = False
    if history and any(k in q for k in ("only show", "filter", "which of these", "how many of them", "largest")):
        is_follow_up = True

    # 1. OPTICAL + SAR FUSION (High priority to prevent water/building false matches)
    if ("optical" in q and "sar" in q) or ("radar" in q and "optical" in q) or pair_type == "CROSS_MODAL":
        return QueryIntent(
            intent="optical_sar_fusion",
            target="built_up_and_water" if ("built" in q and "water" in q) else "optical_sar_features",
            operation="cross_modal_analysis",
            cross_modal=True,
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 2. SATELLITE_SEARCH
    if any(k in q for k in ("search satellite", "find sentinel", "search scene", "download imagery", "copernicus")):
        sensor = "SENTINEL-1" if "sar" in q or "radar" in q else "SENTINEL-2"
        return QueryIntent(
            intent="SATELLITE_SEARCH",
            target=sensor,
            operation="search_catalog",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 3. MISSION MODE
    if "mission" in q or "analyze this region" in q:
        return QueryIntent(
            intent="mission",
            target="urban_expansion" if "urban" in q else "flood_impact",
            operation="mission_workflow",
            temporal=(pair_type == "BI_TEMPORAL" or "expansion" in q or "change" in q),
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 4. SPATIAL GROUNDING / HIGHLIGHT
    if any(k in q for k in ("highlight", "locate", "outline", "find the")):
        target = "water" if "water" in q else ("buildings" if "building" in q else "general")
        return QueryIntent(
            intent="grounding",
            target=target,
            operation="locate_and_segment",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 5. CHANGE VQA / BI-TEMPORAL
    if (
        "between these two dates" in q
        or "between these two" in q
        or "what changed" in q
        or ("increased" in q and "decreased" in q)
        or ("increase" in q and "decrease" in q)
        or "remained unchanged" in q
    ):
        target = "built_up" if ("built-up" in q or "built_up" in q or "building" in q) else "surface_change"
        return QueryIntent(
            intent="change_vqa",
            target=target,
            operation="change_analysis",
            temporal=True,
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 6. CAPTION / DESCRIBE
    if q.startswith("describe") or "caption" in q or "overview of this image" in q:
        return QueryIntent(
            intent="caption",
            target="land_cover",
            operation="describe",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 7. VQA / QUESTION ANSWERING
    if q.startswith("what is the resolution") or q.startswith("what sensor") or q.startswith("is this"):
        return QueryIntent(
            intent="vqa",
            target="metadata_vqa",
            operation="vqa",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 8. OBJECT_COUNTING ("How many buildings", "count structures", "number of ships/vehicles")
    if any(k in q for k in ("how many", "count ", "number of")):
        target = "buildings" if "building" in q or "structure" in q or "house" in q else ("water" if "water" in q else "objects")
        return QueryIntent(
            intent="OBJECT_COUNTING",
            target=target,
            operation="count",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 9. WATER_DETECTION / FLOOD INUNDATION
    if any(k in q for k in ("water", "river", "lake", "flood", "wetland", "reservoir", "inundat")):
        if "change" in q or pair_type == "BI_TEMPORAL":
            return QueryIntent(
                intent="CHANGE_DETECTION",
                target="water_flood",
                operation="change_map",
                temporal=True,
                raw_text=text,
                is_follow_up=is_follow_up,
            )
        return QueryIntent(
            intent="WATER_DETECTION",
            target="water",
            operation="segment",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 10. VEGETATION_ANALYSIS / AGRICULTURE_ANALYSIS
    if any(k in q for k in ("vegetation", "forest", "crop", "farm", "canopy", "ndvi", "green")):
        if "change" in q or "loss" in q or "deforest" in q or pair_type == "BI_TEMPORAL":
            return QueryIntent(
                intent="CHANGE_DETECTION",
                target="vegetation_loss",
                operation="change_map",
                temporal=True,
                raw_text=text,
                is_follow_up=is_follow_up,
            )
        return QueryIntent(
            intent="VEGETATION_ANALYSIS",
            target="vegetation",
            operation="calculate_ndvi_and_segment",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 11. BUILDING_ANALYSIS / URBAN_ANALYSIS
    if any(k in q for k in ("building", "urban", "infrastructure", "city", "built-up", "settlement", "road", "runway")):
        if "change" in q or "expansion" in q or pair_type == "BI_TEMPORAL":
            return QueryIntent(
                intent="CHANGE_DETECTION",
                target="urban_expansion",
                operation="change_map",
                temporal=True,
                raw_text=text,
                is_follow_up=is_follow_up,
            )
        return QueryIntent(
            intent="BUILDING_ANALYSIS",
            target="buildings",
            operation="detect_and_measure",
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # 12. GENERAL CHANGE DETECTION
    if "change" in q or pair_type == "BI_TEMPORAL":
        return QueryIntent(
            intent="CHANGE_DETECTION",
            target="bi_temporal_surface_change",
            operation="change_map",
            temporal=True,
            raw_text=text,
            is_follow_up=is_follow_up,
        )

    # Default: IMAGE_DESCRIPTION / CAPTION
    return QueryIntent(
        intent="caption",
        target="general_terrain",
        operation="scene_description",
        raw_text=text,
        is_follow_up=is_follow_up,
    )

