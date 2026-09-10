# Stage 10 — Tamper-Evident Evidence & Provenance Ledger

SatQuery-X now persists a hash-chained provenance ledger for completed query executions.

## What is recorded

- query identity and task metadata
- execution step identity, tool, agent type, model version and status
- sanitized execution parameters
- input/output/evidence references
- latency and retry count
- hashes of the final evidence graph/bundle
- hash of the final answer

Secrets are not persisted in the ledger. The ledger does not contain hidden chain-of-thought.

## Integrity

Each record contains:

- `previous_hash`
- canonical JSON payload
- `record_hash = SHA-256(previous_hash + payload)`

The verifier walks the complete chain and detects sequence gaps, broken links, or modified payloads.

## API

`GET /api/v1/sessions/<session_id>/queries/<query_id>/provenance/`

Returns the ordered records and verification status. Access is restricted to the query owner.

## Scientific boundary

A valid provenance chain proves that the recorded execution metadata is internally consistent; it does **not** prove that a model prediction is scientifically correct. Model correctness still comes from held-out evaluation and validated source data.
