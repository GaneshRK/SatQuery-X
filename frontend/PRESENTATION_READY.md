# SatQuery-X — Presentation Ready Frontend

## Backend-first result lifecycle

The assistant never treats HTTP 202 as a completed analysis.

`POST /api/analysis/query/` → receive `analysis_id` → poll `GET /api/analysis/{id}/` → wait for `COMPLETED` or `FAILED` → render the persisted backend result.

During `PENDING`/`RUNNING`, the UI displays an explicit processing state.

## Map

The main map uses a realistic satellite basemap and supports zoom, pan, AOI bounds, coordinate display, result overlays, vector evidence and labels. It does not silently move to a hardcoded city when the backend has not returned a location.

## Scientific integrity

No fabricated 94% confidence, 18.4 km² area, changed-pixel count or dates are inserted into the live result. Missing backend measurements display as unavailable.

## Presentation flow

Upload image → ask question → backend processing indicator → final answer → map coordinates/evidence → follow-up analysis → two-image comparison when two observations are supplied.
