# SatQuery-X — API Contract Specification (DRF v1)

## 1. Authentication Endpoints
* `POST /api/v1/auth/token/`
  * Body: `{"username": str, "password": str}`
  * Response: `{"access": str, "refresh": str, "user": {"id": int, "username": str, "role": str}}`
* `POST /api/v1/auth/token/refresh/`
  * Body: `{"refresh": str}`
  * Response: `{"access": str}`

## 2. Session Management
* `GET /api/v1/sessions/` — List sessions filtered by tenant & user.
* `POST /api/v1/sessions/` — Create new Earth Intelligence workspace.
  * Body: `{"name": str, "description": str, "aoi_geojson": object, "mode": "AUTO"|"SATELLITE"|"IMAGE"}`
* `GET /api/v1/sessions/{id}/` — Retrieve session detail with queries and context.

## 3. Query Execution Pipeline
* `POST /api/v1/queries/`
  * Body:
    ```json
    {
      "session": "UUID",
      "text": "What is changing around Coimbatore?",
      "image_ids": [],
      "parameters": {
        "aoi": { "name": "Coimbatore Industrial Basin", "bbox": [76.90, 10.95, 77.05, 11.08] },
        "temporal_range": { "start": "2023-01-01", "end": "2024-01-01" }
      }
    }
    ```
  * Response: Returns `201 Created` with immediate query ID and execution status.
* `GET /api/v1/queries/{id}/`
  * Response contains:
    * `status`: `"COMPLETED"` | `"FAILED"` | `"NEEDS_CLARIFICATION"`
    * `detected_task`: `"CHANGE_DETECTION"` | `"CHANGE_VQA"` | `"GROUNDING"`
    * `answer`: Calibrated scientific narrative
    * `confidence`: Decimal score (e.g. 0.89)
    * `evidence_graph`: Directed graph of scenes, measurements, vectors, and citations
    * `structured_plan`: Execution steps, tool latencies, and contextual UI actions
    * `follow_up_questions`: Contextually relevant suggestions

## 4. Evidence & Export Endpoints
* `GET /api/v1/evidence/regions/?query={query_id}` — GeoJSON FeatureCollection of detected polygons.
* `GET /api/v1/evidence/external/?query={query_id}` — Corroborating citations.
* `POST /api/v1/reports/` — Export PDF / GeoJSON / CSV executive reports.
