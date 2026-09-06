"""Context Engine managing multi-turn conversational memory, deictic pronoun resolution,
spatial constraints, and imagery session state per SatQuery AI Architecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class ResolvedSpatialContext:
    name: str | None = None
    bbox: list[float] | None = None  # [west, south, east, north]
    geometry: dict[str, Any] | None = None
    source: str = "unknown"  # "query_text", "active_aoi", "map_viewport", "conversation_history", "deictic_resolution"
    buffer_meters: float | None = None
    direction: str | None = None


@dataclass
class ResolvedTemporalContext:
    comparison_required: bool = False
    start_date: str | None = None
    end_date: str | None = None
    source: str = "default"  # "explicit_query", "relative_window", "context_history", "sensor_archive"
    reference_event: str | None = None


@dataclass
class ConversationTurn:
    turn_index: int
    query_text: str
    intent: str
    target: str
    location: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ContextEngine:
    """Manages active session context, multi-turn memory, and contextual reference resolution."""

    DEICTIC_HERE_TERMS = {
        "here", "this place", "this area", "this location", "the current area",
        "current map", "in this region", "the highlighted area", "the selected area",
        "this scene", "this map", "there", "that area", "that location"
    }

    PRONOUN_TARGET_TERMS = {
        "it", "the area", "the region", "this", "that", "these", "them"
    }

    FOLLOW_UP_TRIGGER_PATTERNS = [
        r"^(only|just)\s+(show\s+)?(vegetation|water|urban|buildings|forest|roads|damage)",
        r"^how\s+much(\s+changed|\s+area|\s+is\s+it)?\??$",
        r"^where(\s+is\s+it|\s+did\s+it\s+happen|\s+are\s+they)?\??$",
        r"^show\s+(me\s+)?(the\s+)?(polygons|map|evidence|boundaries)",
        r"^which\s+part(s)?(\s+changed|\s+are\s+affected)?\??$",
        r"^why\s+did\s+it\s+change\??$",
        r"^compare\s+with\s+",
    ]

    ENTITY_SWITCH_PATTERNS = [
        r"^(?:what|how)\s+about\s+([a-zA-Z0-9\s\-]+)\??$",
        r"^(?:and|what\s+of)\s+(?:in\s+)?([a-zA-Z0-9\s\-]+)\??$",
        r"^now\s+(?:look\s+at|check|analyze|switch\s+to)\s+([a-zA-Z0-9\s\-]+)\??$",
    ]

    def __init__(self, session_context: dict[str, Any] | None = None):
        self.raw_context = session_context or {}
        self.active_aoi = self.raw_context.get("active_aoi") or {}
        self.current_viewport = self.raw_context.get("current_viewport") or {}
        self.conversation_history: list[dict[str, Any]] = self.raw_context.get("conversation_history", [])
        self.image_count = int(self.raw_context.get("image_count", 0))
        self.has_images = bool(self.raw_context.get("has_images", False) or self.image_count > 0)
        self.selected_sensor = str(self.raw_context.get("sensor", "SENTINEL-2")).upper()

    def is_follow_up_query(self, query: str) -> bool:
        """Determines if the current query depends on previous conversational turns."""
        q = query.lower().strip()
        if not self.conversation_history:
            return False

        # Pattern match known follow-up syntaxes
        for pat in self.FOLLOW_UP_TRIGGER_PATTERNS:
            if re.search(pat, q):
                return True

        # Check entity-switch patterns (e.g. "what about thothukudi?")
        for pat in self.ENTITY_SWITCH_PATTERNS:
            if re.search(pat, q):
                return True

        # Short queries without an explicit location that reference pronouns or quantities
        tokens = set(q.split())
        if len(tokens) <= 5 and (tokens & self.PRONOUN_TARGET_TERMS):
            return True

        return False

    def resolve_entity_switch(self, query: str) -> dict[str, Any] | None:
        """
        Detects entity-switch follow-ups like 'what about thothukudi?'
        and carries forward the prior conversation intent, subject, and temporal window
        while replacing the active location with the new resolved entity.
        """
        q = query.lower().strip()
        matched_loc_str = None
        for pat in self.ENTITY_SWITCH_PATTERNS:
            m = re.search(pat, q)
            if m:
                matched_loc_str = m.group(1).strip()
                break

        if not matched_loc_str:
            return None

        # Clean trailing punctuation
        matched_loc_str = re.sub(r"[\?\.\,\!]+$", "", matched_loc_str).strip()

        from apps.agent.location_resolver import LocationResolver
        resolved_loc = LocationResolver.resolve(matched_loc_str, allow_fuzzy=True, allow_network=True)
        if not resolved_loc or not resolved_loc.is_valid:
            from apps.agent.geocoding import resolve_location
            loc_dict = resolve_location(matched_loc_str, allow_network=True)
            if loc_dict:
                loc_data = loc_dict
            else:
                return None
        else:
            loc_data = resolved_loc.to_dict()

        # Find the last established analysis intent from conversation history
        last_turn = self.conversation_history[-1] if self.conversation_history else {}
        inherited_intent = last_turn.get("intent") or "CHANGE_DETECTION"
        inherited_target = last_turn.get("target") or "surface_change"
        inherited_task = last_turn.get("task") or inherited_intent

        return {
            "is_entity_switch": True,
            "new_location": loc_data,
            "inherited_intent": inherited_task if "change" in str(inherited_task).lower() else inherited_intent,
            "inherited_target": inherited_target,
            "temporal": True,
            "raw_candidate": matched_loc_str,
        }

    def resolve_spatial_context(self, query: str) -> ResolvedSpatialContext:
        """Resolves location and spatial bounding boxes from query or contextual state."""
        q = query.lower().strip()

        # 1. Check for deictic references ("here", "this area", "the map")
        has_deictic = any(re.search(rf"\b{re.escape(term)}\b", q) for term in self.DEICTIC_HERE_TERMS)

        # 2. Check for explicit buffer/direction phrases ("within 5 km of Coimbatore", "north of the lake")
        buffer_meters = None
        buffer_match = re.search(r"within\s+(\d+(?:\.\d+)?)\s*(km|kilometers|m|meters)\s+of\s+([a-zA-Z\s]+)", q)
        if buffer_match:
            dist = float(buffer_match.group(1))
            unit = buffer_match.group(2)
            buffer_meters = dist * 1000.0 if "km" in unit else dist

        direction = None
        dir_match = re.search(r"\b(north|south|east|west|northeast|northwest|southeast|southwest)\s+of\s+([a-zA-Z\s]+)", q)
        if dir_match:
            direction = dir_match.group(1)

        # 3. If explicit place mentioned in query, extract it
        from apps.agent.geocoding import resolve_location
        explicit_loc = resolve_location(query, self.raw_context)

        if explicit_loc and explicit_loc.get("name") and not has_deictic:
            return ResolvedSpatialContext(
                name=explicit_loc.get("name"),
                bbox=explicit_loc.get("bbox"),
                geometry=explicit_loc.get("geometry"),
                source="query_text",
                buffer_meters=buffer_meters,
                direction=direction,
            )

        # 4. If deictic or follow-up, resolve against active AOI or viewport
        if has_deictic or not explicit_loc:
            # Check active AOI first
            if self.active_aoi and self.active_aoi.get("name"):
                return ResolvedSpatialContext(
                    name=self.active_aoi.get("name"),
                    bbox=self.active_aoi.get("bbox"),
                    geometry=self.active_aoi.get("geometry"),
                    source="active_aoi",
                    buffer_meters=buffer_meters,
                    direction=direction,
                )

            # Check viewport second
            if self.current_viewport:
                vp = self.current_viewport
                vp_bbox = None
                if isinstance(vp.get("bbox"), (list, tuple)) and len(vp["bbox"]) == 4:
                    vp_bbox = [float(x) for x in vp["bbox"]]
                elif all(k in vp for k in ("west", "south", "east", "north")):
                    vp_bbox = [float(vp["west"]), float(vp["south"]), float(vp["east"]), float(vp["north"])]

                if vp_bbox:
                    return ResolvedSpatialContext(
                        name=self.active_aoi.get("name") or "Selected Map Viewport",
                        bbox=vp_bbox,
                        source="map_viewport",
                        buffer_meters=buffer_meters,
                        direction=direction,
                    )

            # Check conversation history third
            last_location = self.get_last_location()
            if last_location:
                return ResolvedSpatialContext(
                    name=last_location.get("name"),
                    bbox=last_location.get("bbox"),
                    geometry=last_location.get("geometry"),
                    source="conversation_history",
                    buffer_meters=buffer_meters,
                    direction=direction,
                )

        # Fallback to whatever resolve_location found or empty
        if explicit_loc:
            return ResolvedSpatialContext(
                name=explicit_loc.get("name"),
                bbox=explicit_loc.get("bbox"),
                geometry=explicit_loc.get("geometry"),
                source=explicit_loc.get("source", "geocoding_lookup"),
                buffer_meters=buffer_meters,
                direction=direction,
            )

        return ResolvedSpatialContext(name=None, bbox=None, source="unresolved")

    def resolve_temporal_context(self, query: str) -> ResolvedTemporalContext:
        """Resolves temporal range, comparison requirements, and dates."""
        q = query.lower().strip()
        now = date.today()

        # Check explicit relative periods
        if "last 6 months" in q or "past 6 months" in q:
            t1 = (now - timedelta(days=182)).isoformat()
            t2 = now.isoformat()
            return ResolvedTemporalContext(comparison_required=True, start_date=t1, end_date=t2, source="relative_window")

        if "last year" in q or "past year" in q or "last 12 months" in q:
            t1 = (now - timedelta(days=365)).isoformat()
            t2 = now.isoformat()
            return ResolvedTemporalContext(comparison_required=True, start_date=t1, end_date=t2, source="relative_window")

        if "last 2 years" in q or "past 2 years" in q:
            t1 = (now - timedelta(days=730)).isoformat()
            t2 = now.isoformat()
            return ResolvedTemporalContext(comparison_required=True, start_date=t1, end_date=t2, source="relative_window")

        # Year matching e.g. "between 2024 and 2026" or "from 2023 to 2025"
        year_match = re.search(r"(?:between|from)\s+(\d{4})\s+(?:and|to)\s+(\d{4})", q)
        if year_match:
            y1, y2 = year_match.group(1), year_match.group(2)
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=f"{y1}-01-01",
                end_date=f"{y2}-12-31",
                source="explicit_query",
            )

        # Pre-event / post-event detection e.g. "before the flood"
        if "before the flood" in q or "pre-flood" in q:
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date="2024-10-01",
                end_date="2024-11-05",
                source="reference_event",
                reference_event="flood_event",
            )

        # General change or comparison request implies temporal comparison
        is_temporal = any(w in q for w in ["change", "changed", "changing", "difference", "before and after", "expansion", "shrink", "loss", "growth"])
        if is_temporal:
            # Default to 1-2 year baseline comparison window if unspecified
            start_date = (now - timedelta(days=540)).isoformat()
            end_date = now.isoformat()
            return ResolvedTemporalContext(comparison_required=True, start_date=start_date, end_date=end_date, source="sensor_archive")

        # Single observation: latest
        return ResolvedTemporalContext(
            comparison_required=False,
            start_date=(now - timedelta(days=60)).isoformat(),
            end_date=now.isoformat(),
            source="latest_observation",
        )

    def get_last_location(self) -> dict[str, Any] | None:
        """Returns the most recent location mentioned in the conversation."""
        if self.active_aoi and self.active_aoi.get("name"):
            return self.active_aoi

        for turn in reversed(self.conversation_history):
            loc = turn.get("location")
            if loc and isinstance(loc, dict) and loc.get("name"):
                return loc
            if loc and isinstance(loc, str) and loc.strip():
                return {"name": loc.strip()}

        return None

    def get_last_target(self) -> str | None:
        """Returns the most recent geospatial target (e.g. vegetation, water, urban)."""
        for turn in reversed(self.conversation_history):
            target = turn.get("target")
            if target and target not in ("general", "unknown"):
                return str(target)
        return None

    def get_last_metrics(self) -> dict[str, Any]:
        """Returns the quantitative metrics computed in the previous turn."""
        for turn in reversed(self.conversation_history):
            m = turn.get("metrics")
            if m and isinstance(m, dict):
                return m
        return {}

    def update_history(self, query_text: str, intent: str, target: str, location: str | None, metrics: dict[str, Any]) -> None:
        """Appends an execution turn to conversation history."""
        turn = {
            "turn_index": len(self.conversation_history) + 1,
            "query_text": query_text,
            "intent": intent,
            "target": target,
            "location": location,
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.conversation_history.append(turn)
        # Keep last 15 turns
        if len(self.conversation_history) > 15:
            self.conversation_history = self.conversation_history[-15:]
        self.raw_context["conversation_history"] = self.conversation_history
