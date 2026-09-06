"""
SatQuery-X conversational context engine.

Responsibilities
----------------
- Maintain multi-turn conversational state.
- Resolve references such as "here", "this area", "it", and "them".
- Preserve actual map/AOI context.
- Preserve actual imagery/session metadata.
- Resolve explicit spatial information without fabricating geometry.
- Resolve temporal expressions without inventing historical dates.
- Identify when clarification is required.

Important
---------
This module is a CONTEXT engine.

It is not a scientific analysis engine.

It must never invent:
- coordinates
- bounding boxes
- imagery
- sensor information
- acquisition dates
- measurements
- confidence
- geospatial alignment
- satellite observations
"""

from __future__ import annotations

import calendar
import copy
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any


# ============================================================================
# Data contracts
# ============================================================================


@dataclass
class ResolvedSpatialContext:
    """
    Spatial context grounded from the query or existing session state.

    A location is considered spatially resolved only when actual geometry
    or a valid bounding box is available.

    A name by itself does not create geographic coordinates or an extent.
    """

    name: str | None = None
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None

    source: str = "unknown"

    buffer_meters: float | None = None
    direction: str | None = None

    is_resolved: bool = False
    requires_clarification: bool = False

    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bbox": self.bbox,
            "geometry": self.geometry,
            "source": self.source,
            "buffer_meters": self.buffer_meters,
            "direction": self.direction,
            "is_resolved": self.is_resolved,
            "requires_clarification": self.requires_clarification,
            "confidence": self.confidence,
        }


@dataclass
class ResolvedTemporalContext:
    """
    Temporal information grounded from the query/session.

    Dates are only returned when they are explicitly stated by the user,
    supplied by actual session imagery metadata, or otherwise grounded in
    existing application context.
    """

    comparison_required: bool = False

    start_date: str | None = None
    end_date: str | None = None

    source: str = "unresolved"

    reference_event: str | None = None

    is_resolved: bool = False
    requires_clarification: bool = False

    uncertainty_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_required": self.comparison_required,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source": self.source,
            "reference_event": self.reference_event,
            "is_resolved": self.is_resolved,
            "requires_clarification": self.requires_clarification,
            "uncertainty_notes": list(self.uncertainty_notes),
        }


@dataclass
class ConversationTurn:
    """Compact representation of one completed conversational turn."""

    turn_index: int
    query_text: str

    intent: str
    target: str

    location: str | dict[str, Any] | None = None

    metrics: dict[str, Any] = field(default_factory=dict)

    timestamp: str = field(
        default_factory=lambda: datetime.now(
            dt_timezone.utc
        ).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "query_text": self.query_text,
            "intent": self.intent,
            "target": self.target,
            "location": self.location,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }


# ============================================================================
# Context Engine
# ============================================================================


