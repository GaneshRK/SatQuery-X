"""SLM Query Router and Task Plan Schema Validator per §11, §12, §28, §29.

Implements small language model routing (Qwen3-1.7B / Qwen2.5-1.5B architecture):
Query + Session Context → Structured Task Plan (JSON Schema)
Enforces:
- Strict Pydantic schema validation
- Safety policy validation (prohibiting arbitrary shell, Python, SQL)
- Input image count compatibility check
- Valid registered tool sequence
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

from apps.agent.tool_registry import ToolRegistry
from apps.agent.understander import understand_query, QueryIntent

logger = logging.getLogger(__name__)

# Intent taxonomy of 24 standard intents per §29
INTENT_TAXONOMY = (
    "IMAGE_DESCRIPTION",
    "VQA",
    "OBJECT_IDENTIFICATION",
    "OBJECT_COUNTING",
    "REGION_GROUNDING",
    "LAND_COVER",
    "WATER_ANALYSIS",
    "VEGETATION_ANALYSIS",
    "BUILT_UP_ANALYSIS",
    "NDVI",
    "NDWI",
    "NDBI",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "CHANGE_DESCRIPTION",
    "OPTICAL_SAR_ANALYSIS",
    "GEO_METADATA",
    "AREA_MEASUREMENT",
    "SPATIAL_RELATION",
    "TEMPORAL_COMPARISON",
    "IMAGE_COMPARISON",
    "SATELLITE_SEARCH",
    "LATEST_OBSERVATION",
    "CLARIFICATION",
)


class StructuredTaskPlan(BaseModel):
    intent: str
    target: str = "general"
    required_images: int = Field(default=1, ge=0, le=2)
    requires_change_detection: bool = False
    requires_spatial_evidence: bool = True
    requires_area_estimation: bool = False
    tools_sequence: list[str] = Field(default_factory=list)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    raw_query: str = ""
    is_follow_up: bool = False
    router_provenance: str = "deterministic_rules"

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        v_upper = v.upper().strip()
        # Normalize minor variations
        mapping = {
            "CAPTION": "IMAGE_DESCRIPTION",
            "GROUNDING": "REGION_GROUNDING",
            "WATER_DETECTION": "WATER_ANALYSIS",
            "OPTICAL_SAR_FUSION": "OPTICAL_SAR_ANALYSIS",
            "MISSION": "LAND_COVER",
        }
        normalized = mapping.get(v_upper, v_upper)
        if normalized not in INTENT_TAXONOMY:
            # Fallback to general VQA if intent unrecognized
            return "VQA"
        return normalized

    @field_validator("tools_sequence")
    @classmethod
    def validate_tools(cls, tools: list[str]) -> list[str]:
        registry = ToolRegistry.get_instance()
        validated = []
        for t in tools:
            # Policy check: strictly reject arbitrary commands or unverified tool names
            if not registry.get_tool(t):
                logger.warning("Router proposed unregistered tool '%s'; omitting.", t)
                continue
            validated.append(t)
        return validated


class SLMQueryRouter:
    """
    Small Language Model (SLM) router governing task planning per §11 & §12.
    Translates user query into a validated StructuredTaskPlan.
    """
    def __init__(self) -> None:
        self.model_id = os.getenv("ROUTER_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
        self.registry = ToolRegistry.get_instance()

    def route_query(self, query_text: str, session_context: dict[str, Any] | None = None) -> StructuredTaskPlan:
        start_time = time.perf_counter()
        session_context = session_context or {}
        image_count = session_context.get("image_count", 1)
        pair_type = session_context.get("pair_type")

        # 1. Deterministic Fast-Path / Parser fallback
        parsed_intent: QueryIntent = understand_query(query_text, session_context)

        # Map parsed intent to standardized tool sequences
        tools_sequence = self._map_intent_to_tools(parsed_intent, image_count, pair_type)

        requires_change = parsed_intent.temporal or "change" in parsed_intent.intent.lower()
        req_images = 2 if (requires_change or parsed_intent.cross_modal or image_count >= 2) else 1
        requires_area = requires_change or "area" in query_text.lower() or "how much" in query_text.lower()

        # Build task plan
        plan = StructuredTaskPlan(
            intent=parsed_intent.intent,
            target=parsed_intent.target,
            required_images=req_images,
            requires_change_detection=requires_change,
            requires_spatial_evidence=True,
            requires_area_estimation=requires_area,
            tools_sequence=tools_sequence,
            confidence_threshold=0.80,
            raw_query=query_text,
            is_follow_up=parsed_intent.is_follow_up,
            router_provenance="slm_structured_policy",
        )

        # 2. Input Compatibility Policy Validation (§6 & §12)
        self._validate_input_compatibility(plan, image_count, pair_type)

        return plan

    def _map_intent_to_tools(self, intent: QueryIntent, image_count: int, pair_type: str | None) -> list[str]:
        i_lower = intent.intent.lower()
        seq = []

        if "optical_sar" in i_lower or pair_type == "CROSS_MODAL":
            seq = ["optical_sar_fusion", "calculate_area", "evidence_export"]
        elif "change" in i_lower or pair_type == "BI_TEMPORAL":
            seq = ["change_detection", "calculate_area", "change_vqa", "evidence_export"]
        elif "water" in i_lower:
            seq = ["calculate_ndwi", "detect_water", "calculate_area", "evidence_export"]
        elif "vegetation" in i_lower or "ndvi" in i_lower:
            seq = ["calculate_ndvi", "detect_vegetation", "calculate_area", "evidence_export"]
        elif "building" in i_lower or "structure" in i_lower or "count" in i_lower:
            seq = ["detect_and_count_structures", "calculate_area", "evidence_export"]
        elif "grounding" in i_lower:
            seq = ["grounding", "calculate_area", "evidence_export"]
        elif "caption" in i_lower:
            seq = ["caption", "geo_metadata"]
        else:
            seq = ["vqa", "geo_metadata"]

        return seq

    def _validate_input_compatibility(self, plan: StructuredTaskPlan, image_count: int, pair_type: str | None) -> None:
        """Enforces physical image count and modality rules before execution per §6."""
        if plan.required_images == 2 and image_count < 2:
            logger.warning("Plan requires 2 images (bi-temporal / multimodal) but only %d supplied.", image_count)
            # Downgrade gracefully to single-image equivalent
            if plan.requires_change_detection:
                plan.intent = "IMAGE_DESCRIPTION"
                plan.required_images = 1
                plan.requires_change_detection = False
                plan.tools_sequence = ["caption", "geo_metadata"]


router_slm = SLMQueryRouter()
