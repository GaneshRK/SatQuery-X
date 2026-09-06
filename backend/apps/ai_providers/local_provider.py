from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .base import AIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)


class LocalProvider(AIProvider):
    """
    Local safety/fallback provider.

    This provider intentionally does NOT fabricate satellite observations.

    It can:
    - validate requests
    - summarize supplied structured evidence
    - produce evidence-grounded text from already computed outputs
    - explain missing inputs

    It does NOT:
    - invent NDVI
    - invent coordinates
    - invent change percentages
    - invent sensor/date information
    - pretend that an image was scientifically analyzed when no model ran
    """

    name = "Local Evidence Provider"

    def is_configured(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Capability handling
    # ------------------------------------------------------------------

    def supports_task(self, task: str) -> bool:
        return task.upper() in {
            "REASONING",
            "PLANNING",
            "EXPLANATION",
            "VQA",
            "CAPTION",
            "GROUNDING",
            "SEGMENTATION",
            "CHANGE_DETECTION",
            "CHANGE_VQA",
            "OPTICAL_SAR_FUSION",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _existing_images(paths: list[str]) -> list[str]:
        result: list[str] = []

        for path in paths:
            try:
                if Path(path).is_file():
                    result.append(path)
            except (OSError, TypeError):
                continue

        return result

    @staticmethod
    def _compact_value(value: Any) -> str:
        if value is None:
            return "unknown"

        if isinstance(value, (str, int, float, bool)):
            return str(value)

        if isinstance(value, list):
            return ", ".join(
                LocalProvider._compact_value(item)
                for item in value[:10]
            )

        if isinstance(value, dict):
            parts = []

            for key, item in list(value.items())[:10]:
                parts.append(
                    f"{key}={LocalProvider._compact_value(item)}"
                )

            return "; ".join(parts)

        return str(value)

    @classmethod
    def _summarize_evidence(
        cls,
        evidence: dict[str, Any],
    ) -> list[str]:
        """
        Convert supplied evidence into short factual statements.

        The method only reports fields already present in evidence.
        """

        statements: list[str] = []

        if not isinstance(evidence, dict):
            return statements

        # Explicit textual finding.
        for key in (
            "finding",
            "conclusion",
            "summary",
            "result",
            "answer",
        ):
            value = evidence.get(key)

            if isinstance(value, str) and value.strip():
                statements.append(value.strip())

        # Measurements.
        measurements = evidence.get("measurements")

        if isinstance(measurements, dict):
            for key, value in measurements.items():
                if value is None:
                    continue

                statements.append(
                    f"{key}: {cls._compact_value(value)}"
                )

        # Geometry.
        geometry = evidence.get("geometry")

        if geometry:
            statements.append(
                f"geometry: {cls._compact_value(geometry)}"
            )

        # Observation metadata.
        metadata = evidence.get("metadata")

        if isinstance(metadata, dict):
            allowed_keys = (
                "acquisition_date",
                "start_date",
                "end_date",
                "sensor",
                "platform",
                "crs",
                "resolution",
            )

            for key in allowed_keys:
                value = metadata.get(key)

                if value is not None:
                    statements.append(
                        f"{key}: {cls._compact_value(value)}"
                    )

        return statements[:30]

    @staticmethod
    def _build_trace(
        task: str,
        *,
        used_evidence: bool,
        used_images: bool,
    ) -> list[dict[str, Any]]:
        return [
            {
                "step": "provider_execution",
                "task": task,
                "provider": "local",
            },
            {
                "step": "input_check",
                "images_available": used_images,
                "structured_evidence_available": used_evidence,
            },
        ]

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, request: AIRequest) -> AIResponse:
        started = time.perf_counter()

        errors = request.validate()

        if errors:
            return AIResponse.failed(
                provider="local",
                model_name="evidence-fallback",
                error="; ".join(errors),
            )

        task = request.normalized_task()

        existing_images = self._existing_images(request.image_paths)

        evidence = request.evidence or {}

        evidence_statements = self._summarize_evidence(evidence)

        trace = self._build_trace(
            task,
            used_evidence=bool(evidence_statements),
            used_images=bool(existing_images),
        )

        # --------------------------------------------------------------
        # Best case: actual upstream evidence exists.
        # --------------------------------------------------------------

        if evidence_statements:
            text = " ".join(evidence_statements)

            latency = int(
                (time.perf_counter() - started) * 1000
            )

            return AIResponse(
                provider="local",
                model_name="evidence-fallback",
                text=text,
                structured_data={
                    "task": task,
                    "evidence_summary": evidence_statements,
                },
                confidence=None,
                latency_ms=latency,
                status="ok",
                evidence_refs=evidence.get("evidence_refs", [])
                if isinstance(evidence, dict)
                else [],
                limitations=evidence.get("limitations", [])
                if isinstance(evidence, dict)
                else [],
                trace=trace,
                metadata={
                    "mode": "evidence_grounded_fallback",
                },
            )

        # --------------------------------------------------------------
        # No evidence.
        #
        # Even if an image path exists, this provider refuses to claim
        # scientific image interpretation.
        # --------------------------------------------------------------

        reason = (
            "No verified analysis evidence is available for this request. "
            "The local fallback provider will not infer scientific findings "
            "from an image without a suitable analysis model or measurement "
            "pipeline."
        )

        latency = int(
            (time.perf_counter() - started) * 1000
        )

        return AIResponse.insufficient_evidence(
            provider="local",
            model_name="evidence-fallback",
            reason=reason,
            latency_ms=latency,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": "local",
            "status": "healthy",
            "healthy": True,
            "mode": "evidence_fallback",
            "available_tasks": self.capabilities(),
        }