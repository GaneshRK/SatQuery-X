"""Agent Query Understander supporting 17 intents and conversational follow-ups per §7 & §24."""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryIntent:
    intent: str  # One of standard intents
    target: str  # e.g., "water", "vegetation", "buildings", "infrastructure", "general"
    operation: str  # "detect", "count", "segment", "change_map", "describe", "filter_previous"
    temporal: bool = False
    cross_modal: bool = False
    spatial_filter: dict[str, Any] = field(default_factory=dict)
    requested_output: list[str] = field(default_factory=lambda: ["answer", "confidence", "evidence"])
    raw_text: str = ""
    is_follow_up: bool = False
    location: dict[str, Any] = field(default_factory=dict)
    time_range: dict[str, str] = field(default_factory=dict)
    clarification_required: bool = False
    clarification_prompt: str | None = None
    clarification_options: list[dict[str, str]] = field(default_factory=list)


def understand_query(text: str, session_context: dict[str, Any] | None = None) -> QueryIntent:
    session_context = session_context or {}
    q = text.lower().strip()
    pair_type = session_context.get("pair_type")
    image_count = session_context.get("image_count", 1 if session_context.get("has_images") else 0)
    history = session_context.get("conversation_history", [])

    # Check for conversational follow-up keywords ("only show", "how many", "zoom in", "which of these")
    is_follow_up = False
    if history and any(k in q for k in ("only show", "filter", "which of these", "how many of them", "largest")):
        is_follow_up = True

    # Location resolution from query or session context
    from apps.agent.query_optimizer import QueryOptimizer
    from django.utils import timezone
    optimizer = QueryOptimizer()
    location = {}
    for key, loc in optimizer.KNOWN_LOCATIONS.items():
        if key in q:
            location = loc
            break
    if not location and session_context.get("active_aoi"):
        location = session_context["active_aoi"]
    elif not location and session_context.get("aoi_name") and session_context.get("bbox"):
        location = {
            "name": session_context["aoi_name"],
            "bbox": session_context["bbox"],
            "coords": session_context.get("centroid", [80.25, 13.05]),
        }

    now = timezone.now().date()
    time_range = optimizer._resolve_time_range(q, now)

    # Ambiguity check (§57)
    is_ambiguous = False
    clarification_prompt = None
    clarification_options = []
    if image_count == 0 and not location and not session_context.get("has_images"):
        ambiguous_triggers = [
            "what is changing here", "what changed here", "what is happening here",
            "is there change", "has the city expanded here", "is this area growing",
            "any change here", "what is happening in this area", "what is changing in this area",
            "what is changing?", "what is changing"
        ]
        if any(trig in q for trig in ambiguous_triggers) or q in ("what changed?", "what changed"):
            is_ambiguous = True
            clarification_prompt = (
                "I can analyze surface changes, but I need to know where you mean. "
                "Give me a place name, coordinates, or draw an area on the map."
            )
            clarification_options = [
                {"label": "Pollachi Agricultural Belt", "query": "What is changing around Pollachi?"},
                {"label": "Kaziranga National Park", "query": "Is there flooding around Kaziranga?"},
                {"label": "Chennai Metropolitan Area", "query": "Show me the latest satellite observation of Chennai"},
            ]

    # Helper to construct QueryIntent with common resolved fields
    def _make_intent(**kwargs):
        defaults = {
            "raw_text": text,
            "is_follow_up": is_follow_up,
            "location": location,
            "time_range": time_range,
            "clarification_required": is_ambiguous,
            "clarification_prompt": clarification_prompt,
            "clarification_options": clarification_options,
        }
        defaults.update(kwargs)
        return QueryIntent(**defaults)

    # 0. AMBIGUOUS CLARIFICATION QUERY
    if is_ambiguous:
        return _make_intent(
            intent="CLARIFICATION",
            target="location_and_aoi",
            operation="request_clarification",
            clarification_required=True,
        )

    # 0b. LATEST OBSERVATION
    if any(k in q for k in ("latest satellite observation", "latest observation", "latest clear satellite", "show satellite image", "latest satellite image")):
        sensor = "SENTINEL-1" if "sar" in q or "radar" in q else "SENTINEL-2"
        return _make_intent(
            intent="LATEST_OBSERVATION",
            target=sensor,
            operation="latest_observation",
        )

    # 1. OPTICAL + SAR FUSION (High priority to prevent water/building false matches)
    if ("optical" in q and "sar" in q) or ("radar" in q and "optical" in q) or pair_type == "CROSS_MODAL":
        return _make_intent(
            intent="optical_sar_fusion",
            target="built_up_and_water" if ("built" in q and "water" in q) else "optical_sar_features",
            operation="cross_modal_analysis",
            cross_modal=True,
        )

    # 2. SATELLITE_SEARCH
    if any(k in q for k in ("search satellite", "find sentinel", "search scene", "download imagery", "copernicus")):
        sensor = "SENTINEL-1" if "sar" in q or "radar" in q else "SENTINEL-2"
        return _make_intent(
            intent="SATELLITE_SEARCH",
            target=sensor,
            operation="search_catalog",
        )

    # 3. MISSION MODE
    if "mission" in q or "analyze this region" in q:
        return _make_intent(
            intent="mission",
            target="urban_expansion" if "urban" in q else "flood_impact",
            operation="mission_workflow",
            temporal=(pair_type == "BI_TEMPORAL" or "expansion" in q or "change" in q),
        )

    # 4. SPATIAL GROUNDING / HIGHLIGHT
    if any(k in q for k in ("highlight", "locate", "outline", "find the")):
        target = "water" if "water" in q else ("buildings" if "building" in q else "general")
        return _make_intent(
            intent="grounding",
            target=target,
            operation="locate_and_segment",
        )

    # 5. CHANGE VQA / BI-TEMPORAL
    if (
        "between these two dates" in q
        or "between these two" in q
        or "what changed" in q
        or "what is changing" in q
        or "what has changed" in q
        or ("increased" in q and "decreased" in q)
        or ("increase" in q and "decrease" in q)
        or "remained unchanged" in q
    ):
        target = "built_up" if ("built-up" in q or "built_up" in q or "building" in q) else "surface_change"
        return _make_intent(
            intent="change_vqa",
            target=target,
            operation="change_analysis",
            temporal=True,
        )

    # 6. CAPTION / DESCRIBE
    if q.startswith("describe") or "caption" in q or "overview of this image" in q:
        return _make_intent(
            intent="caption",
            target="land_cover",
            operation="describe",
        )

    # 7. VQA / QUESTION ANSWERING
    if q.startswith("what is the resolution") or q.startswith("what sensor") or q.startswith("is this"):
        return _make_intent(
            intent="vqa",
            target="metadata_vqa",
            operation="vqa",
        )

    # 8. OBJECT_COUNTING ("How many buildings", "count structures", "number of ships/vehicles")
    if any(k in q for k in ("how many", "count ", "number of")):
        target = "buildings" if "building" in q or "structure" in q or "house" in q else ("water" if "water" in q else "objects")
        return _make_intent(
            intent="OBJECT_COUNTING",
            target=target,
            operation="count",
        )

    # 9. WATER_DETECTION / FLOOD INUNDATION
    if any(k in q for k in ("water", "river", "lake", "flood", "wetland", "reservoir", "inundat")):
        if any(w in q for w in ("change", "changing", "changed")) or pair_type == "BI_TEMPORAL":
            return _make_intent(
                intent="CHANGE_DETECTION",
                target="water_flood",
                operation="change_map",
                temporal=True,
            )
        return _make_intent(
            intent="WATER_DETECTION",
            target="water",
            operation="segment",
        )

    # 10. VEGETATION_ANALYSIS / AGRICULTURE_ANALYSIS
    if any(k in q for k in ("vegetation", "forest", "crop", "farm", "canopy", "ndvi", "green")):
        if any(w in q for w in ("change", "changing", "changed", "loss", "deforest")) or pair_type == "BI_TEMPORAL":
            return _make_intent(
                intent="CHANGE_DETECTION",
                target="vegetation_loss",
                operation="change_map",
                temporal=True,
            )
        return _make_intent(
            intent="VEGETATION_ANALYSIS",
            target="vegetation",
            operation="calculate_ndvi_and_segment",
        )

    # 11. BUILDING_ANALYSIS / URBAN_ANALYSIS
    if any(k in q for k in ("building", "urban", "infrastructure", "city", "built-up", "settlement", "road", "runway")):
        if any(w in q for w in ("change", "changing", "changed", "expansion")) or pair_type == "BI_TEMPORAL":
            return _make_intent(
                intent="CHANGE_DETECTION",
                target="urban_expansion",
                operation="change_map",
                temporal=True,
            )
        return _make_intent(
            intent="BUILDING_ANALYSIS",
            target="buildings",
            operation="detect_and_measure",
        )

    # 12. GENERAL CHANGE DETECTION
    if any(w in q for w in ("change", "changing", "changed", "differen", "expansion", "transition")) or pair_type == "BI_TEMPORAL":
        return _make_intent(
            intent="CHANGE_DETECTION",
            target="bi_temporal_surface_change",
            operation="change_map",
            temporal=True,
        )

    # Default: IMAGE_DESCRIPTION / CAPTION
    return _make_intent(
        intent="caption",
        target="general_terrain",
        operation="scene_description",
    )