class ContextEngine:
    """
    Stateful conversational context resolver.

    Spatial priority
    ----------------
    1. Explicitly resolved query location
    2. Active map/AOI selection
    3. Current map viewport
    4. Previous grounded conversation location
    5. Unresolved

    Temporal priority
    -----------------
    1. Explicit query dates
    2. Explicit relative period
    3. Actual imagery/session dates
    4. Explicit event reference
    5. Unresolved

    No scientific defaults are introduced.

    In particular this class never assumes:
        - a city
        - a coordinate
        - a bounding box
        - Sentinel-1
        - Sentinel-2
        - Landsat
        - today's date as an observation date
        - a comparison baseline
        - a spatial buffer
        - a confidence score
    """

    # ------------------------------------------------------------------
    # Deictic expressions
    # ------------------------------------------------------------------

    DEICTIC_HERE_TERMS = {
        "here",
        "this place",
        "this area",
        "this location",
        "this point",
        "the current area",
        "current map",
        "in this region",
        "the highlighted area",
        "the selected area",
        "this scene",
        "this map",
        "there",
        "that area",
        "that location",
        "the area shown",
        "the place shown",
        "the selected region",
        "the highlighted region",
    }

    PRONOUN_TARGET_TERMS = {
        "it",
        "this",
        "that",
        "these",
        "them",
        "those",
        "the area",
        "the region",
        "the site",
        "the place",
    }

    # ------------------------------------------------------------------
    # Follow-up patterns
    # ------------------------------------------------------------------

    FOLLOW_UP_TRIGGER_PATTERNS = (
        r"^\s*what\s+about\b",
        r"^\s*how\s+about\b",
        r"^\s*and\s+what\s+about\b",
        r"^\s*what\s+else\b",
        r"^\s*also\b",
        r"^\s*compare\s+(?:it|this|that)\b",
        r"\bthe\s+same\s+(?:area|place|location|image|scene)\b",
        r"\bprevious\s+(?:image|scene|result|analysis)\b",
        r"\bearlier\s+(?:image|scene|result|analysis)\b",
        r"\bwhat\s+did\s+you\s+find\b",
        r"\bwhy\s+(?:is|was|did)\s+(?:it|this|that)\b",
        r"\bhow\s+much\s+(?:did|has)\s+(?:it|this|that)\b",
    )

    ENTITY_SWITCH_PATTERNS = (
        r"^\s*what\s+about\s+(.+?)\s*\??$",
        r"^\s*how\s+about\s+(.+?)\s*\??$",
        r"^\s*now\s+(?:check|analyze|look\s+at|show)\s+(.+?)\s*\??$",
        r"^\s*instead\s+(?:check|analyze|look\s+at)\s+(.+?)\s*\??$",
        r"^\s*check\s+(.+?)\s+instead\s*\??$",
    )

    LOCATION_PREPOSITION_PATTERNS = (
        r"\b(?:in|at|near|around|over|across|within|outside)\s+"
        r"([A-Za-z][A-Za-z0-9 .'\-]{1,80}?)(?:\s+(?:from|between|during|"
        r"over|using|with|and|for)\b|[?.!,;:]|$)",

        r"\b(?:of|for)\s+"
        r"([A-Za-z][A-Za-z0-9 .'\-]{1,80}?)(?:\s+(?:from|between|during|"
        r"over|using|with|and)\b|[?.!,;:]|$)",
    )

    # ------------------------------------------------------------------
    # Temporal keywords
    # ------------------------------------------------------------------

    TEMPORAL_COMPARISON_TERMS = (
        "change",
        "changed",
        "changing",
        "difference",
        "compare",
        "comparison",
        "before and after",
        "before-after",
        "evolution",
        "expansion",
        "shrink",
        "loss",
        "growth",
        "increase",
        "decrease",
        "decline",
        "between",
        "over time",
        "through time",
        "temporal",
        "historical",
        "trend",
        "trends",
    )

    LATEST_TERMS = (
        "latest",
        "current",
        "currently",
        "most recent",
        "recent",
    )

    EVENT_NAMES = (
        "flood",
        "cyclone",
        "fire",
        "earthquake",
        "landslide",
        "storm",
        "drought",
    )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        context: dict[str, Any] | None = None,
    ):
        self.raw_context: dict[str, Any] = copy.deepcopy(
            context
            if isinstance(context, dict)
            else {}
        )

        self.raw_context.setdefault(
            "active_aoi",
            {},
        )

        self.raw_context.setdefault(
            "current_viewport",
            {},
        )

        self.raw_context.setdefault(
            "conversation_history",
            [],
        )

        self.raw_context.setdefault(
            "image_assets",
            [],
        )

        self.raw_context.setdefault(
            "image_count",
            0,
        )

        self.raw_context.setdefault(
            "has_images",
            False,
        )

        self.raw_context.setdefault(
            "selected_dates",
            [],
        )

        self.raw_context.setdefault(
            "selected_scenes",
            [],
        )

        self.raw_context.setdefault(
            "available_evidence",
            [],
        )

        self.raw_context.setdefault(
            "active_map_context",
            {},
        )

        self.raw_context.setdefault(
            "time_range",
            {},
        )

        self.raw_context.setdefault(
            "max_history_turns",
            15,
        )

        self.active_aoi = self._normalize_mapping(
            self.raw_context.get(
                "active_aoi"
            )
        )

        self.current_viewport = self._normalize_mapping(
            self.raw_context.get(
                "current_viewport"
            )
        )

        self.active_map_context = self._normalize_mapping(
            self.raw_context.get(
                "active_map_context"
            )
        )

        self.conversation_history = self._normalize_history(
            self.raw_context.get(
                "conversation_history"
            )
        )

        self.image_count = self._safe_nonnegative_int(
            self.raw_context.get(
                "image_count"
            )
        )

        self.has_images = bool(
            self.raw_context.get(
                "has_images"
            )
        ) or self.image_count > 0

        self.selected_sensor = self._normalize_sensor(
            self.raw_context.get(
                "sensor"
            )
        )

    # =========================================================================
    # Default context
    # =========================================================================

    @staticmethod
    def get_default_context(
        session_name: str = "Designated Area of Interest",
    ) -> dict[str, Any]:
        """
        Create an empty context.

        The session name may be retained as a human-readable project label,
        but it does NOT create an AOI, coordinate, or geometry.
        """

        context: dict[str, Any] = {
            "active_project": {},
            "active_aoi": {},
            "active_map_context": {},
            "active_scene": {},
            "active_region": {},
            "active_focus": None,
            "selected_dates": [],
            "selected_scenes": [],
            "active_analysis": {},
            "previous_questions": [],
            "previous_results": [],
            "user_intent": {},
            "conversation_entities": [],
            "current_visual_state": {},
            "current_viewport": {},
            "available_evidence": [],
            "image_assets": [],
            "image_count": 0,
            "has_images": False,
            "sensor": None,
            "time_range": {},
            "conversation_history": [],
            "max_history_turns": 15,
        }

        if session_name:
            context["session_name"] = str(
                session_name
            ).strip()

        return context

    # =========================================================================
    # Normalization
    # =========================================================================

    @staticmethod
    def _normalize_mapping(
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(
            value,
            dict,
        ):
            return {}

        return copy.deepcopy(
            value
        )

    @staticmethod
    def _normalize_history(
        value: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(
            value,
            list,
        ):
            return []

        normalized: list[dict[str, Any]] = []

        for item in value:
            if isinstance(
                item,
                dict,
            ):
                normalized.append(
                    copy.deepcopy(item)
                )

        return normalized

    @staticmethod
    def _safe_nonnegative_int(
        value: Any,
    ) -> int:
        try:
            number = int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0

        return max(
            0,
            number,
        )

    @staticmethod
    def _normalize_sensor(
        value: Any,
    ) -> str | None:
        """
        Preserve an explicitly supplied sensor only.

        No default sensor is ever selected.
        """

        if not isinstance(
            value,
            str,
        ):
            return None

        normalized = value.strip()

        return normalized if normalized else None

    @staticmethod
    def _clean_text(
        value: str,
    ) -> str:
        normalized = str(
            value or ""
        ).lower().strip()

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        normalized = re.sub(
            r"^[\s\.,;:!?]+|[\s\.,;:!?]+$",
            "",
            normalized,
        )

        return normalized

    @staticmethod
    def _safe_confidence(
        value: Any,
    ) -> float | None:
        """
        Preserve confidence only when explicitly supplied and valid.
        """

        if value is None:
            return None

        try:
            confidence = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not 0.0 <= confidence <= 1.0:
            return None

        return confidence

    @staticmethod
    def _valid_bbox(
        value: Any,
    ) -> list[float] | None:
        if not isinstance(
            value,
            (list, tuple),
        ):
            return None

        if len(value) != 4:
            return None

        try:
            bbox = [
                float(v)
                for v in value
            ]
        except (
            TypeError,
            ValueError,
        ):
            return None

        west, south, east, north = bbox

        if not (
            -180.0 <= west <= 180.0
            and -180.0 <= east <= 180.0
            and -90.0 <= south <= 90.0
            and -90.0 <= north <= 90.0
        ):
            return None

        if west > east or south > north:
            return None

        return bbox

    @staticmethod
    def _valid_geometry(
        value: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(
            value,
            dict,
        ):
            return None

        geometry_type = value.get(
            "type"
        )

        if not isinstance(
            geometry_type,
            str,
        ):
            return None

        if geometry_type != "GeometryCollection":
            if "coordinates" not in value:
                return None

        return copy.deepcopy(
            value
        )

    @staticmethod
    def _normalize_iso_date(
        value: Any,
    ) -> str | None:
        if isinstance(
            value,
            datetime,
        ):
            return value.date().isoformat()

        if isinstance(
            value,
            date,
        ):
            return value.isoformat()

        if not isinstance(
            value,
            str,
        ):
            return None

        value = value.strip()

        if not value:
            return None

        # Accept ISO datetime strings by using the date portion.
        candidate = value[:10]

        try:
            parsed = date.fromisoformat(
                candidate
            )
        except ValueError:
            return None

        return parsed.isoformat()

    @staticmethod
    def _normalize_date_list(
        values: Any,
    ) -> list[str]:
        if not isinstance(
            values,
            (list, tuple),
        ):
            return []

        result: list[str] = []

        for value in values:
            normalized = ContextEngine._normalize_iso_date(
                value
            )

            if normalized and normalized not in result:
                result.append(
                    normalized
                )

        return sorted(result)

    # =========================================================================
    # Context image helpers
    # =========================================================================

    def _context_contains_images(self) -> bool:
        if self.image_count > 0:
            return True

        for key in (
            "images",
            "image_assets",
            "image_paths",
            "image_ids",
            "uploaded_images",
            "selected_scenes",
        ):
            value = self.raw_context.get(
                key
            )

            if isinstance(
                value,
                (list, tuple),
            ) and value:
                return True

        return False

    def _actual_image_dates(self) -> list[str]:
        dates: list[str] = []

        for key in (
            "image_dates",
            "selected_dates",
        ):
            values = self.raw_context.get(
                key
            )

            for value in self._normalize_date_list(
                values
            ):
                if value not in dates:
                    dates.append(
                        value
                    )

        assets = self.raw_context.get(
            "image_assets"
        )

        if isinstance(
            assets,
            list,
        ):
            for asset in assets:
                if not isinstance(
                    asset,
                    dict,
                ):
                    continue

                for key in (
                    "date",
                    "acquisition_date",
                    "acquired_at",
                    "datetime",
                    "timestamp",
                ):
                    normalized = self._normalize_iso_date(
                        asset.get(
                            key
                        )
                    )

                    if (
                        normalized
                        and normalized not in dates
                    ):
                        dates.append(
                            normalized
                        )

        return sorted(dates)

    # =========================================================================
    # Follow-up detection
    # =========================================================================

    def is_follow_up_query(
        self,
        query: str,
    ) -> bool:
        q = self._clean_text(
            query
        )

        if (
            not q
            or not self.conversation_history
        ):
            return False

        for pattern in self.FOLLOW_UP_TRIGGER_PATTERNS:
            if re.search(
                pattern,
                q,
            ):
                return True

        for pattern in self.ENTITY_SWITCH_PATTERNS:
            if re.search(
                pattern,
                q,
            ):
                return True

        if self._contains_deictic_reference(
            q
        ):
            return True

        # Very short queries in an existing conversation can be follow-ups,
        # but only when actual context exists.
        if len(
            q.split()
        ) <= 6:
            if (
                self.get_last_target()
                or self.get_last_location()
                or self.active_aoi
                or self.active_map_context
                or self.current_viewport
            ):
                return True

        return False

    # =========================================================================
    # Entity switching
    # =========================================================================

    def resolve_entity_switch(
        self,
        query: str,
    ) -> dict[str, Any] | None:
        """
        Resolve a new location in a follow-up.

        Analytical intent may be inherited from the previous turn.

        The new location itself must be independently grounded.
        """

        q = self._clean_text(
            query
        )

        candidate: str | None = None

        for pattern in self.ENTITY_SWITCH_PATTERNS:
            match = re.search(
                pattern,
                q,
            )

            if not match:
                continue

            candidate = match.group(
                1
            ).strip()

            candidate = re.sub(
                r"[\?\.,!;:]+$",
                "",
                candidate,
            ).strip()

            break

        if not candidate:
            return None

        location_data = self._resolve_location_candidate(
            candidate
        )

        last_turn = self.get_last_turn() or {}

        inherited_intent = (
            last_turn.get("intent")
            or self.raw_context.get("intent")
        )

        inherited_target = (
            last_turn.get("target")
            or self.raw_context.get("target")
            or self.get_last_target()
        )

        inherited_task = (
            last_turn.get("task")
            or last_turn.get("operation")
            or self.get_last_operation()
            or inherited_intent
        )

        temporal_required = (
            self._previous_turn_requires_temporal_context()
            or self._query_implies_temporal_comparison(
                q
            )
        )

        if not location_data:
            return {
                "is_entity_switch": True,
                "new_location": None,
                "inherited_intent": inherited_intent,
                "inherited_target": inherited_target,
                "inherited_task": inherited_task,
                "temporal": temporal_required,
                "raw_candidate": candidate,
                "requires_clarification": True,
                "clarification_prompt": (
                    f"I couldn't resolve '{candidate}' to a grounded "
                    "location. Please select it on the map or provide "
                    "a more specific place."
                ),
            }

        return {
            "is_entity_switch": True,
            "new_location": location_data,
            "inherited_intent": inherited_intent,
            "inherited_target": inherited_target,
            "inherited_task": inherited_task,
            "temporal": temporal_required,
            "raw_candidate": candidate,
            "requires_clarification": False,
        }

    def _resolve_location_candidate(
        self,
        candidate: str,
    ) -> dict[str, Any] | None:
        """
        Resolve a location through the project's actual resolver.

        No static gazetteer is maintained here.
        """

        try:
            from apps.agent.location_resolver import (
                LocationResolver,
            )

            result = LocationResolver.resolve(
                candidate,
                allow_fuzzy=True,
                allow_network=True,
                session_context=self.raw_context,
            )

            if (
                result
                and getattr(
                    result,
                    "is_valid",
                    False,
                )
            ):
                return result.to_dict()

        except TypeError:
            # Compatibility with a resolver implementation that does not
            # expose session_context.
            try:
                from apps.agent.location_resolver import (
                    LocationResolver,
                )

                result = LocationResolver.resolve(
                    candidate,
                    allow_fuzzy=True,
                    allow_network=True,
                )

                if (
                    result
                    and getattr(
                        result,
                        "is_valid",
                        False,
                    )
                ):
                    return result.to_dict()

            except Exception:
                pass

        except Exception:
            pass

        # Compatibility fallback.
        try:
            from apps.agent.geocoding import (
                resolve_location,
            )

            result = resolve_location(
                candidate,
                self.raw_context,
            )

            if isinstance(
                result,
                dict,
            ):
                if (
                    result.get("name")
                    or result.get("canonical_name")
                    or result.get("display_name")
                ):
                    return result

        except Exception:
            pass

        return None

    # =========================================================================
    # Spatial resolution
    # =========================================================================

    def resolve_spatial_context(
        self,
        query: str,
    ) -> ResolvedSpatialContext:
        """
        Resolve spatial context using actual evidence.

        Priority:

            1. Explicit query location
            2. Active map/AOI context
            3. Current viewport
            4. Previous grounded conversation location
            5. Unresolved

        A place name without returned geometry remains unresolved for
        geospatial operations.
        """

        q = self._clean_text(
            query
        )

        if not q:
            return ResolvedSpatialContext(
                source="unresolved",
                is_resolved=False,
                requires_clarification=True,
            )

        buffer_meters = self._extract_buffer_meters(
            q
        )

        direction = self._extract_direction(
            q
        )

        has_deictic = self._contains_deictic_reference(
            q
        )

        # --------------------------------------------------------------
        # 1. Explicit query location
        # --------------------------------------------------------------

        explicit = self._resolve_explicit_location(
            query
        )

        if explicit and not has_deictic:
            return self._spatial_from_location(
                explicit,
                source=explicit.get(
                    "source",
                    "query_location",
                ),
                buffer_meters=buffer_meters,
                direction=direction,
            )

        # --------------------------------------------------------------
        # 2. Active map context
        # --------------------------------------------------------------

        if has_deictic or not explicit:
            active_map = self._spatial_from_context_mapping(
                self.active_map_context,
                source="active_map_context",
                buffer_meters=buffer_meters,
                direction=direction,
            )

            if active_map:
                return active_map

            active = self._spatial_from_context_mapping(
                self.active_aoi,
                source="active_aoi",
                buffer_meters=buffer_meters,
                direction=direction,
            )

            if active:
                return active

        # --------------------------------------------------------------
        # 3. Current viewport
        # --------------------------------------------------------------

        if has_deictic or not explicit:
            viewport = self._spatial_from_viewport(
                buffer_meters=buffer_meters,
                direction=direction,
            )

            if viewport:
                return viewport

        # --------------------------------------------------------------
        # 4. Previous grounded conversation
        # --------------------------------------------------------------

        if has_deictic or not explicit:
            previous = self._spatial_from_previous_turn(
                buffer_meters=buffer_meters,
                direction=direction,
            )

            if previous:
                return previous

        # --------------------------------------------------------------
        # 5. Explicit location with incomplete geometry
        # --------------------------------------------------------------

        if explicit:
            return self._spatial_from_location(
                explicit,
                source=explicit.get(
                    "source",
                    "query_location",
                ),
                buffer_meters=buffer_meters,
                direction=direction,
            )

        return ResolvedSpatialContext(
            source="unresolved",
            buffer_meters=buffer_meters,
            direction=direction,
            is_resolved=False,
            requires_clarification=True,
        )

    def _resolve_explicit_location(
        self,
        original_query: str,
    ) -> dict[str, Any] | None:
        """
        Resolve explicit location information.

        Failure is represented by None.
        """

        # First use the project's geocoding compatibility layer.
        try:
            from apps.agent.geocoding import (
                resolve_location,
            )

            result = resolve_location(
                original_query,
                self.raw_context,
            )

            if isinstance(
                result,
                dict,
            ):
                if (
                    result.get("name")
                    or result.get("canonical_name")
                    or result.get("display_name")
                    or result.get("bbox")
                    or result.get("geometry")
                ):
                    return result

        except Exception:
            pass

        candidate = self._extract_location_candidate(
            self._clean_text(
                original_query
            )
        )

        if not candidate:
            return None

        return self._resolve_location_candidate(
            candidate
        )

    @staticmethod
    def _extract_location_candidate(
        query: str,
    ) -> str | None:
        """
        Extract a conservative text candidate.

        This function does not verify the place.

        LocationResolver must verify the candidate.
        """

        stop_words = {
            "the",
            "area",
            "region",
            "place",
            "location",
            "image",
            "images",
            "scene",
            "satellite",
            "imagery",
            "vegetation",
            "water",
            "urban",
            "buildings",
            "change",
            "changes",
            "current",
            "latest",
            "recent",
            "this",
            "that",
            "show",
            "analyze",
            "analysis",
            "compare",
            "between",
            "over",
            "from",
            "during",
            "using",
            "with",
            "and",
            "to",
            "for",
            "near",
            "around",
            "in",
            "at",
        }

        for pattern in ContextEngine.LOCATION_PREPOSITION_PATTERNS:
            match = re.search(
                pattern,
                query,
            )

            if not match:
                continue

            candidate = match.group(
                1
            ).strip()

            words = candidate.split()

            cleaned_words: list[str] = []

            for word in words:
                normalized = word.lower().strip(
                    ".,!?;:"
                )

                if normalized in stop_words:
                    break

                cleaned_words.append(
                    word.strip(
                        ".,!?;:"
                    )
                )

            candidate = " ".join(
                word
                for word in cleaned_words
                if word
            ).strip()

            if len(candidate) >= 2:
                return candidate

        return None

    @staticmethod
    def _contains_deictic_reference(
        query: str,
    ) -> bool:
        normalized = ContextEngine._clean_text(
            query
        )

        for term in ContextEngine.DEICTIC_HERE_TERMS:
            if re.search(
                rf"\b{re.escape(term)}\b",
                normalized,
            ):
                return True

        return False

    @staticmethod
    def _extract_buffer_meters(
        query: str,
    ) -> float | None:
        """
        Parse only an explicitly requested spatial buffer.

        No default buffer is created.
        """

        match = re.search(
            r"\bwithin\s+"
            r"(\d+(?:\.\d+)?)\s*"
            r"(km|kilometers|m|meters)\s+of\b",
            query,
        )

        if not match:
            return None

        try:
            distance = float(
                match.group(
                    1
                )
            )
        except ValueError:
            return None

        if distance < 0:
            return None

        if match.group(
            2
        ) in {
            "km",
            "kilometers",
        }:
            return distance * 1000.0

        return distance

    @staticmethod
    def _extract_direction(
        query: str,
    ) -> str | None:
        match = re.search(
            r"\b("
            r"north|south|east|west|"
            r"northeast|northwest|southeast|southwest"
            r")\s+of\b",
            query,
        )

        return (
            match.group(1)
            if match
            else None
        )

    def _spatial_from_location(
        self,
        location: dict[str, Any],
        source: str,
        buffer_meters: float | None,
        direction: str | None,
    ) -> ResolvedSpatialContext:
        name = (
            location.get("name")
            or location.get("canonical_name")
            or location.get("display_name")
        )

        bbox = self._valid_bbox(
            location.get(
                "bbox"
            )
        )

        geometry = self._valid_geometry(
            location.get(
                "geometry"
            )
        )

        resolved = bool(
            bbox is not None
            or geometry is not None
        )

        return ResolvedSpatialContext(
            name=(
                str(name)
                if name
                else None
            ),
            bbox=bbox,
            geometry=geometry,
            source=source,
            buffer_meters=buffer_meters,
            direction=direction,
            is_resolved=resolved,
            requires_clarification=not resolved,
            confidence=self._safe_confidence(
                location.get(
                    "confidence"
                )
            ),
        )

    def _spatial_from_context_mapping(
        self,
        context: dict[str, Any],
        source: str,
        buffer_meters: float | None,
        direction: str | None,
    ) -> ResolvedSpatialContext | None:
        if not context:
            return None

        # Support nested map-context structures.
        for key in (
            "active_pin",
            "map_pin",
            "selected_pin",
            "aoi",
            "location",
        ):
            nested = context.get(
                key
            )

            if isinstance(
                nested,
                dict,
            ):
                result = self._spatial_from_context_mapping(
                    nested,
                    source=f"{source}:{key}",
                    buffer_meters=buffer_meters,
                    direction=direction,
                )

                if result:
                    return result

        name = (
            context.get("name")
            or context.get("canonical_name")
            or context.get("display_name")
            or context.get("label")
        )

        bbox = self._valid_bbox(
            context.get(
                "bbox"
            )
        )

        if bbox is None:
            bbox = self._valid_bbox(
                context.get(
                    "bounds"
                )
            )

        geometry = self._valid_geometry(
            context.get(
                "geometry"
            )
        )

        if not name and bbox is None and geometry is None:
            return None

        resolved = bool(
            bbox is not None
            or geometry is not None
        )

        return ResolvedSpatialContext(
            name=(
                str(name)
                if name
                else None
            ),
            bbox=bbox,
            geometry=geometry,
            source=source,
            buffer_meters=buffer_meters,
            direction=direction,
            is_resolved=resolved,
            requires_clarification=not resolved,
            confidence=self._safe_confidence(
                context.get(
                    "confidence"
                )
            ),
        )

    def _spatial_from_viewport(
        self,
        buffer_meters: float | None,
        direction: str | None,
    ) -> ResolvedSpatialContext | None:
        viewport = self.current_viewport

        if not viewport:
            return None

        bbox = self._valid_bbox(
            viewport.get(
                "bbox"
            )
        )

        if bbox is None:
            keys = (
                "west",
                "south",
                "east",
                "north",
            )

            if all(
                key in viewport
                for key in keys
            ):
                bbox = self._valid_bbox(
                    [
                        viewport["west"],
                        viewport["south"],
                        viewport["east"],
                        viewport["north"],
                    ]
                )

        geometry = self._valid_geometry(
            viewport.get(
                "geometry"
            )
        )

        if bbox is None and geometry is None:
            return None

        name = (
            viewport.get("name")
            or viewport.get("label")
            or "Current Map View"
        )

        return ResolvedSpatialContext(
            name=str(
                name
            ),
            bbox=bbox,
            geometry=geometry,
            source="map_viewport",
            buffer_meters=buffer_meters,
            direction=direction,
            is_resolved=True,
            requires_clarification=False,
            confidence=self._safe_confidence(
                viewport.get(
                    "confidence"
                )
            ),
        )

    def _spatial_from_previous_turn(
        self,
        buffer_meters: float | None,
        direction: str | None,
    ) -> ResolvedSpatialContext | None:
        location = self._get_last_location_record()

        if not location:
            return None

        return self._spatial_from_context_mapping(
            location,
            source="conversation_history",
            buffer_meters=buffer_meters,
            direction=direction,
        )

    # =========================================================================
    # Temporal resolution
    # =========================================================================

    def resolve_temporal_context(
        self,
        query: str,
    ) -> ResolvedTemporalContext:
        """
        Resolve temporal information without creating arbitrary dates.

        Examples:

            "compare 2020 and 2025"
                -> explicit temporal context

            "compare the available observations"
                -> comparison required, dates unresolved

            "show changes"
                -> comparison required, dates unresolved

            "show the latest image"
                -> latest observation requested, actual catalog date
                   must be determined by retrieval
        """

        q = self._clean_text(
            query
        )

        if not q:
            return ResolvedTemporalContext(
                source="unresolved",
                is_resolved=False,
                requires_clarification=False,
            )

        reference_date = self._get_context_date()

        # --------------------------------------------------------------
        # Explicit date range
        # --------------------------------------------------------------

        explicit_range = self._parse_explicit_date_range(
            q
        )

        if explicit_range:
            start, end = explicit_range

            return ResolvedTemporalContext(
                comparison_required=(
                    self._query_implies_temporal_comparison(
                        q
                    )
                ),
                start_date=start,
                end_date=end,
                source="explicit_query",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Multiple explicit years
        # --------------------------------------------------------------

        year_context = self._parse_year_context(
            q,
            reference_date,
        )

        if year_context:
            return year_context

        # --------------------------------------------------------------
        # Explicit relative window
        # --------------------------------------------------------------

        relative = self._parse_relative_window(
            q,
            reference_date,
        )

        if relative:
            return relative

        # --------------------------------------------------------------
        # Event reference
        # --------------------------------------------------------------

        event_context = self._resolve_event_reference(
            q
        )

        if event_context:
            return event_context

        # --------------------------------------------------------------
        # Existing session/image temporal evidence
        # --------------------------------------------------------------

        session_context = self._resolve_temporal_from_session()

        if session_context:
            return session_context

        # --------------------------------------------------------------
        # Comparison requested without dates
        # --------------------------------------------------------------

        if self._query_implies_temporal_comparison(
            q
        ):
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=None,
                end_date=None,
                source="unresolved_comparison",
                is_resolved=False,
                requires_clarification=True,
                uncertainty_notes=[
                    "A temporal comparison was requested, but "
                    "grounded comparison dates are not available."
                ],
            )

        # --------------------------------------------------------------
        # Latest/current request
        # --------------------------------------------------------------

        if any(
            term in q
            for term in self.LATEST_TERMS
        ):
            return ResolvedTemporalContext(
                comparison_required=False,
                start_date=None,
                end_date=None,
                source="latest_observation",
                is_resolved=False,
                requires_clarification=False,
                uncertainty_notes=[
                    "The latest available observation must be "
                    "determined from actual catalogue data."
                ],
            )

        # --------------------------------------------------------------
        # No temporal requirement
        # --------------------------------------------------------------

        return ResolvedTemporalContext(
            comparison_required=False,
            start_date=None,
            end_date=None,
            source="not_specified",
            is_resolved=False,
            requires_clarification=False,
        )

    @staticmethod
    def _parse_explicit_date_range(
        query: str,
    ) -> tuple[str, str] | None:
        """
        Parse explicit ISO-like date ranges.

        Supported:

            2024-01-01 to 2024-03-31
            from 2024-01-01 to 2024-03-31
            between 2024-01-01 and 2024-03-31
        """

        pattern = (
            r"(?:between\s+|from\s+)?"
            r"(\d{4}-\d{1,2}-\d{1,2})"
            r"\s+(?:and|to|-)\s+"
            r"(\d{4}-\d{1,2}-\d{1,2})"
        )

        match = re.search(
            pattern,
            query,
        )

        if not match:
            return None

        start = ContextEngine._normalize_iso_date(
            match.group(
                1
            )
        )

        end = ContextEngine._normalize_iso_date(
            match.group(
                2
            )
        )

        if not start or not end:
            return None

        if start > end:
            start, end = end, start

        return start, end

    @staticmethod
    def _parse_year_context(
        query: str,
        reference_date: date,
    ) -> ResolvedTemporalContext | None:
        years = [
            int(value)
            for value in re.findall(
                r"\b(19\d{2}|20\d{2})\b",
                query,
            )
        ]

        years = sorted(
            {
                year
                for year in years
                if 1900 <= year <= reference_date.year
            }
        )

        if not years:
            return None

        if len(years) >= 2:
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=f"{years[0]:04d}-01-01",
                end_date=f"{years[-1]:04d}-12-31",
                source="explicit_query",
                is_resolved=True,
                requires_clarification=False,
            )

        year = years[0]

        if any(
            term in query
            for term in (
                "since",
                "from",
            )
        ):
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=f"{year:04d}-01-01",
                end_date=reference_date.isoformat(),
                source="explicit_query",
                is_resolved=True,
                requires_clarification=False,
                uncertainty_notes=[
                    "The upper bound uses the supplied context "
                    "reference date because the query used 'since/from'."
                ],
            )

        if "before" in query:
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=None,
                end_date=f"{year:04d}-12-31",
                source="explicit_query",
                is_resolved=False,
                requires_clarification=True,
                uncertainty_notes=[
                    "An upper temporal bound was provided, but "
                    "a grounded start date was not provided."
                ],
            )

        return ResolvedTemporalContext(
            comparison_required=False,
            start_date=f"{year:04d}-01-01",
            end_date=f"{year:04d}-12-31",
            source="explicit_query",
            is_resolved=True,
            requires_clarification=False,
        )

    @staticmethod
    def _parse_relative_window(
        query: str,
        reference_date: date,
    ) -> ResolvedTemporalContext | None:
        """
        Resolve only relative windows explicitly present in the query.

        The reference date is a temporal interpretation anchor, not an
        observation date.
        """

        # --------------------------------------------------------------
        # Last/past N months
        # --------------------------------------------------------------

        month_match = re.search(
            r"\b(?:last|past|over\s+the\s+last|over\s+the\s+past)\s+"
            r"(\d+)\s+months?\b",
            query,
        )

        if month_match:
            months = int(
                month_match.group(
                    1
                )
            )

            if months <= 0:
                return None

            year = reference_date.year
            month = reference_date.month - months

            while month <= 0:
                year -= 1
                month += 12

            day = min(
                reference_date.day,
                calendar.monthrange(
                    year,
                    month,
                )[1],
            )

            start = date(
                year,
                month,
                day,
            )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Last/past N years
        # --------------------------------------------------------------

        year_match = re.search(
            r"\b(?:last|past|over\s+the\s+last|over\s+the\s+past)\s+"
            r"(\d+)\s+years?\b",
            query,
        )

        if year_match:
            years = int(
                year_match.group(
                    1
                )
            )

            if years <= 0:
                return None

            try:
                start = reference_date.replace(
                    year=reference_date.year - years
                )
            except ValueError:
                start = reference_date.replace(
                    year=reference_date.year - years,
                    day=28,
                )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Last/past N weeks
        # --------------------------------------------------------------

        week_match = re.search(
            r"\b(?:last|past)\s+(\d+)\s+weeks?\b",
            query,
        )

        if week_match:
            weeks = int(
                week_match.group(
                    1
                )
            )

            if weeks <= 0:
                return None

            start = reference_date - timedelta(
                weeks=weeks
            )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Last/past N days
        # --------------------------------------------------------------

        day_match = re.search(
            r"\b(?:last|past)\s+(\d+)\s+days?\b",
            query,
        )

        if day_match:
            days = int(
                day_match.group(
                    1
                )
            )

            if days <= 0:
                return None

            start = reference_date - timedelta(
                days=days
            )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Last year
        # --------------------------------------------------------------

        if (
            "last year" in query
            or "past year" in query
        ):
            try:
                start = reference_date.replace(
                    year=reference_date.year - 1
                )
            except ValueError:
                start = reference_date.replace(
                    year=reference_date.year - 1,
                    day=28,
                )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        # --------------------------------------------------------------
        # Last month
        # --------------------------------------------------------------

        if (
            "last month" in query
            or "past month" in query
        ):
            year = reference_date.year
            month = reference_date.month - 1

            if month == 0:
                year -= 1
                month = 12

            day = min(
                reference_date.day,
                calendar.monthrange(
                    year,
                    month,
                )[1],
            )

            start = date(
                year,
                month,
                day,
            )

            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=start.isoformat(),
                end_date=reference_date.isoformat(),
                source="relative_window",
                is_resolved=True,
                requires_clarification=False,
            )

        return None

    @staticmethod
    def _resolve_event_reference(
        query: str,
    ) -> ResolvedTemporalContext | None:
        """
        Identify an event reference without inventing its date.
        """

        for event in ContextEngine.EVENT_NAMES:
            pattern = (
                rf"\b(?:before|after|pre|post)[-\s]?"
                rf"(?:the\s+)?{event}\b"
            )

            if re.search(
                pattern,
                query,
            ):
                return ResolvedTemporalContext(
                    comparison_required=True,
                    start_date=None,
                    end_date=None,
                    source="reference_event",
                    reference_event=event,
                    is_resolved=False,
                    requires_clarification=True,
                    uncertainty_notes=[
                        f"The query references a {event} event, "
                        "but its actual event timing is not present "
                        "in the current context."
                    ],
                )

        return None

    def _resolve_temporal_from_session(
        self,
    ) -> ResolvedTemporalContext | None:
        """
        Use actual dates already present in the session.

        No current date is converted into an imagery date.
        """

        candidates = self._actual_image_dates()

        if len(candidates) >= 2:
            return ResolvedTemporalContext(
                comparison_required=True,
                start_date=candidates[0],
                end_date=candidates[-1],
                source="imagery_metadata",
                is_resolved=True,
                requires_clarification=False,
            )

        if len(candidates) == 1:
            return ResolvedTemporalContext(
                comparison_required=False,
                start_date=candidates[0],
                end_date=candidates[0],
                source="imagery_metadata",
                is_resolved=True,
                requires_clarification=False,
            )

        # Explicit session time range.
        time_range = self.raw_context.get(
            "time_range"
        )

        if isinstance(
            time_range,
            dict,
        ):
            start = self._normalize_iso_date(
                time_range.get(
                    "start_date",
                    time_range.get(
                        "start"
                    ),
                )
            )

            end = self._normalize_iso_date(
                time_range.get(
                    "end_date",
                    time_range.get(
                        "end"
                    ),
                )
            )

            if start or end:
                return ResolvedTemporalContext(
                    comparison_required=bool(
                        time_range.get(
                            "comparison_required"
                        )
                        or (
                            start
                            and end
                            and start != end
                        )
                    ),
                    start_date=start,
                    end_date=end,
                    source="session_context",
                    is_resolved=bool(
                        start and end
                    ),
                    requires_clarification=not bool(
                        start and end
                    ),
                    uncertainty_notes=(
                        []
                        if start and end
                        else [
                            "Session temporal context is incomplete."
                        ]
                    ),
                )

        return None

    def _get_context_date(self) -> date:
        """
        Obtain a reference date for interpreting explicit relative language.

        This is NOT treated as an imagery acquisition date.

        If the application supplies a deterministic current_date, it is used.
        Otherwise the system date is used only as the temporal interpretation
        anchor for phrases such as "last 30 days".
        """

        configured = self.raw_context.get(
            "current_date"
        )

        normalized = self._normalize_iso_date(
            configured
        )

        if normalized:
            return date.fromisoformat(
                normalized
            )

        return date.today()

    def _query_implies_temporal_comparison(
        self,
        query: str,
    ) -> bool:
        normalized = self._clean_text(
            query
        )

        return any(
            term in normalized
            for term in self.TEMPORAL_COMPARISON_TERMS
        )

    def _previous_turn_requires_temporal_context(
        self,
    ) -> bool:
        last_turn = self.get_last_turn()

        if not last_turn:
            return False

        temporal = last_turn.get(
            "temporal"
        )

        if isinstance(
            temporal,
            dict,
        ):
            if temporal.get(
                "comparison_required"
            ):
                return True

        text = " ".join(
            str(
                last_turn.get(
                    key,
                    "",
                )
            )
            for key in (
                "intent",
                "operation",
                "task",
            )
        ).lower()

        return any(
            keyword in text
            for keyword in (
                "change",
                "temporal",
                "compare",
                "bitemporal",
            )
        )

    # =========================================================================
    # Conversation history
    # =========================================================================

    def get_last_location(
        self,
    ) -> dict[str, Any] | None:
        """
        Return the most recent grounded location.

        A location name without geometry can still be returned as conversational
        context, but downstream spatial operations must inspect `bbox` or
        `geometry` before treating it as spatially resolved.
        """

        # Active map context takes priority.
        if self.active_map_context:
            location = self._extract_location_record(
                self.active_map_context
            )

            if location:
                return location

        if self.active_aoi:
            location = self._extract_location_record(
                self.active_aoi
            )

            if location:
                return location

        # Then previous grounded turns.
        for turn in reversed(
            self.conversation_history
        ):
            location = turn.get(
                "location"
            )

            if isinstance(
                location,
                dict,
            ):
                if self._location_record_has_content(
                    location
                ):
                    return copy.deepcopy(
                        location
                    )

            elif isinstance(
                location,
                str,
            ):
                value = location.strip()

                if value:
                    return {
                        "name": value
                    }

        return None

    @staticmethod
    def _extract_location_record(
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(
            context,
            dict,
        ):
            return None

        for key in (
            "active_pin",
            "map_pin",
            "selected_pin",
            "location",
            "aoi",
        ):
            nested = context.get(
                key
            )

            if isinstance(
                nested,
                dict,
            ):
                record = ContextEngine._extract_location_record(
                    nested
                )

                if record:
                    return record

        if ContextEngine._location_record_has_content(
            context
        ):
            return copy.deepcopy(
                context
            )

        return None

    @staticmethod
    def _location_record_has_content(
        location: dict[str, Any],
    ) -> bool:
        return bool(
            location.get("name")
            or location.get("canonical_name")
            or location.get("display_name")
            or location.get("bbox")
            or location.get("geometry")
            or (
                location.get("latitude") is not None
                and location.get("longitude") is not None
            )
        )

    def _get_last_location_record(
        self,
    ) -> dict[str, Any] | None:
        return self.get_last_location()

    def get_last_target(
        self,
    ) -> str | None:
        """
        Return the most recent meaningful analytical target.
        """

        for turn in reversed(
            self.conversation_history
        ):
            target = turn.get(
                "target"
            )

            if (
                target
                and str(target).lower()
                not in {
                    "general",
                    "unknown",
                    "general_landcover",
                }
            ):
                return str(
                    target
                )

        target = self.raw_context.get(
            "target"
        )

        if target:
            return str(
                target
            )

        return None

    def get_last_metrics(
        self,
    ) -> dict[str, Any]:
        """
        Return actual metrics stored by the previous completed analysis.

        No metric is calculated here.
        """

        for turn in reversed(
            self.conversation_history
        ):
            metrics = turn.get(
                "metrics"
            )

            if isinstance(
                metrics,
                dict,
            ) and metrics:
                return copy.deepcopy(
                    metrics
                )

        return {}

    def get_last_intent(
        self,
    ) -> str | None:
        for turn in reversed(
            self.conversation_history
        ):
            intent = turn.get(
                "intent"
            )

            if intent:
                return str(
                    intent
                )

        value = self.raw_context.get(
            "intent"
        )

        return (
            str(value)
            if value
            else None
        )

    def get_last_operation(
        self,
    ) -> str | None:
        for turn in reversed(
            self.conversation_history
        ):
            operation = (
                turn.get("operation")
                or turn.get("task")
            )

            if operation:
                return str(
                    operation
                )

        return None

    def get_last_turn(
        self,
    ) -> dict[str, Any] | None:
        if not self.conversation_history:
            return None

        return copy.deepcopy(
            self.conversation_history[-1]
        )

    def update_history(
        self,
        query_text: str,
        intent: str,
        target: str,
        location: str | dict[str, Any] | None,
        metrics: dict[str, Any] | None = None,
        operation: str | None = None,
        task: str | None = None,
        temporal: dict[str, Any] | None = None,
    ) -> None:
        """
        Append a completed conversational turn.

        Metrics must come from actual execution.

        This method never calculates or synthesizes measurements.
        """

        turn = {
            "turn_index": (
                len(
                    self.conversation_history
                )
                + 1
            ),
            "query_text": str(
                query_text
                or ""
            ),
            "intent": str(
                intent
                or ""
            ),
            "target": str(
                target
                or ""
            ),
            "location": copy.deepcopy(
                location
            ),
            "metrics": (
                copy.deepcopy(
                    metrics
                )
                if isinstance(
                    metrics,
                    dict,
                )
                else {}
            ),
            "timestamp": datetime.now(
                dt_timezone.utc
            ).isoformat(),
        }

        if operation:
            turn["operation"] = str(
                operation
            )

        if task:
            turn["task"] = str(
                task
            )

        if isinstance(
            temporal,
            dict,
        ):
            turn["temporal"] = copy.deepcopy(
                temporal
            )

        self.conversation_history.append(
            turn
        )

        max_history = self._safe_nonnegative_int(
            self.raw_context.get(
                "max_history_turns",
                15,
            )
        )

        if max_history <= 0:
            max_history = 15

        self.conversation_history = (
            self.conversation_history[
                -max_history:
            ]
        )

        self.raw_context[
            "conversation_history"
        ] = copy.deepcopy(
            self.conversation_history
        )

    # =========================================================================
    # Context snapshot
    # =========================================================================

    def get_context_snapshot(
        self,
    ) -> dict[str, Any]:
        """
        Return compact state for the orchestrator/planner.

        This is state and provenance information, not chain-of-thought.
        """

        return {
            "active_aoi": copy.deepcopy(
                self.active_aoi
            ),
            "active_map_context": copy.deepcopy(
                self.active_map_context
            ),
            "current_viewport": copy.deepcopy(
                self.current_viewport
            ),
            "image_count": self.image_count,
            "has_images": self.has_images,
            "image_assets": copy.deepcopy(
                self.raw_context.get(
                    "image_assets",
                    [],
                )
            ),
            "image_dates": self._actual_image_dates(),
            "sensor": self.selected_sensor,
            "last_location": self.get_last_location(),
            "last_target": self.get_last_target(),
            "last_metrics": self.get_last_metrics(),
            "last_intent": self.get_last_intent(),
            "last_operation": self.get_last_operation(),
            "last_turn": self.get_last_turn(),
            "conversation_history": copy.deepcopy(
                self.conversation_history
            ),
            "selected_dates": copy.deepcopy(
                self.raw_context.get(
                    "selected_dates",
                    [],
                )
            ),
            "selected_scenes": copy.deepcopy(
                self.raw_context.get(
                    "selected_scenes",
                    [],
                )
            ),
            "available_evidence": copy.deepcopy(
                self.raw_context.get(
                    "available_evidence",
                    [],
                )
            ),
            "time_range": copy.deepcopy(
                self.raw_context.get(
                    "time_range",
                    {},
                )
            ),
        }

    # =========================================================================
    # Mutable spatial context
    # =========================================================================

    def set_active_aoi(
        self,
        aoi: dict[str, Any] | None,
    ) -> None:
        """
        Update active AOI using supplied application state.

        Invalid spatial data is retained only as non-spatial metadata; it is
        never converted into coordinates or geometry.
        """

        self.active_aoi = (
            copy.deepcopy(
                aoi
            )
            if isinstance(
                aoi,
                dict,
            )
            else {}
        )

        self.raw_context[
            "active_aoi"
        ] = copy.deepcopy(
            self.active_aoi
        )

    def set_map_context(
        self,
        map_context: dict[str, Any] | None,
    ) -> None:
        """
        Set first-class active map context.

        Expected examples include:

            {
                "pin": {
                    "latitude": ...,
                    "longitude": ...
                }
            }

        or:

            {
                "aoi": {
                    "bbox": [...]
                }
            }

        No geometry is generated if it is absent.
        """

        self.active_map_context = (
            copy.deepcopy(
                map_context
            )
            if isinstance(
                map_context,
                dict,
            )
            else {}
        )

        self.raw_context[
            "active_map_context"
        ] = copy.deepcopy(
            self.active_map_context
        )

    def set_viewport(
        self,
        viewport: dict[str, Any] | None,
    ) -> None:
        """
        Store actual map viewport state.
        """

        self.current_viewport = (
            copy.deepcopy(
                viewport
            )
            if isinstance(
                viewport,
                dict,
            )
            else {}
        )

        self.raw_context[
            "current_viewport"
        ] = copy.deepcopy(
            self.current_viewport
        )

    def set_image_context(
        self,
        image_count: int,
        image_dates: list[str] | None = None,
        sensor: str | None = None,
        image_assets: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Store actual imagery metadata.

        No dates or sensors are generated.
        """

        self.image_count = self._safe_nonnegative_int(
            image_count
        )

        self.has_images = (
            self.image_count > 0
        )

        self.raw_context[
            "image_count"
        ] = self.image_count

        self.raw_context[
            "has_images"
        ] = self.has_images

        if image_dates is not None:
            self.raw_context[
                "image_dates"
            ] = self._normalize_date_list(
                image_dates
            )

        if image_assets is not None:
            self.raw_context[
                "image_assets"
            ] = copy.deepcopy(
                image_assets
            )

        if sensor is not None:
            normalized_sensor = self._normalize_sensor(
                sensor
            )

            self.selected_sensor = normalized_sensor

            self.raw_context[
                "sensor"
            ] = normalized_sensor

    def set_available_evidence(
        self,
        evidence: list[Any] | None,
    ) -> None:
        """
        Store evidence produced by actual analysis/retrieval layers.

        This method does not generate evidence.
        """

        if not isinstance(
            evidence,
            list,
        ):
            evidence = []

        self.raw_context[
            "available_evidence"
        ] = copy.deepcopy(
            evidence
        )

    def set_time_range(
        self,
        time_range: dict[str, Any] | None,
    ) -> None:
        """
        Store an actual time range supplied by the application/retrieval
        layer.
        """

        if not isinstance(
            time_range,
            dict,
        ):
            self.raw_context[
                "time_range"
            ] = {}

            return

        normalized = copy.deepcopy(
            time_range
        )

        for source_key, target_key in (
            ("start", "start_date"),
            ("end", "end_date"),
        ):
            if (
                source_key in normalized
                and target_key not in normalized
            ):
                normalized[
                    target_key
                ] = normalized[
                    source_key
                ]

        for key in (
            "start_date",
            "end_date",
        ):
            if key in normalized:
                normalized[key] = (
                    self._normalize_iso_date(
                        normalized[key]
                    )
                )

        self.raw_context[
            "time_range"
        ] = normalized

    # =========================================================================
    # Reference resolution
    # =========================================================================

    def resolve_references(
        self,
        query: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        Resolve conversational references using actual context.

        Examples:

            "What changed here?"
                -> uses active map/AOI context if available.

            "How much did it expand?"
                -> inherits the previous grounded target/location if available.

        This method never invents:
            - baseline dates
            - coordinates
            - AOIs
            - measurements
        """

        original = str(
            query
            or ""
        ).strip()

        if not original:
            return original, self.get_context_snapshot()

        context = self.get_context_snapshot()

        spatial = self.resolve_spatial_context(
            original
        )

        temporal = self.resolve_temporal_context(
            original
        )

        reference_resolution = {
            "spatial": spatial.to_dict(),
            "temporal": temporal.to_dict(),
            "is_follow_up": self.is_follow_up_query(
                original
            ),
            "resolved_references": [],
            "unresolved_references": [],
        }

        normalized_query = self._clean_text(
            original
        )

        # --------------------------------------------------------------
        # Spatial deictic references
        # --------------------------------------------------------------

        if self._contains_deictic_reference(
            normalized_query
        ):
            if spatial.is_resolved:
                reference_resolution[
                    "resolved_references"
                ].append(
                    "spatial_deictic"
                )
            else:
                reference_resolution[
                    "unresolved_references"
                ].append(
                    "spatial_deictic"
                )

        # --------------------------------------------------------------
        # Target references
        # --------------------------------------------------------------

        if self._contains_target_pronoun(
            normalized_query
        ):
            target = self.get_last_target()

            if target:
                context[
                    "resolved_target"
                ] = target

                reference_resolution[
                    "resolved_references"
                ].append(
                    "previous_target"
                )
            else:
                reference_resolution[
                    "unresolved_references"
                ].append(
                    "previous_target"
                )

        # --------------------------------------------------------------
        # Previous location
        # --------------------------------------------------------------

        if self._contains_deictic_reference(
            normalized_query
        ):
            if spatial.is_resolved:
                context[
                    "resolved_location"
                ] = spatial.to_dict()

        # --------------------------------------------------------------
        # Entity switch
        # --------------------------------------------------------------

        entity_switch = self.resolve_entity_switch(
            original
        )

        if entity_switch:
            context[
                "entity_switch"
            ] = entity_switch

            if entity_switch.get(
                "requires_clarification"
            ):
                reference_resolution[
                    "unresolved_references"
                ].append(
                    "entity_switch"
                )
            else:
                reference_resolution[
                    "resolved_references"
                ].append(
                    "entity_switch"
                )

        # --------------------------------------------------------------
        # Record temporal context
        # --------------------------------------------------------------

        context[
            "resolved_temporal_context"
        ] = temporal.to_dict()

        # --------------------------------------------------------------
        # Do not rewrite scientific meaning.
        #
        # The planner receives the original query plus resolved context.
        # This prevents context resolution from silently changing the user's
        # intent.
        # --------------------------------------------------------------

        context[
            "_reference_resolution"
        ] = reference_resolution

        return original, context

    @staticmethod
    def _contains_target_pronoun(
        query: str,
    ) -> bool:
        normalized = ContextEngine._clean_text(
            query
        )

        for term in ContextEngine.PRONOUN_TARGET_TERMS:
            if re.search(
                rf"\b{re.escape(term)}\b",
                normalized,
            ):
                return True

        return False

    # =========================================================================
    # Ambiguity
    # =========================================================================

    def detect_ambiguity(
        self,
        query_text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Detect genuinely ambiguous user requests.

        Context may reduce ambiguity only when the context contains actual
        analytical information. It does not manufacture an interpretation.
        """

        query = self._clean_text(
            query_text
        )

        if not query:
            return {
                "type": "empty_query",
                "message": "Please enter an analysis request.",
                "options": [],
            }

        active_context = (
            context
            if isinstance(
                context,
                dict,
            )
            else self.raw_context
        )

        # --------------------------------------------------------------
        # Growth ambiguity
        # --------------------------------------------------------------

        if re.fullmatch(
            r"(?:is\s+(?:this\s+place|it)\s+growing\??|"
            r"any\s+growth\??)",
            query,
            flags=re.IGNORECASE,
        ):
            return {
                "type": "ambiguous_growth",
                "message": (
                    "What type of growth should I analyze?"
                ),
                "options": [
                    {
                        "label": "Urban & Construction",
                        "query": (
                            "Analyze urban expansion and new "
                            "building development in this area"
                        ),
                    },
                    {
                        "label": "Vegetation",
                        "query": (
                            "Analyze vegetation growth and loss "
                            "in this area"
                        ),
                    },
                    {
                        "label": "Water",
                        "query": (
                            "Analyze surface water extent and "
                            "water-body changes in this area"
                        ),
                    },
                ],
            }

        # --------------------------------------------------------------
        # Generic change ambiguity
        # --------------------------------------------------------------

        if re.fullmatch(
            r"(?:what\s+changed|what\s+is\s+new)\??",
            query,
            flags=re.IGNORECASE,
        ):
            return {
                "type": "ambiguous_change_target",
                "message": (
                    "What type of change should I focus on?"
                ),
                "options": [
                    {
                        "label": "All Detectable Changes",
                        "query": (
                            "Detect meaningful surface changes "
                            "between the available observations"
                        ),
                    },
                    {
                        "label": "New Construction",
                        "query": (
                            "Detect new construction and built-up "
                            "development"
                        ),
                    },
                    {
                        "label": "Vegetation",
                        "query": (
                            "Analyze vegetation gain and loss "
                            "between the available observations"
                        ),
                    },
                    {
                        "label": "Water",
                        "query": (
                            "Analyze surface water extent and "
                            "water-body changes"
                        ),
                    },
                ],
            }

        # --------------------------------------------------------------
        # Generic "growth" with actual focus
        # --------------------------------------------------------------

        if "growth" in query:
            focus = (
                active_context.get(
                    "active_focus"
                )
                or active_context.get(
                    "last_target"
                )
            )

            if focus:
                return None

        return None

    # =========================================================================
    # Context mutation from query
    # =========================================================================

    def update_context(
        self,
        *,
        intent: str | None = None,
        target: str | None = None,
        operation: str | None = None,
        location: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        input_assets: list[dict[str, Any]] | None = None,
        evidence: list[Any] | None = None,
        map_context: dict[str, Any] | None = None,
    ) -> None:
        """
        Update context from already-resolved application state.

        No scientific values are generated.
        """

        if intent:
            self.raw_context[
                "intent"
            ] = str(intent)

            self.raw_context[
                "user_intent"
            ] = {
                "intent": str(intent)
            }

        if target:
            self.raw_context[
                "target"
            ] = str(target)

            self.raw_context[
                "active_focus"
            ] = str(target)

        if operation:
            self.raw_context[
                "operation"
            ] = str(operation)

        if isinstance(
            location,
            dict,
        ):
            self.set_active_aoi(
                location
            )

        if isinstance(
            temporal,
            dict,
        ):
            self.set_time_range(
                temporal
            )

        if input_assets is not None:
            self.raw_context[
                "image_assets"
            ] = copy.deepcopy(
                input_assets
            )

            self.image_count = len(
                input_assets
            )

            self.has_images = (
                self.image_count > 0
            )

            self.raw_context[
                "image_count"
            ] = self.image_count

            self.raw_context[
                "has_images"
            ] = self.has_images

        if evidence is not None:
            self.set_available_evidence(
                evidence
            )

        if map_context is not None:
            self.set_map_context(
                map_context
            )

    # =========================================================================
    # Utility state helpers
    # =========================================================================

    def get_actual_sensor(
        self,
    ) -> str | None:
        """
        Return an explicitly supplied sensor.

        Never returns a default satellite.
        """

        return self.selected_sensor

    def get_image_count(
        self,
    ) -> int:
        return self.image_count

    def has_actual_images(
        self,
    ) -> bool:
        return self._context_contains_images()

    def get_actual_image_dates(
        self,
    ) -> list[str]:
        return self._actual_image_dates()

    def has_resolved_spatial_context(
        self,
    ) -> bool:
        spatial = self.resolve_spatial_context(
            "here"
        )

        return spatial.is_resolved

    def has_temporal_context(
        self,
    ) -> bool:
        temporal = self.resolve_temporal_context(
            ""
        )

        return bool(
            temporal.start_date
            or temporal.end_date
        )

    # =========================================================================
    # Compatibility aliases
    # =========================================================================

    def resolve_spatial(
        self,
        query: str,
    ) -> ResolvedSpatialContext:
        return self.resolve_spatial_context(
            query
        )

    def resolve_temporal(
        self,
        query: str,
    ) -> ResolvedTemporalContext:
        return self.resolve_temporal_context(
            query
        )


# ============================================================================
# Compatibility aliases
# ============================================================================

ResolvedSpatialContextDict = dict[str, Any]
ResolvedTemporalContextDict = dict[str, Any]