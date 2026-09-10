"""End-to-end pipeline validation and execution contract.

This module validates that an agent run has enough real evidence to proceed
through retrieval -> acquisition -> routing -> geospatial preparation ->
model inference -> evidence/provenance. It is intentionally side-effect free:
it does not download imagery or fabricate missing metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.agent.modality_router import resolve_analysis_route


@dataclass(frozen=True)
class PipelineStageResult:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class PipelineValidationError(ValueError):
    """Raised when a pipeline contract cannot be satisfied."""

    def __init__(self, stage: str, code: str, message: str, details: dict[str, Any] | None = None):
        self.stage = stage
        self.code = code
        self.details = details or {}
        super().__init__(message)


def _require(condition: bool, stage: str, code: str, message: str, details=None):
    if not condition:
        raise PipelineValidationError(stage, code, message, details)


def validate_pipeline_contract(
    *,
    records: list[dict[str, Any]],
    paths: list[str],
    requested_relationship: str = "",
    question: str = "",
    coregistration_result: dict[str, Any] | None = None,
    model_result: dict[str, Any] | None = None,
    evidence_result: dict[str, Any] | None = None,
    provenance_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a completed or preflighted run without doing inference."""
    stages: list[PipelineStageResult] = []

    _require(records, "retrieval", "NO_OBSERVATIONS", "No satellite observations were supplied.")
    _require(len(records) == len(paths), "acquisition", "ASSET_METADATA_MISMATCH", "Each image path must have one metadata record.")
    stages.append(PipelineStageResult("retrieval", "passed", "Observation metadata is present.", {"count": len(records)}))

    for i, path in enumerate(paths):
        _require(path, "acquisition", "EMPTY_ASSET_PATH", f"Observation {i} has an empty asset path.")
    stages.append(PipelineStageResult("acquisition", "passed", "Asset references are present.", {"count": len(paths)}))

    route = resolve_analysis_route(records, requested_relationship)
    _require(route["status"] != "needs_resolution", "routing", "ROUTE_UNRESOLVED", "The requested analysis route cannot be resolved from supplied metadata.", route)
    stages.append(PipelineStageResult("routing", "passed", "Analysis route resolved from metadata.", route))

    if route["route"] == "BI_TEMPORAL_OPTICAL_SAR":
        _require(coregistration_result is not None, "geospatial", "COREGISTRATION_MISSING", "Four-stream temporal Optical/SAR analysis requires coregistration output.")
        _require(coregistration_result.get("status") == "completed", "geospatial", "COREGISTRATION_FAILED", "Temporal Optical/SAR coregistration did not complete.", coregistration_result)
        _require(coregistration_result.get("stream_order") == ["optical_t1", "sar_t1", "optical_t2", "sar_t2"], "geospatial", "STREAM_ORDER_INVALID", "Coregistration did not produce the required four-stream order.", coregistration_result)
        stages.append(PipelineStageResult("geospatial", "passed", "Temporal pairing and coregistration completed.", {"pairs": len(coregistration_result.get("pairs", []))}))
    else:
        stages.append(PipelineStageResult("geospatial", "not_required", "No four-stream temporal coregistration is required for this route."))

    if model_result is not None:
        _require(model_result.get("status", "ok") not in {"error", "failed"}, "inference", "MODEL_FAILED", "Model inference reported failure.", model_result)
        _require(model_result.get("answer") not in (None, ""), "inference", "EMPTY_MODEL_ANSWER", "Model inference completed without an answer.", model_result)
        stages.append(PipelineStageResult("inference", "passed", "Model returned an answer.", {"status": model_result.get("status")}))
    else:
        stages.append(PipelineStageResult("inference", "pending", "Inference has not been executed yet."))

    if evidence_result is not None:
        _require(bool(evidence_result.get("evidence") or evidence_result.get("provenance") or evidence_result.get("status")), "evidence", "EVIDENCE_EMPTY", "Evidence stage returned no structured result.", evidence_result)
        stages.append(PipelineStageResult("evidence", "passed", "Structured evidence result is present."))
    else:
        stages.append(PipelineStageResult("evidence", "pending", "Evidence assembly has not been executed yet."))

    if provenance_result is not None:
        _require(provenance_result.get("valid", provenance_result.get("status") in {"valid", "verified"}), "provenance", "PROVENANCE_INVALID", "Provenance verification failed.", provenance_result)
        stages.append(PipelineStageResult("provenance", "passed", "Provenance verification is valid."))
    else:
        stages.append(PipelineStageResult("provenance", "pending", "Provenance verification has not been executed yet."))

    return {
        "status": "passed" if all(s.status in {"passed", "not_required"} for s in stages) else "pending",
        "route": route,
        "question_present": bool(str(question).strip()),
        "stages": [s.__dict__ for s in stages],
        "failure_policy": "Stop at the first unmet scientific contract; never synthesize missing evidence.",
    }


def format_pipeline_failure(exc: PipelineValidationError) -> dict[str, Any]:
    return {"status": "failed", "stage": exc.stage, "code": exc.code, "message": str(exc), "details": exc.details}
