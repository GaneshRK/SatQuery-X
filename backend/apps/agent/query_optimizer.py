from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
from django.utils import timezone


@dataclass
class StructuredQueryPlan:
    intent: str
    target: str
    operation: str
    aoi: Dict[str, Any]
    time_range: Dict[str, str]
    modalities: List[str]
    analysis: List[str]
    external_evidence_required: bool
    external_query: str = ""
    is_follow_up: bool = False
    requested_measurements: List[str] = field(default_factory=list)
    confidence_threshold: float = 0.70
    uncertainty_notes: List[str] = field(default_factory=list)
    clarification_prompt: Optional[str] = None
    clarification_options: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "target": self.target,
            "operation": self.operation,
            "aoi": self.aoi,
            "time_range": self.time_range,
            "modalities": self.modalities,
            "analysis": self.analysis,
            "external_evidence_required": self.external_evidence_required,
            "external_query": self.external_query,
            "is_follow_up": self.is_follow_up,
            "requested_measurements": self.requested_measurements,
            "confidence_threshold": self.confidence_threshold,
            "uncertainty_notes": self.uncertainty_notes,
            "clarification_prompt": self.clarification_prompt,
            "clarification_options": self.clarification_options,
        }


class QueryOptimizer:
    """
    Optimizes natural language questions into structured, machine-verifiable execution plans.
    Performs spatial reference grounding, temporal resolution, sensor selection,
    and determines whether external web evidence is required.
    """

    KNOWN_LOCATIONS: Dict[str, Dict[str, Any]] = {
        "chennai": {
            "name": "Chennai Metropolitan Region",
            "bbox": [80.15, 12.95, 80.35, 13.15],
            "coords": [80.2707, 13.0827],
        },
        "pollachi": {
            "name": "Pollachi Agricultural Belt",
            "bbox": [76.92, 10.58, 77.08, 10.72],
            "coords": [77.0064, 10.6582],
        },
        "kaziranga": {
            "name": "Kaziranga National Park & Brahmaputra Basin",
            "bbox": [93.05, 26.50, 93.30, 26.65],
            "coords": [93.1711, 26.5775],
        },
        "brahmaputra": {
            "name": "Brahmaputra River Basin",
            "bbox": [93.00, 26.40, 93.40, 26.80],
            "coords": [93.2000, 26.6000],
        },
        "bengaluru": {
            "name": "Bengaluru IT Corridor",
            "bbox": [77.60, 12.85, 77.78, 13.02],
            "coords": [77.6974, 12.9352],
        },
        "bangalore": {
            "name": "Bengaluru IT Corridor",
            "bbox": [77.60, 12.85, 77.78, 13.02],
            "coords": [77.6974, 12.9352],
        },
        "sundarbans": {
            "name": "Sundarbans Mangrove Delta",
            "bbox": [88.70, 21.80, 89.00, 22.10],
            "coords": [88.8532, 21.9497],
        },
        "mumbai": {
            "name": "Mumbai Metropolitan Region",
            "bbox": [72.77, 18.88, 72.99, 19.27],
            "coords": [72.8777, 19.0760],
        },
        "delhi": {
            "name": "Delhi-NCR Urban Belt",
            "bbox": [77.00, 28.40, 77.35, 28.85],
            "coords": [77.2090, 28.6139],
        },
        "delhi-ncr": {
            "name": "Delhi-NCR Urban Belt",
            "bbox": [77.00, 28.40, 77.35, 28.85],
            "coords": [77.2090, 28.6139],
        },
        "kolkata": {
            "name": "Kolkata Metropolitan Area",
            "bbox": [88.25, 22.45, 88.45, 22.65],
            "coords": [88.3639, 22.5726],
        },
        "hyderabad": {
            "name": "Hyderabad Urban Agglomeration",
            "bbox": [78.35, 17.30, 78.55, 17.50],
            "coords": [78.4867, 17.3850],
        },
        "coimbatore": {
            "name": "Coimbatore Industrial Basin",
            "bbox": [76.90, 10.95, 77.05, 11.08],
            "coords": [76.9558, 11.0168],
        },
        "western ghats": {
            "name": "Western Ghats Ecological Reserve",
            "bbox": [76.80, 10.20, 77.20, 10.60],
            "coords": [77.0000, 10.4000],
        },
    }

    def optimize(self, text: str, session_context: Optional[Dict[str, Any]] = None) -> StructuredQueryPlan:
        session_context = session_context or {}
        from apps.agent.conversation_engine import ConversationEngine
        conv_engine = ConversationEngine()

        # Check for ambiguity
        ambiguity = conv_engine.detect_ambiguity(text, session_context)
        clarification_prompt = ambiguity["clarification_prompt"] if ambiguity else None
        clarification_options = ambiguity["options"] if ambiguity else []

        # Resolve references/pronouns in query text using conversation context
        resolved_text, updated_context = conv_engine.resolve_references(text, session_context)
        q = resolved_text.lower().strip()
        now = timezone.now().date()

        # 1. Resolve Location / AOI
        aoi = self._resolve_aoi(q, session_context)

        # 2. Resolve Temporal Window
        time_range = self._resolve_time_range(q, now)

        # 3. Detect External Web Evidence Requirement
        external_required, ext_query = self._detect_external_necessity(q, aoi["name"])

        # 4. Classify Intent, Modalities, and Analysis Types
        intent, target, operation, modalities, analysis, measurements = self._classify_pipeline(
            q, session_context, external_required
        )

        # 5. Check if Conversational Follow-up
        is_follow_up = False
        history = session_context.get("conversation_history", [])
        if history and any(k in q for k in ("only show", "filter", "which of these", "how many of them", "why", "what about", "focus on", "were they", "how much did")):
            is_follow_up = True

        return StructuredQueryPlan(
            intent=intent,
            target=target,
            operation=operation,
            aoi=aoi,
            time_range=time_range,
            modalities=modalities,
            analysis=analysis,
            external_evidence_required=external_required,
            external_query=ext_query,
            is_follow_up=is_follow_up,
            requested_measurements=measurements,
            confidence_threshold=0.75 if external_required else 0.70,
            clarification_prompt=clarification_prompt,
            clarification_options=clarification_options,
        )

    def _resolve_aoi(self, q: str, session_context: Dict[str, Any]) -> Dict[str, Any]:
        # Check explicit location mentions in query
        for key, loc in self.KNOWN_LOCATIONS.items():
            if key in q:
                return loc

        # Fall back to session context active AOI or default
        if session_context.get("aoi_name") and session_context.get("bbox"):
            return {
                "name": session_context["aoi_name"],
                "bbox": session_context["bbox"],
                "coords": session_context.get("centroid", [80.25, 13.05]),
            }

        return {
            "name": "Designated Area of Interest",
            "bbox": [80.15, 12.95, 80.35, 13.15],
            "coords": [80.2707, 13.0827],
        }

    def _resolve_time_range(self, q: str, now: date) -> Dict[str, str]:
        def _make_range(s: str, e: str) -> Dict[str, str]:
            return {"start": s, "end": e, "start_date": s, "end_date": e}

        # Relative time: "over the last 5 years", "past 5 years"
        last_years_match = re.search(r"(?:last|past|over the past|over the last)\s*(\d+)\s*years?", q)
        if last_years_match:
            n_years = int(last_years_match.group(1))
            start_year = now.year - n_years
            return _make_range(f"{start_year}-01-01", now.strftime("%Y-%m-%d"))

        # Match explicit multi-year range, e.g. "between 2018 and 2026", "2018 to 2024"
        range_match = re.search(r"(?:between|from)?\s*(201\d|202\d)\s*(?:and|to|-)\s*(201\d|202\d)", q)
        if range_match:
            y1 = int(range_match.group(1))
            y2 = int(range_match.group(2))
            start_y, end_y = min(y1, y2), max(y1, y2)
            return _make_range(f"{start_y}-01-01", f"{end_y}-12-31")

        # Match single year, e.g. "in 2018", "since 2020", "before 2022"
        single_year_match = re.search(r"\b(201\d|202\d)\b", q)
        if single_year_match:
            year = int(single_year_match.group(1))
            if "since" in q or "after" in q or "from" in q:
                return _make_range(f"{year}-01-01", now.strftime("%Y-%m-%d"))
            elif "before" in q:
                return _make_range("2016-01-01", f"{year}-12-31")
            else:
                return _make_range(f"{year}-01-01", f"{year}-12-31")

        # Relative time: "5 years ago"
        rel_match = re.search(r"(\d+)\s*years?\s*ago", q)
        if rel_match:
            years_ago = int(rel_match.group(1))
            target_year = now.year - years_ago
            return _make_range(f"{target_year}-01-01", f"{target_year}-12-31")

        if "recent" in q or "latest" in q or "now" in q or "currently" in q:
            start_date = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            return _make_range(start_date, now.strftime("%Y-%m-%d"))

        if "earliest" in q:
            return _make_range("2016-01-01", "2017-12-31")

        # Default multi-year historical comparison window
        return _make_range("2018-01-01", now.strftime("%Y-%m-%d"))

    def _detect_external_necessity(self, q: str, aoi_name: str) -> tuple[bool, str]:
        external_triggers = [
            "why",
            "reason",
            "cause",
            "warning",
            "alert",
            "official",
            "government",
            "drought",
            "rainfall",
            "precipitation",
            "weather",
            "cyclone",
            "flood",
            "inundation",
            "disaster",
            "project",
            "announced",
            "report",
            "policy",
        ]

        if any(trig in q for trig in external_triggers):
            # Formulate targeted web query
            clean_q = re.sub(r"[^\w\s]", "", q).strip()
            ext_query = f"{aoi_name} {clean_q}"
            return True, ext_query

        return False, ""

    def _classify_pipeline(
        self, q: str, session_context: Dict[str, Any], external_required: bool
    ) -> tuple[str, str, str, List[str], List[str], List[str]]:
        modalities = ["optical"]
        analysis = []
        measurements = []

        # UI Navigation command check
        if any(w in q for w in ("show vegetation", "show changes", "show me 2020", "zoom to", "zoom in", "where is it", "show where")):
            analysis.append("ui_action_dispatch")
            return (
                "ui_navigation_command",
                "ui_control",
                "action_dispatch",
                modalities,
                analysis,
                [],
            )

        # Multi-intent check: e.g. "expanded" or "buildings" AND "vegetation"
        if (any(k in q for k in ("urban", "building", "construction", "expansion", "city", "expanded")) and
            any(k in q for k in ("vegetation", "forest", "crop", "canopy", "trees", "greenery"))):
            analysis.extend(["calculate_ndbi", "calculate_ndvi", "bitemporal_built_up_differencing", "bitemporal_ndvi_differencing"])
            measurements.extend(["expansion_hectares", "canopy_loss_hectares", "mean_ndvi"])
            return (
                "multi_intent_urban_vegetation_analysis",
                "mixed_urban_vegetation",
                "fused_bitemporal_differencing",
                modalities,
                analysis,
                measurements,
            )

        # SAR / Flood check
        if any(k in q for k in ("flood", "sar", "radar", "water extent", "monsoon")):
            modalities = ["sar"] if "optical" not in q else ["optical", "sar"]
            analysis.extend(["sar_thresholding", "water_masking"])
            measurements.append("inundated_area_hectares")
            return (
                "flood_inundation_assessment",
                "water_bodies",
                "sar_water_segmentation",
                modalities,
                analysis,
                measurements,
            )

        # Vegetation / Agriculture check
        if any(k in q for k in ("vegetation", "agriculture", "forest", "crop", "canopy", "greenery")):
            analysis.extend(["calculate_ndvi", "canopy_segmentation"])
            measurements.extend(["mean_ndvi", "vegetation_coverage_pct", "canopy_loss_hectares"])
            if any(k in q for k in ("change", "decrease", "increase", "loss", "difference", "between")):
                analysis.append("bitemporal_ndvi_differencing")
                return (
                    "vegetation_temporal_change",
                    "vegetation",
                    "bitemporal_differencing",
                    modalities,
                    analysis,
                    measurements,
                )
            return (
                "vegetation_health_analysis",
                "vegetation",
                "spectral_index_calculation",
                modalities,
                analysis,
                measurements,
            )

        # Urban Expansion / Building / Infrastructure check
        if any(k in q for k in ("building", "urban", "construction", "structure", "expansion", "road")):
            analysis.extend(["calculate_ndbi", "structure_detection", "canny_contours"])
            measurements.extend(["built_up_coverage_pct", "structure_count", "expansion_hectares"])
            if any(k in q for k in ("change", "new", "appeared", "increase", "growth", "between")):
                analysis.append("bitemporal_built_up_differencing")
                return (
                    "urban_expansion_monitoring",
                    "built_up",
                    "structure_change_detection",
                    modalities,
                    analysis,
                    measurements,
                )
            return (
                "infrastructure_detection",
                "structures",
                "object_detection",
                modalities,
                analysis,
                measurements,
            )

        # General Bi-temporal change detection
        if any(k in q for k in ("change", "changed", "before and after", "evolution", "compare")):
            analysis.extend(["spectral_differencing", "polygonization", "change_quantification"])
            measurements.extend(["changed_area_hectares", "change_percentage"])
            return (
                "change_detection",
                "surface_dynamics",
                "bitemporal_differencing",
                modalities,
                analysis,
                measurements,
            )

        # Default VQA / Scene Description
        analysis.append("vlm_multimodal_description")
        return (
            "scene_understanding",
            "general_landcover",
            "vlm_reasoning",
            modalities,
            analysis,
            measurements,
        )
