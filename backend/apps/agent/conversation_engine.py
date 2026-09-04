from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from datetime import datetime


class ConversationEngine:
    """
    Manages multi-turn conversation memory, pronoun/reference resolution,
    ambiguity detection, and dialogue context evolution across turns.
    """

    AMBIGUOUS_PATTERNS = [
        (
            re.compile(r"^(?:is\s+this\s+place\s+growing\??|is\s+it\s+growing\??|any\s+growth\??)$", re.IGNORECASE),
            "Do you mean urban development, agricultural vegetation growth, or surface water expansion?",
            [
                {"label": "Urban & Construction", "query": "Analyze urban expansion and new building clusters in this area"},
                {"label": "Vegetation Canopy", "query": "Analyze agricultural vegetation canopy health and NDVI changes"},
                {"label": "Water Bodies", "query": "Analyze surface water bodies and flood inundation extent"},
            ],
        ),
        (
            re.compile(r"^(?:what\s+changed\??|what\s+is\s+new\??)$", re.IGNORECASE),
            "Do you want me to check new buildings, vegetation loss, water extent, or all major changes?",
            [
                {"label": "All Major Changes", "query": "Detect all significant surface changes between baseline and latest observations"},
                {"label": "New Construction", "query": "Detect new building footprints and urban development"},
                {"label": "Vegetation Changes", "query": "Measure vegetation canopy change and forest loss"},
            ],
        ),
    ]

    @staticmethod
    def get_default_context(session_name: str = "Designated Area of Interest") -> Dict[str, Any]:
        """Generate a complete default conversation context object."""
        return {
            "active_project": {},
            "active_aoi": {
                "name": session_name or "Designated Area of Interest",
                "bbox": [80.15, 12.95, 80.35, 13.15],
                "coords": [80.2707, 13.0827],
            },
            "active_scene": {
                "sensor": "Sentinel-2",
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
            },
            "active_region": {},
            "active_focus": "landscape",
            "selected_dates": ["2020-01-01", datetime.utcnow().strftime("%Y-%m-%d")],
            "selected_scenes": [],
            "active_analysis": {},
            "previous_questions": [],
            "previous_results": [],
            "user_intent": {},
            "conversation_entities": [],
            "current_visual_state": {
                "center": [80.2707, 13.0827],
                "zoom": 11,
                "active_layer": "rgb",
            },
            "available_evidence": [],
        }

    def detect_ambiguity(self, query_text: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determine if query lacks sufficient specificity and requires conversational clarification.
        """
        clean_q = query_text.strip()
        # If user is in an ongoing conversation with a set focus, don't interrupt unnecessarily
        if context.get("active_focus") and context["active_focus"] != "landscape":
            return None

        for pattern, prompt, options in self.AMBIGUOUS_PATTERNS:
            if pattern.search(clean_q):
                return {
                    "is_ambiguous": True,
                    "clarification_prompt": prompt,
                    "options": options,
                }
        return None

    def resolve_references(self, query_text: str, context: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """
        Resolve anaphoric pronouns ("they", "it", "this part", "here", "the construction")
        against prior dialogue state and visual context.
        """
        resolved_query = query_text
        updated_context = dict(context or {})
        q_lower = query_text.lower().strip()

        active_focus = updated_context.get("active_focus", "landscape")
        entities = updated_context.get("conversation_entities", [])

        # 1. Update focus if user explicitly redirects focus
        if any(w in q_lower for w in ("focus on the construction", "focus on buildings", "look at buildings", "urban area")):
            active_focus = "built_up"
            updated_context["active_focus"] = "built_up"
            if "built-up infrastructure" not in entities:
                entities.append("built-up infrastructure")
        elif any(w in q_lower for w in ("focus on vegetation", "only look at vegetation", "look at trees", "agricultural")):
            active_focus = "vegetation"
            updated_context["active_focus"] = "vegetation"
            if "vegetation canopy" not in entities:
                entities.append("vegetation canopy")
        elif any(w in q_lower for w in ("focus on water", "look at the lake", "look at the river", "flooding")):
            active_focus = "water"
            updated_context["active_focus"] = "water"
            if "surface water bodies" not in entities:
                entities.append("surface water bodies")

        # 2. Pronoun & entity resolution
        # "were they there in 2019?", "were they there before?"
        if re.search(r"\bwere\s+they\s+there\b", q_lower) or re.search(r"\bdid\s+they\s+exist\b", q_lower):
            target_str = active_focus if active_focus != "landscape" else "built-up structures"
            year_match = re.search(r"\b(201\d|202\d)\b", q_lower)
            baseline_year = year_match.group(1) if year_match else "2018"
            resolved_query = f"Compare baseline observation from {baseline_year} with current observation to determine whether {target_str} were present."

        # "how much did they expand?", "how much did it expand?"
        elif re.search(r"\bhow\s+much\s+did\s+(?:they|it)\s+(?:expand|grow|change)\b", q_lower):
            target_str = active_focus if active_focus != "landscape" else "built-up area"
            resolved_query = f"Quantify metric area expansion in hectares for {target_str} in this designated region."

        # "what about this part?", "analyze this part", "what is happening here?"
        elif any(phrase in q_lower for phrase in ("this part", "this area", "here", "selected region")):
            aoi_name = updated_context.get("active_aoi", {}).get("name", "the selected region")
            if "what is happening" in q_lower:
                resolved_query = f"Analyze landcover, terrain features, and recent surface changes in {aoi_name}."
            else:
                resolved_query = f"{query_text} (scoped to {aoi_name})"

        # "show me exactly where"
        elif any(phrase in q_lower for phrase in ("show me exactly where", "where is it", "show the changes", "show where")):
            target_str = active_focus if active_focus != "landscape" else "detected change features"
            resolved_query = f"Zoom to and highlight all localized vector polygons for {target_str}."

        # "give me a report", "create a report", "summarize everything"
        elif any(phrase in q_lower for phrase in ("give me a report", "create a report", "generate report", "summarize everything")):
            aoi_name = updated_context.get("active_aoi", {}).get("name", "this area")
            resolved_query = f"Generate an executive geospatial intelligence summary report for {aoi_name} synthesizing all accumulated evidence."

        updated_context["conversation_entities"] = entities
        return resolved_query, updated_context

    def update_context_after_query(
        self,
        context: Dict[str, Any],
        query_text: str,
        answer: str,
        plan: Dict[str, Any],
        measurements: List[Dict[str, Any]],
        ui_actions: List[Dict[str, Any]] = None,
        visual_state: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Evolve the conversation context state after successful execution."""
        ctx = dict(context or self.get_default_context())

        # Update previous questions
        prev_q = list(ctx.get("previous_questions") or [])
        prev_q.append(query_text)
        ctx["previous_questions"] = prev_q[-15:]

        # Update previous results
        prev_res = list(ctx.get("previous_results") or [])
        prev_res.append({
            "query": query_text,
            "answer_excerpt": answer[:200] if answer else "",
            "measurements": measurements or [],
            "timestamp": datetime.utcnow().isoformat(),
        })
        ctx["previous_results"] = prev_res[-10:]

        # Update AOI if plan has one
        if plan.get("aoi") and isinstance(plan["aoi"], dict):
            ctx["active_aoi"] = plan["aoi"]

        # Update selected dates if plan has time_range
        if plan.get("time_range") and isinstance(plan["time_range"], dict):
            s = plan["time_range"].get("start")
            e = plan["time_range"].get("end")
            if s and e:
                ctx["selected_dates"] = [s, e]

        # Update visual state if passed
        if visual_state:
            ctx["current_visual_state"] = visual_state

        # Update entities
        entities = list(ctx.get("conversation_entities") or [])
        target = plan.get("target")
        if target and target not in entities:
            entities.append(target)
        ctx["conversation_entities"] = entities[-10:]

        return ctx
