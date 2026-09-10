# Stage 17 — End-to-End Pipeline Validation

Stage 17 adds a side-effect-free execution contract for the complete SatQuery-X
path: real retrieval/acquisition -> modality routing -> geospatial preparation
-> model inference -> evidence -> provenance.

## Why

Earlier stages implemented each component independently. This stage makes the
boundaries explicit and fail-closed so a successful downstream result cannot be
claimed when a required upstream scientific contract is missing.

## Contract

- Observation metadata must match the number of asset paths.
- Routing must be resolvable from actual modality metadata.
- Four-stream temporal Optical/SAR analysis requires completed temporal
  coregistration with the exact stream order:
  `optical_t1, sar_t1, optical_t2, sar_t2`.
- Model results must contain a non-empty answer and no failure status.
- Evidence and provenance remain explicit stages; pending stages are not treated
  as successful.
- Failure codes identify the first unmet contract and stop progression.

The validation module performs no downloads, inference, geospatial fabrication,
or benchmark scoring. Its tests use tiny temporary GeoTIFFs only to validate
software contracts; these are test fixtures, not satellite data or evaluation
results.
