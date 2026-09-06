"""Qwen SLM Query Router & Task Planner Adapter per §7, §8, §34, §37.

Provides Small Language Model (SLM) planning and intent classification (Qwen3-1.7B / Qwen2.5-1.5B class):
Query + Image Context → Structured Plan (JSON) → Validator → Tool Registry
"""

from __future__ import annotations

import os
import time
from typing import Any

from apps.agent.router_slm import router_slm, StructuredTaskPlan
from apps.models_ai.manager import model_manager
from .base import SLMPlannerAdapter as BaseSLMPlannerAdapter


class QwenSLMAdapter(BaseSLMPlannerAdapter):
    """
    Specialist adapter for Small Language Model intent classification and query planning.
    Decides 'What does the user want?' without touching heavy pixel analysis models.
    """
    model_id = "Qwen-SLM"
    version = "2.1-router"
    task = "query_planning_and_intent_routing"
    gpu_requirement = "OPTIONAL"

    def __init__(self) -> None:
        super().__init__()
        self.model_name = os.getenv("SLM_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
        self._router = router_slm

    def plan_query(self, query_text: str, session_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Translates user query into a validated, structured task plan."""
        start_t = time.perf_counter()
        structured_plan: StructuredTaskPlan = self._router.route_query(query_text, session_context)
        latency = int((time.perf_counter() - start_t) * 1000)

        return {
            "intent": structured_plan.intent,
            "target": structured_plan.target,
            "required_images": structured_plan.required_images,
            "requires_change_detection": structured_plan.requires_change_detection,
            "requires_spatial_evidence": structured_plan.requires_spatial_evidence,
            "requires_area_estimation": structured_plan.requires_area_estimation,
            "tools_sequence": structured_plan.tools_sequence,
            "confidence_threshold": structured_plan.confidence_threshold,
            "model_architecture": self.model_name,
            "latency_ms": latency,
            "status": "ok",
        }
