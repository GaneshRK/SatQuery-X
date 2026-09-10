# Stage 18 — Provider Boundary & End-to-End Integration Validation

Stage 18 adds a dependency-injected integration runner and a structured satellite-provider boundary.

## Purpose

The production workflow can now be tested end-to-end without replacing the real provider implementation. Tests inject an explicit provider double at the external boundary. A provider failure is surfaced as a structured failure and never silently replaced with synthetic imagery.

## Pipeline

`provider search -> acquisition -> routing -> temporal coregistration -> model -> evidence -> provenance -> contract validation`

## Guarantees

- Provider/network/authentication errors are classified.
- Test doubles are explicitly marked in results.
- No automatic mock fallback exists in `get_satellite_provider()`.
- Missing evidence stops the pipeline.
- Four-stream temporal Optical/SAR analysis requires successful coregistration.
- Integration tests may use tiny synthetic raster fixtures only as software-test inputs; they are not scientific satellite data and must never become benchmark results.
