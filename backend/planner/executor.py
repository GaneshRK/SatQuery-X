"""Deterministic plan executor with complete evidence and trace tracking."""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from backend.evidence.engine import EvidenceEngine
from backend.planner.schemas import EvidenceOutput, ExecutionTrace, PlanStep
from backend.planner.validator import PlanValidationError, validate_plan
from backend.registry.contracts import ModelInput, ModelStatus
from backend.registry.loader import ModelRegistry

logger = structlog.get_logger()


class PlanExecutor:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.evidence = EvidenceEngine()

    def execute(
        self,
        query: str,
        plan: list[PlanStep],
        task_classification: str,
        detected_mode: str,
        image_bytes: list[bytes],
        image_metadata: list[dict[str, Any]],
        session_id: uuid.UUID,
        query_id: uuid.UUID,
    ) -> ExecutionTrace:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        step_outputs: dict[str, Any] = {}
        errors: list[str] = []

        try:
            validate_plan(plan, detected_mode, len(image_bytes), self.registry)
        except PlanValidationError as exc:
            return ExecutionTrace(
                query=query,
                detected_mode=detected_mode,
                task_classification=task_classification,
                plan=plan,
                outputs={},
                answer=f"Plan validation failed: {exc}",
                confidence=0.0,
                evidence=EvidenceOutput(),
                timings_ms={"total": round((time.perf_counter() - t0) * 1000, 2)},
                errors=[str(exc)],
            )

        answers: list[str] = []
        confidences: list[float] = []
        all_boxes: list[dict] = []
        geojson_items: list[dict] = []
        artifact_keys: dict[str, str] = {}
        quantified_km2: float | None = None
        quantified_ha: float | None = None
        change_pct: float | None = None

        for step in plan:
            step_start = time.perf_counter()
            payload = ModelInput(
                model_id=step.tool,
                image_bytes=image_bytes,
                question=step.params.get("question", query),
                text_prompt=step.params.get("text_prompt", query),
                params=step.params,
                context={"image_metadata": image_metadata},
            )

            if step.tool == "CHANGE_VQA" and "step1" in str(step.params.get("change_mask_ref", "")):
                prev = step_outputs.get("step1")
                if prev and prev.change_mask_bytes:
                    payload.change_mask = prev.change_mask_bytes

            try:
                output = self.registry.invoke(step.tool, payload)
            except Exception as exc:
                logger.exception("model_invoke_failed", tool=step.tool)
                errors.append(f"{step.tool}: {exc}")
                timings[f"step{step.step}"] = round((time.perf_counter() - step_start) * 1000, 2)
                continue

            step_outputs[f"step{step.step}"] = output
            timings[f"step{step.step}"] = round(output.latency_ms or ((time.perf_counter() - step_start) * 1000), 2)

            if output.status == ModelStatus.NOT_IMPLEMENTED:
                errors.append(output.error or f"{step.tool} not implemented")
                continue
            if output.error:
                errors.append(output.error)

            if output.answer:
                answers.append(output.answer)
            elif output.caption:
                answers.append(output.caption)

            if output.confidence > 0:
                confidences.append(output.confidence)

            ev = self.evidence.process_output(
                output=output,
                image_metadata=image_metadata,
                session_id=session_id,
                query_id=query_id,
                step=step.step,
            )
            all_boxes.extend(ev.get("bboxes", []))
            geojson_items.extend(ev.get("geojson", []))
            artifact_keys.update(ev.get("artifact_keys", {}))
            if ev.get("quantified_area_km2") is not None:
                quantified_km2 = ev.get("quantified_area_km2")
                quantified_ha = ev.get("quantified_area_hectares")
                change_pct = ev.get("change_percentage")

        final_answer = answers[-1] if answers else "No answer produced."
        if len(answers) > 1:
            # Combine sequential/compound answers cleanly
            final_answer = " | ".join(answers)

        confidence = self.evidence.aggregate_confidence(confidences, strategy="min")
        timings["total"] = round((time.perf_counter() - t0) * 1000, 2)

        # Before/after preview urls
        before_after = [
            f"/api/v1/sessions/{session_id}/images/{m.get('image_id')}/preview"
            for m in image_metadata
            if m.get("image_id")
        ]

        evidence = EvidenceOutput(
            change_mask_url=artifact_keys.get("change_mask"),
            overlay_url=artifact_keys.get("overlay"),
            bboxes=all_boxes,
            geojson=geojson_items,
            before_after_thumbnails=before_after,
            quantified_area_km2=quantified_km2,
            quantified_area_hectares=quantified_ha,
            change_percentage=change_pct,
        )

        return ExecutionTrace(
            query=query,
            detected_mode=detected_mode,
            task_classification=task_classification,
            plan=plan,
            outputs={k: self._serialize_output(v) for k, v in step_outputs.items()},
            answer=final_answer,
            confidence=confidence,
            evidence=evidence,
            timings_ms=timings,
            errors=errors,
        )

    def _serialize_output(self, output: Any) -> dict[str, Any]:
        return {
            "model_id": output.model_id,
            "version": output.version,
            "answer": output.answer,
            "caption": output.caption,
            "confidence": round(output.confidence, 3),
            "status": output.status.value if hasattr(output.status, "value") else str(output.status),
            "boxes": [
                {
                    "x1": b.x1,
                    "y1": b.y1,
                    "x2": b.x2,
                    "y2": b.y2,
                    "label": b.label,
                    "confidence": round(b.confidence, 3),
                }
                for b in output.boxes
            ],
            "raw": output.raw,
            "latency_ms": round(output.latency_ms, 2),
        }
