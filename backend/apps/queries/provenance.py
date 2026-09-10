"""Tamper-evident provenance ledger for SatQuery-X execution records."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import ExecutionStep, ProvenanceRecord, Query


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash_record(prev_hash: str | None, payload: dict[str, Any]) -> str:
    body = {"prev_hash": prev_hash, "payload": payload}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _safe_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Remove obvious secret fields before persisting audit metadata."""
    if not isinstance(parameters, dict):
        return {}
    secret_words = ("token", "secret", "password", "authorization", "api_key", "access_key")
    result: dict[str, Any] = {}
    for key, value in parameters.items():
        if any(word in str(key).lower() for word in secret_words):
            result[str(key)] = "[REDACTED]"
        else:
            result[str(key)] = value
    return result


def build_provenance_ledger(query: Query) -> dict[str, Any]:
    """Create an ordered, hash-chained audit ledger from persisted execution facts."""
    with transaction.atomic():
        ProvenanceRecord.objects.filter(query=query).delete()
        prev_hash: str | None = None
        count = 0

        def append(kind: str, step: ExecutionStep | None, payload: dict[str, Any]) -> None:
            nonlocal prev_hash, count
            clean = json.loads(_canonical(payload))
            record_hash = _hash_record(prev_hash, clean)
            row = ProvenanceRecord.objects.create(
                query=query,
                execution_step=step,
                sequence=count + 1,
                event_type=kind,
                payload=clean,
                previous_hash=prev_hash or "",
                record_hash=record_hash,
                created_at=timezone.now(),
            )
            prev_hash = row.record_hash
            count += 1

        append("query_created", None, {
            "query_id": str(query.id),
            "text_sha256": hashlib.sha256((query.text or "").encode("utf-8")).hexdigest(),
            "detected_task": query.detected_task,
            "mode": getattr(query, "mode", None),
        })

        for step in query.execution_steps.order_by("step_number"):
            append("execution_step", step, {
                "step_id": str(step.id),
                "step_number": step.step_number,
                "tool_name": step.tool_name,
                "agent_type": step.agent_type,
                "model_version": step.model_version,
                "status": step.status,
                "parameters": _safe_parameters(step.parameters),
                "input_refs": step.input_refs,
                "output_ref": step.output_ref,
                "evidence_refs": step.evidence_refs,
                "latency_ms": step.latency_ms,
                "retry_count": step.retry_count,
                "error": step.error,
            })

        append("final_evidence", None, {
            "evidence_graph_sha256": hashlib.sha256(_canonical(query.evidence_graph or {}).encode("utf-8")).hexdigest(),
            "evidence_bundle_sha256": hashlib.sha256(_canonical(query.evidence_bundle or {}).encode("utf-8")).hexdigest(),
            "answer_trace": query.answer_trace or {},
        })

        append("final_answer", None, {
            "answer_sha256": hashlib.sha256((query.answer or "").encode("utf-8")).hexdigest(),
            "status": query.status,
            "confidence": query.confidence,
        })

    return verify_provenance_ledger(query)


def verify_provenance_ledger(query: Query) -> dict[str, Any]:
    records = list(query.provenance_records.order_by("sequence"))
    prev = ""
    failures: list[str] = []
    for expected_sequence, record in enumerate(records, start=1):
        if record.sequence != expected_sequence:
            failures.append(f"sequence_gap:{expected_sequence}")
        if record.previous_hash != prev:
            failures.append(f"previous_hash_mismatch:{record.sequence}")
        expected_hash = _hash_record(record.previous_hash or None, record.payload)
        if record.record_hash != expected_hash:
            failures.append(f"record_hash_mismatch:{record.sequence}")
        prev = record.record_hash
    return {
        "valid": not failures and bool(records),
        "record_count": len(records),
        "head_hash": prev or None,
        "failures": failures,
    }
