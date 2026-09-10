"""Dependency-injected end-to-end orchestration contract.

This runner is intentionally small: production adapters can inject the real
provider/acquisition/model/evidence/provenance functions, while integration
tests inject a provider double at the external boundary. A provider failure
stops the pipeline; no synthetic imagery is substituted automatically.
"""
from __future__ import annotations

from typing import Any, Callable

from apps.agent.pipeline_validation import PipelineValidationError, validate_pipeline_contract
from apps.satellite.providers.boundary import SatelliteProviderBoundary


def run_integrated_pipeline(
    *,
    provider: Any,
    search_kwargs: dict[str, Any],
    acquire: Callable[[list[Any]], dict[str, Any]],
    route: Callable[[list[dict[str, Any]], str], dict[str, Any]],
    prepare: Callable[[list[dict[str, Any]], list[str]], dict[str, Any]] | None,
    infer: Callable[[dict[str, Any]], dict[str, Any]],
    build_evidence: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    verify_provenance: Callable[[dict[str, Any]], dict[str, Any]],
    requested_relationship: str = "",
    test_double: bool = False,
) -> dict[str, Any]:
    """Run all boundaries and return an auditable integration result."""
    boundary = SatelliteProviderBoundary(provider, test_double=test_double)
    search_result = boundary.call("search_scenes", provider.search_scenes, **search_kwargs)
    if search_result.status != "success":
        return {"status": "failed", "failed_stage": "retrieval", "provider": search_result.to_dict()}

    candidates = search_result.data or []
    acquisition = acquire(candidates)
    if acquisition.get("status") in {"failed", "error"}:
        return {"status": "failed", "failed_stage": "acquisition", "acquisition": acquisition}

    records = acquisition.get("records") or []
    paths = acquisition.get("paths") or []
    routing = route(records, requested_relationship)
    if routing.get("status") == "needs_resolution":
        return {"status": "failed", "failed_stage": "routing", "routing": routing}

    coregistration = None
    if routing.get("route") == "BI_TEMPORAL_OPTICAL_SAR":
        if prepare is None:
            return {"status": "failed", "failed_stage": "geospatial", "code": "PREPARATION_UNAVAILABLE"}
        try:
            coregistration = prepare(records, paths)
        except Exception as exc:
            return {"status": "failed", "failed_stage": "geospatial", "code": "COREGISTRATION_FAILED", "message": str(exc)}
        if coregistration.get("status") != "completed":
            return {"status": "failed", "failed_stage": "geospatial", "coregistration": coregistration}

    model_input = {
        "records": records,
        "paths": (coregistration or {}).get("ordered_paths", paths),
        "routing": routing,
        "coregistration": coregistration,
    }
    model_result = infer(model_input)
    if model_result.get("status") in {"failed", "error"} or not model_result.get("answer"):
        return {"status": "failed", "failed_stage": "inference", "model": model_result}

    evidence_result = build_evidence(model_result, model_input)
    provenance_result = verify_provenance(evidence_result)
    validation = validate_pipeline_contract(
        records=records,
        paths=model_input["paths"],
        requested_relationship=requested_relationship,
        coregistration_result=coregistration,
        model_result=model_result,
        evidence_result=evidence_result,
        provenance_result=provenance_result,
    )
    return {
        "status": validation["status"],
        "validation": validation,
        "routing": routing,
        "coregistration": coregistration,
        "model": model_result,
        "evidence": evidence_result,
        "provenance": provenance_result,
        "provider": search_result.to_dict(),
        "test_double": bool(test_double),
    }
