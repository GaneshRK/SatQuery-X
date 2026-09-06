"""Agent Query Understander supporting 20+ fine-grained intents, deictic pronoun resolution,
multi-location comparison, and conversational follow-ups per §7, §24, §57.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.agent.context_engine import ContextEngine, ResolvedSpatialContext, ResolvedTemporalContext
from apps.agent.intent_ontology import GeoIntent, classify_geo_intent, extract_multiple_locations


@dataclass
class QueryIntent:
    intent: str  # One of standard intent keys
    target: str  # e.g., "water", "vegetation", "buildings", "infrastructure", "surface_change", "general"
    operation: str  # "detect", "count", "segment", "change_map", "describe", "filter_previous", "region_comparison"
    temporal: bool = False
    cross_modal: bool = False
    spatial_filter: Dict[str, Any] = field(default_factory=dict)
    requested_output: List[str] = field(default_factory=lambda: ["answer", "confidence", "evidence"])
    raw_text: str = ""
    is_follow_up: bool = False
    location: Dict[str, Any] = field(default_factory=dict)
    time_range: Dict[str, str] = field(default_factory=dict)
    clarification_required: bool = False
    clarification_prompt: Optional[str] = None
    clarification_options: List[Dict[str, str]] = field(default_factory=list)
    geo_intent: Optional[GeoIntent] = None
    missing_data: List[str] = field(default_factory=list)
    auto_search_required: bool = False
    multi_locations: List[Dict[str, Any]] = field(default_factory=list)
    context_source: str = ""


def understand_query(text: str, session_context: Optional[Dict[str, Any]] = None) -> QueryIntent:
    session_context = session_context or {}
    q = text.lower().strip()
    pair_type = session_context.get("pair_type")
    image_count = session_context.get("image_count", 1 if session_context.get("has_images") else 0)

    # 1. Initialize ContextEngine for spatial, temporal, and multi-turn tracking
    context_engine = ContextEngine(session_context)

    # 2. Resolve spatial context (deictic "here", active AOI, map viewport, or text lookup)
    resolved_spatial = context_engine.resolve_spatial_context(text)
    if resolved_spatial and resolved_spatial.name:
        location = {
            "name": resolved_spatial.name,
            "bbox": resolved_spatial.bbox,
            "source": resolved_spatial.source,
            "geometry": resolved_spatial.geometry,
            "coords": [
                (resolved_spatial.bbox[0] + resolved_spatial.bbox[2]) / 2.0,
                (resolved_spatial.bbox[1] + resolved_spatial.bbox[3]) / 2.0,
            ] if resolved_spatial.bbox and len(resolved_spatial.bbox) >= 4 else None,
        }
    else:
        from apps.agent.geocoding import resolve_location
        location = resolve_location(text, session_context) or {}

    # 3. Resolve temporal context
    resolved_temporal = context_engine.resolve_temporal_context(text)
    time_range = {}
    if resolved_temporal.start_date and resolved_temporal.end_date:
        time_range = {
            "start": resolved_temporal.start_date,
            "end": resolved_temporal.end_date,
            "source": resolved_temporal.source,
        }
    else:
        from apps.agent.query_optimizer import QueryOptimizer
        from django.utils import timezone
        optimizer = QueryOptimizer()
        now = timezone.now().date()
        time_range = optimizer._resolve_time_range(q, now)

    # 4. Check for conversational follow-up
    is_follow_up = context_engine.is_follow_up_query(text)

    # 4b. Check for entity-switch follow-up (e.g. "what about thothukudi?")
    entity_switch = context_engine.resolve_entity_switch(text)
    if entity_switch:
        new_loc = entity_switch["new_location"]
        inherited_intent = entity_switch["inherited_intent"]
        inherited_target = entity_switch["inherited_target"]
        return QueryIntent(
            raw_text=text,
            intent="CHANGE_DETECTION" if "change" in str(inherited_intent).lower() else str(inherited_intent),
            target=str(inherited_target),
            operation="change_analysis" if "change" in str(inherited_intent).lower() else "inspect",
            location=new_loc,
            time_range=time_range,
            temporal=entity_switch.get("temporal", True),
            is_follow_up=True,
            geo_intent=GeoIntent.BI_TEMPORAL_CHANGE,
            context_source="entity_switch_follow_up",
            auto_search_required=True,
            missing_data=["temporal_pair_t1", "temporal_pair_t2"],
        )

    # 5. Classify ontology intent
    geo_intent, classified_target, extra_info = classify_geo_intent(text, context_engine)

    # 6. Ambiguity check (§57)
    # Ambiguous triggers only fire when there is truly NO location, NO image, NO AOI, NO viewport
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

    # Helper to construct QueryIntent
    def _make_intent(**kwargs):
        defaults = {
            "raw_text": text,
            "is_follow_up": is_follow_up,
            "location": location,
            "time_range": time_range,
            "clarification_required": is_ambiguous,
            "clarification_prompt": clarification_prompt,
            "clarification_options": clarification_options,
            "geo_intent": geo_intent,
            "missing_data": [],
            "auto_search_required": False,
            "multi_locations": extra_info.get("multi_locations", []),
            "context_source": resolved_spatial.source if resolved_spatial else "",
        }
        defaults.update(kwargs)

        # Detect data gap for temporal change operations
        if defaults.get("temporal") and image_count < 2:
            defaults["missing_data"] = ["temporal_pair_t2"] if image_count == 1 else ["temporal_pair_t1", "temporal_pair_t2"]
            defaults["auto_search_required"] = True

        return QueryIntent(**defaults)

    # 0. AMBIGUOUS CLARIFICATION QUERY
    if is_ambiguous:
        return _make_intent(
            intent="CLARIFICATION",
            target="location_and_aoi",
            operation="request_clarification",
            clarification_required=True,
            geo_intent=GeoIntent.CLARIFICATION,
        )

    # 0a. REGION COMPARISON QUERY (Multi-location)
    if geo_intent == GeoIntent.REGION_COMPARISON:
        prompt = extra_info.get("structured_comparison_prompt")
        options = extra_info.get("comparison_options", [])
        return _make_intent(
            intent="REGION_COMPARISON",
            target=classified_target,
            operation="region_comparison",
            clarification_required=bool(prompt),
            clarification_prompt=prompt,
            clarification_options=options,
            multi_locations=extra_info.get("multi_locations", []),
            geo_intent=geo_intent,
            temporal=True,
        )

    # 0b. FOLLOW-UP REFINEMENT
    if geo_intent == GeoIntent.FOLLOW_UP_REFINEMENT:
        follow_up_action = extra_info.get("follow_up_action", "filter_previous")
        return _make_intent(
            intent="FOLLOW_UP_REFINEMENT",
            target=classified_target,
            operation=follow_up_action,
            is_follow_up=True,
            geo_intent=geo_intent,
        )

    # 0c. LATEST OBSERVATION
    if any(k in q for k in ("latest satellite observation", "latest observation", "latest clear satellite", "show satellite image", "latest satellite image", "latest condition", "live footage", "live satellite", "latest flood", "latest monitoring")):
        sensor = "SENTINEL-1" if ("sar" in q or "radar" in q) else "SENTINEL-2"
        return _make_intent(
            intent="LATEST_OBSERVATION",
            target=sensor,
            operation="latest_observation",
        )

    # 0d. GENERAL EARTH KNOWLEDGE (Geography & Earth features without local AOI/raster)
    if any(k in q for k in (
        "largest mountain", "highest mountain", "tallest mountain", "highest peak", "tallest peak",
        "deepest ocean", "longest river", "what is the largest mountain", "what is the highest peak",
        "highest point on earth", "largest volcano", "greatest depth", "deepest trench"
    )) and not session_context.get("has_images"):
        return _make_intent(
            intent="GENERAL_EARTH_KNOWLEDGE",
            target="earth_geography",
            operation="explain_geography",
            temporal=False,
            geo_intent=GeoIntent.GENERAL_EARTH_KNOWLEDGE,
        )

    # 0e. THERMAL HOTSPOT / SPATIAL HEATMAP VISUALIZATION
    if any(k in q for k in (
        "heat coordinate", "heat cordinates", "heat coordinates", "visualize the heat", "visualize heat",
        "hotspot", "hotspots", "thermal", "temperature", "heat map", "heatmap"
    )):
        last_loc = context_engine.get_last_location() or {}
        loc_to_use = location if location else last_loc
        last_target = context_engine.get_last_target() or "spatial_change_hotspots"
        return _make_intent(
            intent="THERMAL_HOTSPOT",
            target=last_target,
            operation="visualize_hotspots",
            temporal=False,
            is_follow_up=bool(last_loc),
            location=loc_to_use,
            geo_intent=GeoIntent.THERMAL_HOTSPOT,
        )

    # 1. OPTICAL + SAR FUSION (High priority to prevent false matches)
    if ("optical" in q and "sar" in q) or ("radar" in q and "optical" in q) or pair_type == "CROSS_MODAL":
        return _make_intent(
            intent="optical_sar_fusion",
            target="built_up_and_water" if ("built" in q and "water" in q) else "optical_sar_features",
            operation="cross_modal_analysis",
            cross_modal=True,
        )

    # 2. SATELLITE_SEARCH
    if any(k in q for k in ("search satellite", "find sentinel", "search scene", "download imagery", "copernicus")):
        sensor = "SENTINEL-1" if ("sar" in q or "radar" in q) else "SENTINEL-2"
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
        or "what the changes" in q
        or "changes in here" in q
        or "change in here" in q
        or "changes here" in q
        or "what are the changes" in q
        or "any change" in q
        or "surface dynamic" in q
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
        target = "buildings" if ("building" in q or "structure" in q or "house" in q) else ("water" if "water" in q else "objects")
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
        if any(w in q for w in ("change", "changing", "changed", "loss", "deforest", "decrease", "decreased", "reduction", "decline", "declined", "shrink", "shrinkage", "stress", "degraded", "drop")) or pair_type == "BI_TEMPORAL":
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
