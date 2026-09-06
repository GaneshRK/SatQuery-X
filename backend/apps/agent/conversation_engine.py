"""
SatQuery-X Conversation Engine
==============================

Conversation-level state management for SatQuery-X.

Responsibilities
----------------
- Detect genuinely ambiguous follow-up questions.
- Resolve conversational references such as:
    "here"
    "this area"
    "that location"
    "it"
    "they"
- Preserve active map/AOI context.
- Preserve actual imagery and analysis evidence references.
- Track conversational focus.
- Track previous analysis results.
- Support multi-turn follow-up queries.
- Never fabricate scientific information.

Important
---------
This module is NOT a scientific analysis engine.

It must never invent:
- coordinates
- bounding boxes
- geometry
- imagery
- sensors
- dates
- measurements
- confidence
- scientific conclusions
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone as dt_timezone
from typing import Any


class ConversationEngine:
    """
    Multi-turn conversation manager.

    Conversation context is treated as a combination of:

        1. active map state
        2. active AOI
        3. uploaded imagery references
        4. previous analysis outputs
        5. active analytical focus
        6. conversation entities
        7. conversation history

    Scientific truth remains owned by the execution/evidence layer.
    """

    MAX_HISTORY = 20
    MAX_RESULTS = 10
    MAX_ENTITIES = 20
    MAX_QUESTIONS = 20

    # ------------------------------------------------------------------
    # Ambiguity patterns
    # ------------------------------------------------------------------

    AMBIGUOUS_PATTERNS = [
        (
            re.compile(
                r"^(?:"
                r"is\s+this\s+place\s+growing"
                r"|is\s+it\s+growing"
                r"|any\s+growth"
                r")\??$",
                re.IGNORECASE,
            ),
            (
                "What kind of growth do you want me to analyze: "
                "urban development, vegetation, or water extent?"
            ),
            [
                {
                    "label": "Urban & Construction",
                    "query": (
                        "Analyze urban expansion and new "
                        "building clusters in this area"
                    ),
                },
                {
                    "label": "Vegetation",
                    "query": (
                        "Analyze vegetation condition and "
                        "vegetation change in this area"
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
        ),
        (
            re.compile(
                r"^(?:"
                r"what\s+changed"
                r"|what\s+is\s+new"
                r")\??$",
                re.IGNORECASE,
            ),
            (
                "What type of change should I focus on: "
                "urban development, vegetation, water, "
                "or all detectable changes?"
            ),
            [
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
                        "Detect new construction and "
                        "built-up development"
                    ),
                },
                {
                    "label": "Vegetation",
                    "query": (
                        "Analyze vegetation gain and loss "
                        "between the available observations"
                    ),
                },
            ],
        ),
    ]

    # ------------------------------------------------------------------
    # Focus phrases
    # ------------------------------------------------------------------

    FOCUS_PATTERNS = {
        "built_up": (
            "focus on construction",
            "focus on buildings",
            "look at buildings",
            "focus on urban",
            "urban development",
            "new construction",
            "built-up",
            "built up",
            "buildings",
        ),
        "vegetation": (
            "focus on vegetation",
            "look at vegetation",
            "only look at vegetation",
            "look at trees",
            "focus on crops",
            "focus on agriculture",
            "agricultural area",
            "vegetation",
            "forest",
            "crops",
        ),
        "water": (
            "focus on water",
            "look at water",
            "look at the lake",
            "look at the river",
            "focus on flooding",
            "focus on water",
            "surface water",
            "water bodies",
            "flood",
        ),
        "roads": (
            "focus on roads",
            "look at roads",
            "road network",
            "roads",
        ),
        "damage": (
            "focus on damage",
            "look at damage",
            "damaged areas",
            "damage",
        ),
    }

    # ------------------------------------------------------------------
    # Conversational reference patterns
    # ------------------------------------------------------------------

    SPATIAL_REFERENCE_TERMS = (
        "here",
        "this place",
        "this area",
        "this location",
        "this map",
        "this scene",
        "current map",
        "selected area",
        "selected region",
        "selected location",
        "highlighted area",
        "highlighted region",
        "that area",
        "that location",
        "same area",
        "same place",
        "same location",
        "there",
    )

    TARGET_REFERENCE_PATTERNS = (
        r"\bit\b",
        r"\bthey\b",
        r"\bthem\b",
        r"\bthese\b",
        r"\bthose\b",
        r"\bthis\b",
        r"\bthat\b",
    )

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        context: dict[str, Any] | None = None,
    ):
        self.context = self._copy_context(
            context
            if isinstance(context, dict)
            else self.get_default_context()
        )

        self._ensure_context_shape()

    # =========================================================================
    # Context creation
    # =========================================================================

    @staticmethod
    def get_default_context(
        session_name: str = "Designated Area of Interest",
    ) -> dict[str, Any]:
        """
        Return a genuinely empty conversation context.

        No geographic coordinates, dates, sensors, imagery, or viewport
        values are inserted here.
        """

        name = (
            str(session_name).strip()
            if session_name
            else "Designated Area of Interest"
        )

        return {
            "active_project": {},

            "active_aoi": {
                "name": name,
            },

            "active_map_context": {},

            "active_scene": {},

            "active_region": {},

            "active_focus": None,

            "target": None,

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

            "modalities": [],

            "time_range": {},

            "conversation_history": [],

            "last_resolved_query": None,

            "last_query_id": None,

            "last_answer": None,

            "last_execution_trace": [],

        }

    # =========================================================================
    # Context shape
    # =========================================================================

    def _ensure_context_shape(self) -> None:
        defaults = self.get_default_context()

        for key, value in defaults.items():
            if key not in self.context:
                self.context[key] = copy.deepcopy(value)

    @staticmethod
    def _copy_context(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return copy.deepcopy(context)
        except Exception:
            return dict(context)

    # =========================================================================
    # Ambiguity
    # =========================================================================

    def detect_ambiguity(
        self,
        query_text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Detect genuinely underspecified conversational queries.

        A previously grounded focus is respected, but a new query that
        explicitly changes scope is still allowed to be clarified.
        """

        clean_query = self._clean_text(query_text)

        if not clean_query:
            return {
                "is_ambiguous": True,
                "clarification_required": True,
                "clarification_prompt": (
                    "What would you like me to analyze?"
                ),
                "options": [],
            }

        active_context = (
            context
            if isinstance(context, dict)
            else self.context
        )

        active_focus = active_context.get(
            "active_focus"
        )

        for pattern, prompt, options in self.AMBIGUOUS_PATTERNS:
            if not pattern.fullmatch(clean_query):
                continue

            # If the conversation has an explicit active focus, preserve it.
            # However, only suppress clarification when the focus is genuinely
            # meaningful and not merely a generic value.
            if active_focus in {
                "built_up",
                "vegetation",
                "water",
                "roads",
                "damage",
            }:
                return None

            return {
                "is_ambiguous": True,
                "clarification_required": True,
                "clarification_prompt": prompt,
                "options": copy.deepcopy(options),
            }

        return None

    # =========================================================================
    # Reference resolution
    # =========================================================================

    def resolve_references(
        self,
        query_text: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Resolve conversational references against grounded context.

        The returned query is an instruction for the downstream planner.

        This method never converts missing context into fabricated geography,
        dates, sensors, measurements, or scientific conclusions.
        """

        ctx = self._copy_context(
            context
            if isinstance(context, dict)
            else self.context
        )

        self._ensure_context_shape_for(ctx)

        original_query = (
            str(query_text or "").strip()
        )

        if not original_query:
            return "", ctx

        normalized = self._clean_text(
            original_query
        )

        # ------------------------------------------------------------------
        # Update explicit analytical focus.
        # ------------------------------------------------------------------

        active_focus = self._detect_focus(
            normalized
        )

        if active_focus:
            ctx["active_focus"] = active_focus

            focus_label = {
                "built_up": "built-up infrastructure",
                "vegetation": "vegetation",
                "water": "surface water",
                "roads": "roads",
                "damage": "damage",
            }.get(active_focus)

            if focus_label:
                self._append_unique(
                    ctx,
                    "conversation_entities",
                    focus_label,
                    self.MAX_ENTITIES,
                )

        # ------------------------------------------------------------------
        # Determine actual previous target.
        # ------------------------------------------------------------------

        previous_target = (
            self._get_last_target(ctx)
        )

        if not previous_target:
            previous_target = ctx.get(
                "target"
            )

        # ------------------------------------------------------------------
        # Resolve spatial context.
        # ------------------------------------------------------------------

        location = self._get_active_location(
            ctx
        )

        # ------------------------------------------------------------------
        # "They were there" / "did they exist?"
        # ------------------------------------------------------------------

        if (
            re.search(
                r"\bwere\s+they\s+there\b",
                normalized,
            )
            or re.search(
                r"\bdid\s+they\s+exist\b",
                normalized,
            )
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Determine whether the previously identified "
                f"{target} were present in the requested "
                "observation, using only actual imagery evidence."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "How much did they expand/grow/change?"
        # ------------------------------------------------------------------

        if re.search(
            r"\bhow\s+much\s+did\s+"
            r"(?:they|it)\s+"
            r"(?:expand|grow|change)\b",
            normalized,
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Quantify the change in the previously identified "
                f"{target}, using actual measurements only when "
                "the required geospatial evidence is available."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "How many?"
        # ------------------------------------------------------------------

        if re.fullmatch(
            r"how\s+many(?:\s+of\s+them)?\??",
            normalized,
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Count the previously identified "
                f"{target}, using actual model or GIS detections."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "Why did it change?"
        # ------------------------------------------------------------------

        if re.fullmatch(
            r"why\s+did\s+it\s+change\??",
            normalized,
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Analyze the observed change affecting "
                f"{target}. Separate directly observed evidence "
                "from possible contextual explanations and do not "
                "claim a cause unless supported by evidence."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "What caused it?"
        # ------------------------------------------------------------------

        if re.fullmatch(
            r"what\s+caused\s+it\??",
            normalized,
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Assess possible causes of the observed change in "
                f"{target}. Report only causes supported by available "
                "evidence and clearly distinguish them from hypotheses."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "Where is it?"
        # ------------------------------------------------------------------

        if (
            re.fullmatch(
                r"where(?:\s+is\s+it)?\??",
                normalized,
            )
            or "show me where" in normalized
            or "show where" in normalized
            or "show me exactly where" in normalized
            or "highlight the changes" in normalized
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            resolved = (
                "Locate the spatial evidence for "
                f"{target}, using actual georeferenced outputs "
                "when available."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # "This area / here / this place"
        # ------------------------------------------------------------------

        if self._contains_spatial_reference(
            normalized
        ):
            if (
                "what is happening" in normalized
                or "what's happening" in normalized
            ):
                if location:
                    display_name = (
                        location.get("name")
                        or location.get("display_name")
                        if isinstance(location, dict)
                        else str(location)
                    )

                    if display_name:
                        resolved = (
                            "Analyze the requested phenomenon in "
                            f"{display_name}, using the active map "
                            "or AOI context."
                        )
                    else:
                        resolved = (
                            "Analyze the requested phenomenon in "
                            "the active map/AOI context."
                        )
                else:
                    resolved = (
                        "Analyze the requested phenomenon in the "
                        "active map/AOI context."
                    )

                return self._finalize_resolution(
                    resolved,
                    ctx,
                )

            # For ordinary queries such as:
            # "show vegetation here"
            # preserve the user's wording. ContextEngine and planner can
            # attach the actual map context separately.
            return self._finalize_resolution(
                original_query,
                ctx,
            )

        # ------------------------------------------------------------------
        # Report requests.
        # ------------------------------------------------------------------

        if self._contains_any(
            normalized,
            (
                "give me a report",
                "create a report",
                "generate a report",
                "summarize everything",
                "summary of the analysis",
            ),
        ):
            scope = (
                self._scope_description(ctx)
            )

            resolved = (
                "Generate an evidence-based geospatial intelligence "
                f"summary for {scope}, using only completed analysis "
                "results and available evidence."
            )

            return self._finalize_resolution(
                resolved,
                ctx,
            )

        # ------------------------------------------------------------------
        # Generic pronoun follow-up.
        # ------------------------------------------------------------------

        if self._contains_target_reference(
            normalized
        ):
            target = (
                previous_target
                or self._fallback_target(
                    ctx
                )
            )

            if target:
                ctx["resolved_target"] = target

        return self._finalize_resolution(
            original_query,
            ctx,
        )

    # =========================================================================
    # Context update
    # =========================================================================

    def update_context_after_query(
        self,
        context: dict[str, Any] | None,
        query_text: str,
        answer: str | None,
        plan: dict[str, Any] | None,
        measurements: list[dict[str, Any]] | None,
        ui_actions: list[dict[str, Any]] | None = None,
        visual_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update conversational state after a completed execution.

        Only values explicitly supplied by the caller are persisted.
        """

        ctx = self._copy_context(
            context
            if isinstance(context, dict)
            else self.get_default_context()
        )

        self._ensure_context_shape_for(ctx)

        safe_plan = (
            plan
            if isinstance(plan, dict)
            else {}
        )

        safe_measurements = (
            measurements
            if isinstance(measurements, list)
            else []
        )

        now = datetime.now(
            dt_timezone.utc
        ).isoformat()

        # ------------------------------------------------------------------
        # Question history
        # ------------------------------------------------------------------

        questions = list(
            ctx.get(
                "previous_questions",
                [],
            )
            or []
        )

        if query_text:
            questions.append(
                str(query_text).strip()
            )

        ctx["previous_questions"] = (
            questions[-self.MAX_QUESTIONS:]
        )

        # ------------------------------------------------------------------
        # Result history
        # ------------------------------------------------------------------

        results = list(
            ctx.get(
                "previous_results",
                [],
            )
            or []
        )

        result_record = {
            "query": str(query_text or ""),
            "answer_excerpt": (
                str(answer)[:500]
                if answer
                else None
            ),
            "measurements": copy.deepcopy(
                safe_measurements
            ),
            "timestamp": now,
        }

        results.append(
            result_record
        )

        ctx["previous_results"] = (
            results[-self.MAX_RESULTS:]
        )

        # ------------------------------------------------------------------
        # Target
        # ------------------------------------------------------------------

        target = self._extract_plan_value(
            safe_plan,
            "target",
        )

        if target:
            target = str(target).strip()

            if target:
                ctx["target"] = target

                self._append_unique(
                    ctx,
                    "conversation_entities",
                    target,
                    self.MAX_ENTITIES,
                )

        # ------------------------------------------------------------------
        # Active focus
        # ------------------------------------------------------------------

        plan_focus = self._extract_plan_value(
            safe_plan,
            "active_focus",
        )

        if plan_focus:
            ctx["active_focus"] = (
                str(plan_focus).strip()
            )

        # ------------------------------------------------------------------
        # Actual AOI/spatial context
        # ------------------------------------------------------------------

        plan_aoi = (
            safe_plan.get("aoi")
        )

        if self._has_grounded_spatial_content(
            plan_aoi
        ):
            ctx["active_aoi"] = copy.deepcopy(
                plan_aoi
            )

        spatial_context = (
            safe_plan.get(
                "spatial_context"
            )
        )

        if self._has_grounded_spatial_content(
            spatial_context
        ):
            ctx["active_map_context"] = (
                copy.deepcopy(
                    spatial_context
                )
            )

        # ------------------------------------------------------------------
        # Actual time range
        # ------------------------------------------------------------------

        time_range = (
            safe_plan.get("time_range")
        )

        if self._has_grounded_time_content(
            time_range
        ):
            ctx["time_range"] = copy.deepcopy(
                time_range
            )

        # ------------------------------------------------------------------
        # Actual scenes
        # ------------------------------------------------------------------

        scenes = (
            safe_plan.get("selected_scenes")
            or safe_plan.get("scenes")
        )

        if isinstance(
            scenes,
            list,
        ) and scenes:
            ctx["selected_scenes"] = copy.deepcopy(
                scenes
            )

        # ------------------------------------------------------------------
        # Actual imagery
        # ------------------------------------------------------------------

        image_assets = (
            safe_plan.get("image_assets")
            or safe_plan.get("input_assets")
        )

        if isinstance(
            image_assets,
            list,
        ):
            ctx["image_assets"] = copy.deepcopy(
                image_assets
            )
            ctx["image_count"] = len(
                image_assets
            )
            ctx["has_images"] = bool(
                image_assets
            )

        # ------------------------------------------------------------------
        # Sensor only when explicitly returned.
        # ------------------------------------------------------------------

        sensor = safe_plan.get(
            "sensor"
        )

        if sensor:
            ctx["sensor"] = sensor

        modalities = safe_plan.get(
            "modalities"
        )

        if isinstance(
            modalities,
            list,
        ) and modalities:
            ctx["modalities"] = copy.deepcopy(
                modalities
            )

        # ------------------------------------------------------------------
        # Evidence
        # ------------------------------------------------------------------

        evidence = (
            safe_plan.get(
                "evidence"
            )
        )

        if isinstance(
            evidence,
            list,
        ):
            ctx["available_evidence"] = copy.deepcopy(
                evidence
            )

        # ------------------------------------------------------------------
        # Active analysis
        # ------------------------------------------------------------------

        active_analysis = (
            safe_plan.get(
                "active_analysis"
            )
        )

        if isinstance(
            active_analysis,
            dict,
        ):
            ctx["active_analysis"] = copy.deepcopy(
                active_analysis
            )

        # ------------------------------------------------------------------
        # Visual/map state
        # ------------------------------------------------------------------

        if isinstance(
            visual_state,
            dict,
        ):
            if visual_state:
                ctx["current_visual_state"] = copy.deepcopy(
                    visual_state
                )

                viewport = visual_state.get(
                    "viewport"
                )

                if isinstance(
                    viewport,
                    dict,
                ):
                    ctx["current_viewport"] = copy.deepcopy(
                        viewport
                    )

        # ------------------------------------------------------------------
        # UI actions
        # ------------------------------------------------------------------

        if isinstance(
            ui_actions,
            list,
        ):
            ctx["last_ui_actions"] = copy.deepcopy(
                ui_actions
            )

        # ------------------------------------------------------------------
        # Conversation history
        # ------------------------------------------------------------------

        history = list(
            ctx.get(
                "conversation_history",
                [],
            )
            or []
        )

        history.append(
            {
                "turn_index": len(history) + 1,
                "query_text": str(
                    query_text or ""
                ),
                "answer_excerpt": (
                    str(answer)[:500]
                    if answer
                    else None
                ),
                "target": target,
                "location": self._location_for_history(
                    ctx
                ),
                "timestamp": now,
            }
        )

        ctx["conversation_history"] = (
            history[-self.MAX_HISTORY:]
        )

        # ------------------------------------------------------------------
        # Last resolved query
        # ------------------------------------------------------------------

        if query_text:
            ctx["last_resolved_query"] = (
                str(query_text)
            )

        if answer is not None:
            ctx["last_answer"] = str(
                answer
            )

        return ctx

    # =========================================================================
    # Focus helpers
    # =========================================================================

    def _detect_focus(
        self,
        query: str,
    ) -> str | None:
        for focus, phrases in self.FOCUS_PATTERNS.items():
            for phrase in phrases:
                if phrase in query:
                    return focus

        return None

    # =========================================================================
    # Context helpers
    # =========================================================================

    @staticmethod
    def _ensure_context_shape_for(
        context: dict[str, Any],
    ) -> None:
        defaults = ConversationEngine.get_default_context()

        for key, value in defaults.items():
            if key not in context:
                context[key] = copy.deepcopy(
                    value
                )

    @staticmethod
    def _extract_plan_value(
        plan: dict[str, Any],
        key: str,
    ) -> Any:
        if key in plan:
            return plan.get(key)

        nested = plan.get(
            "understanding"
        )

        if isinstance(
            nested,
            dict,
        ) and key in nested:
            return nested.get(key)

        return None

    @staticmethod
    def _has_grounded_spatial_content(
        value: Any,
    ) -> bool:
        if not isinstance(
            value,
            dict,
        ):
            return False

        for key in (
            "geometry",
            "bbox",
            "latitude",
            "longitude",
            "coordinates",
            "name",
            "display_name",
            "place_id",
        ):
            current = value.get(
                key
            )

            if current is not None:
                if current != "":
                    return True

        return False

    @staticmethod
    def _has_grounded_time_content(
        value: Any,
    ) -> bool:
        if not isinstance(
            value,
            dict,
        ):
            return False

        return any(
            value.get(key)
            for key in (
                "start",
                "end",
                "start_date",
                "end_date",
            )
        )

    # =========================================================================
    # Location helpers
    # =========================================================================

    @staticmethod
    def _get_active_location(
        context: dict[str, Any],
    ) -> dict[str, Any] | str | None:
        for key in (
            "active_map_context",
            "active_aoi",
            "active_region",
        ):
            value = context.get(
                key
            )

            if isinstance(
                value,
                dict,
            ):
                if ConversationEngine._has_grounded_spatial_content(
                    value
                ):
                    return copy.deepcopy(
                        value
                    )

        visual_state = context.get(
            "current_visual_state"
        )

        if isinstance(
            visual_state,
            dict,
        ):
            location = visual_state.get(
                "location"
            )

            if isinstance(
                location,
                dict,
            ):
                if ConversationEngine._has_grounded_spatial_content(
                    location
                ):
                    return copy.deepcopy(
                        location
                    )

        return None

    @staticmethod
    def _location_for_history(
        context: dict[str, Any],
    ) -> Any:
        location = ConversationEngine._get_active_location(
            context
        )

        if location is None:
            return None

        if isinstance(
            location,
            dict,
        ):
            return {
                key: location[key]
                for key in (
                    "name",
                    "display_name",
                    "latitude",
                    "longitude",
                    "bbox",
                    "place_id",
                )
                if key in location
            }

        return location

    @staticmethod
    def _scope_description(
        context: dict[str, Any],
    ) -> str:
        location = ConversationEngine._get_active_location(
            context
        )

        if isinstance(
            location,
            dict,
        ):
            return (
                location.get("name")
                or location.get("display_name")
                or "the selected analysis context"
            )

        if location:
            return str(location)

        return "the selected analysis context"

    # =========================================================================
    # Target helpers
    # =========================================================================

    @staticmethod
    def _get_last_target(
        context: dict[str, Any],
    ) -> str | None:
        history = context.get(
            "conversation_history",
            [],
        )

        if isinstance(
            history,
            list,
        ):
            for turn in reversed(history):
                if not isinstance(
                    turn,
                    dict,
                ):
                    continue

                target = turn.get(
                    "target"
                )

                if target:
                    return str(target)

        target = context.get(
            "target"
        )

        if target:
            return str(target)

        entities = context.get(
            "conversation_entities",
            [],
        )

        if isinstance(
            entities,
            list,
        ):
            for entity in reversed(entities):
                if entity:
                    return str(entity)

        return None

    @staticmethod
    def _fallback_target(
        context: dict[str, Any],
    ) -> str:
        focus = context.get(
            "active_focus"
        )

        return {
            "built_up": "built-up structures",
            "vegetation": "vegetation",
            "water": "surface water",
            "roads": "roads",
            "damage": "damaged areas",
        }.get(
            focus,
            "the selected analysis target",
        )

    # =========================================================================
    # Reference helpers
    # =========================================================================

    @classmethod
    def _contains_spatial_reference(
        cls,
        text: str,
    ) -> bool:
        for term in cls.SPATIAL_REFERENCE_TERMS:
            if re.search(
                rf"\b{re.escape(term)}\b",
                text,
            ):
                return True

        return False

    @classmethod
    def _contains_target_reference(
        cls,
        text: str,
    ) -> bool:
        return any(
            re.search(
                pattern,
                text,
            )
            for pattern in cls.TARGET_REFERENCE_PATTERNS
        )

    # =========================================================================
    # Generic helpers
    # =========================================================================

    @staticmethod
    def _clean_text(
        text: str | None,
    ) -> str:
        value = (
            str(text or "")
            .strip()
            .lower()
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value

    @staticmethod
    def _contains_any(
        text: str,
        phrases: tuple[str, ...],
    ) -> bool:
        return any(
            phrase in text
            for phrase in phrases
        )

    @staticmethod
    def _append_unique(
        context: dict[str, Any],
        key: str,
        value: Any,
        maximum: int,
    ) -> None:
        items = list(
            context.get(
                key,
                [],
            )
            or []
        )

        if value not in items:
            items.append(value)

        context[key] = items[-maximum:]

    # =========================================================================
    # Finalization
    # =========================================================================

    @staticmethod
    def _finalize_resolution(
        resolved_query: str,
        context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        updated = copy.deepcopy(
            context
        )

        updated[
            "last_resolved_query"
        ] = resolved_query

        return (
            resolved_query,
            updated,
        )