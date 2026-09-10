# Stage 14 — Agentic Runtime Model Routing

Stage 14 adds a runtime modality router between preprocessing and specialist execution.

## Routes

- `SINGLE_IMAGE` → single-image specialist path.
- `BI_TEMPORAL_SAME_MODALITY` → change detection + Change VQA.
- `CROSS_MODAL_OPTICAL_SAR` → Optical/SAR fusion.
- `BI_TEMPORAL_OPTICAL_SAR` → explicitly identified when two optical and two SAR observations are present.

## Guardrails

The router uses explicit `modality` metadata first, then conservative sensor/platform metadata. It never assumes that list position means optical or SAR. Unknown modality remains unknown.

The four-observation temporal optical/SAR route is surfaced as a composed route; Stage 14 does not falsely claim that an existing two-image model can consume four observations. A future native four-stream model can consume this route without changing the evidence contract.
