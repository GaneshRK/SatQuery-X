"""Agentic planner — tool-calling loop with rule-based fallback and Mission Mode."""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from backend.config import get_settings
from backend.planner.schemas import PlanStep
from backend.planner.understander import classify_query
from backend.registry.loader import ModelRegistry

logger = structlog.get_logger()


TOOL_SCHEMAS = [
    {
        "name": "RS_VQA",
        "description": "Visual question answering on a single satellite image.",
        "parameters": {"question": "str"},
    },
    {
        "name": "RS_CAPTION",
        "description": "Generate a descriptive caption for a satellite image.",
        "parameters": {},
    },
    {
        "name": "RS_GROUNDING",
        "description": "Locate candidate bounding box regions matching a text description or spectral category.",
        "parameters": {"text_prompt": "str"},
    },
    {
        "name": "CHANGE_DETECTION",
        "description": "Detect pixel-level changes between bi-temporal image pair and extract changed bounding boxes.",
        "parameters": {},
    },
    {
        "name": "CHANGE_VQA",
        "description": "Answer a question about detected changes between two images.",
        "parameters": {"question": "str"},
    },
    {
        "name": "OPTICAL_SAR_FUSION",
        "description": "Fused analysis of co-registered optical + SAR pair.",
        "parameters": {"question": "str"},
    },
]


class AgenticPlanner:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.settings = get_settings()

    def create_plan(
        self,
        query: str,
        detected_mode: str,
        image_count: int,
        ingestion_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[PlanStep], str]:
        task_class = classify_query(query, detected_mode, image_count)

        if self.settings.planner_llm_provider == "openai" and self.settings.openai_api_key:
            try:
                plan = self._llm_plan(query, detected_mode, image_count, ingestion_metadata or {})
                return plan, task_class
            except Exception as exc:
                logger.warning("planner_llm_failed", error=str(exc))

        return self._rules_plan(query, task_class, detected_mode, image_count), task_class

    def _rules_plan(
        self, query: str, task_class: str, detected_mode: str, image_count: int
    ) -> list[PlanStep]:
        # Mission Mode: Multi-step chained intelligence workflow
        if task_class == "mission_mode":
            steps: list[PlanStep] = []
            if image_count >= 2:
                cd = self.registry.get("CHANGE_DETECTION")
                steps.append(PlanStep(step=1, tool="CHANGE_DETECTION", version=cd.version, params={}))
                cvqa = self.registry.get("CHANGE_VQA")
                steps.append(
                    PlanStep(
                        step=2,
                        tool="CHANGE_VQA",
                        version=cvqa.version,
                        params={"question": query, "change_mask_ref": "step1.change_mask"},
                    )
                )
                grounding = self.registry.get("RS_GROUNDING")
                steps.append(
                    PlanStep(
                        step=3,
                        tool="RS_GROUNDING",
                        version=grounding.version,
                        params={"text_prompt": query},
                    )
                )
            else:
                cap = self.registry.get("RS_CAPTION")
                vqa = self.registry.get("RS_VQA")
                grounding = self.registry.get("RS_GROUNDING")
                steps.append(PlanStep(step=1, tool="RS_CAPTION", version=cap.version, params={}))
                steps.append(PlanStep(step=2, tool="RS_VQA", version=vqa.version, params={"question": query}))
                steps.append(PlanStep(step=3, tool="RS_GROUNDING", version=grounding.version, params={"text_prompt": query}))
            return steps

        # Mode 2: Cross-modal optical+SAR pair fusion
        if task_class == "fusion" or detected_mode == "cross_modal_pair":
            entry = self.registry.get("OPTICAL_SAR_FUSION")
            return [
                PlanStep(
                    step=1,
                    tool="OPTICAL_SAR_FUSION",
                    version=entry.version,
                    params={"question": query},
                )
            ]

        # Mode 3 & Mode 4: Bi-temporal change detection & change-VQA
        if task_class in {"change_detection", "change_vqa"} or detected_mode == "bi_temporal":
            steps: list[PlanStep] = []
            cd = self.registry.get("CHANGE_DETECTION")
            steps.append(PlanStep(step=1, tool="CHANGE_DETECTION", version=cd.version, params={}))
            cvqa = self.registry.get("CHANGE_VQA")
            steps.append(
                PlanStep(
                    step=2,
                    tool="CHANGE_VQA",
                    version=cvqa.version,
                    params={"question": query, "change_mask_ref": "step1.change_mask"},
                )
            )
            return steps

        # Compound VQA + Grounding
        if task_class == "compound_vqa_grounding":
            vqa = self.registry.get("RS_VQA")
            grounding = self.registry.get("RS_GROUNDING")
            return [
                PlanStep(step=1, tool="RS_VQA", version=vqa.version, params={"question": query}),
                PlanStep(step=2, tool="RS_GROUNDING", version=grounding.version, params={"text_prompt": query}),
            ]

        if task_class == "grounding":
            entry = self.registry.get("RS_GROUNDING")
            return [
                PlanStep(
                    step=1,
                    tool="RS_GROUNDING",
                    version=entry.version,
                    params={"text_prompt": query},
                )
            ]

        if task_class == "caption":
            entry = self.registry.get("RS_CAPTION")
            return [PlanStep(step=1, tool="RS_CAPTION", version=entry.version, params={})]

        # Compound: VQA + caption for descriptive compound queries
        if " and " in query.lower() and image_count == 1:
            vqa = self.registry.get("RS_VQA")
            cap = self.registry.get("RS_CAPTION")
            return [
                PlanStep(step=1, tool="RS_VQA", version=vqa.version, params={"question": query}),
                PlanStep(step=2, tool="RS_CAPTION", version=cap.version, params={}),
            ]

        # Mode 1: Single image VQA
        entry = self.registry.get("RS_VQA")
        return [
            PlanStep(step=1, tool="RS_VQA", version=entry.version, params={"question": query}),
        ]

    def _llm_plan(
        self,
        query: str,
        detected_mode: str,
        image_count: int,
        metadata: dict[str, Any],
    ) -> list[PlanStep]:
        system = (
            "You are SatQuery-X planner. Return JSON with keys task_classification and plan. "
            "plan is an ordered list of {step, tool, version, params}. "
            f"Available tools: {json.dumps(TOOL_SCHEMAS)}. "
            f"Detected mode: {detected_mode}, image_count: {image_count}. "
            "Max 5 steps. Only use compatible tools."
        )
        payload = {
            "model": self.settings.planner_model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps({"query": query, "metadata": metadata}),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return [PlanStep(**s) for s in parsed["plan"]]
