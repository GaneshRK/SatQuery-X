# SatQuery-X API Specification (REST & OpenAPI Reference)

**Base URL**: `/api/v1`  
**Protocol**: HTTP/1.1 & HTTP/2 (Django REST Framework ASGI/WSGI)  
**Authentication**: Bearer JWT (`/api/v1/auth/login/`)

---

## Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health/` | Service liveness, readiness, and component diagnostics |
| `POST` | `/api/v1/auth/login/` | Obtain role-based JWT access and refresh tokens |
| `POST` | `/api/v1/sessions/` | Create a new analysis session |
| `GET` | `/api/v1/sessions/` | List user sessions and workspaces |
| `GET` | `/api/v1/sessions/{id}/` | Retrieve session details and list of ingested rasters |
| `POST` | `/api/v1/sessions/{id}/images/` | Upload 1 or 2 satellite rasters (GeoTIFF/PNG) |
| `GET` | `/api/v1/sessions/{id}/images/{img_id}/preview/` | Get rendered web PNG thumbnail of raster |
| `GET` | `/api/v1/sessions/{id}/images/{img_id}/` | Get metadata, CRS, resolution, and affine transform |
| `POST` | `/api/v1/sessions/{id}/queries/` | Submit natural-language query to Agentic Planner & Executor |
| `GET` | `/api/v1/sessions/{id}/queries/{q_id}/` | Retrieve execution trace and evidence for query |
| `GET` | `/api/v1/sessions/{id}/queries/{q_id}/stream/` | Server-Sent Events (SSE) stream of execution progress |
| `POST` | `/api/v1/sessions/{id}/reports/` | Generate auditable HTML/PDF intelligence report |
| `GET` | `/api/v1/reports/{id}/` | View or download HTML/PDF intelligence report |
| `GET` | `/api/v1/models/` | List all registered specialist models and health status |
| `GET` | `/api/v1/models/{model_id}/` | Get specialist model specification and contracts |

---

## Request & Response Payloads

### 1. Ingest Images (`POST /v1/sessions/{id}/images`)
**Form Data**: `files`: `[file_1.tif, file_2.tif]`  
**Response (201 Created)**:
```json
{
  "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "images": [
    {
      "image_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "filename": "cartosat_ahmedabad.tif",
      "content_type": "image/tiff",
      "width": 1024,
      "height": 1024,
      "band_count": 3,
      "geo_referenced": true,
      "crs": "EPSG:32643",
      "bounds_wgs84": {
        "west": 72.50,
        "south": 23.00,
        "east": 72.60,
        "north": 23.10
      },
      "affine": [2.5, 0.0, 500000.0, 0.0, -2.5, 3000000.0],
      "sensor_type": "optical",
      "preview_url": "/api/v1/sessions/3fa85f64-5717-4562-b3fc-2c963f66afa6/images/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/preview"
    }
  ],
  "detected_mode": "single_image",
  "co_registration_valid": true,
  "validation_message": "Successfully ingested 1 image(s). Mode: single_image."
}
```

### 2. Submit Query (`POST /v1/sessions/{id}/query`)
**Request Body**:
```json
{
  "text": "Has built-up area increased significantly between these two dates?",
  "sync": true
}
```
**Response (200 OK)**:
```json
{
  "query_id": "d3b07384-d113-46fb-a09c-e3621fc57c91",
  "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "query": "Has built-up area increased significantly between these two dates?",
  "detected_mode": "bi_temporal",
  "task_classification": "change_vqa",
  "status": "completed",
  "plan": [
    { "step": 1, "tool": "CHANGE_DETECTION", "version": "v0.1-baseline", "params": {} },
    { "step": 2, "tool": "CHANGE_VQA", "version": "v0.1-baseline", "params": { "question": "Has built-up area increased significantly between these two dates?", "change_mask_ref": "step1.change_mask" } }
  ],
  "outputs": {
    "step1": { "model_id": "CHANGE_DETECTION", "answer": "Detected change covering approximately 18.4% of the image area.", "confidence": 0.85 },
    "step2": { "model_id": "CHANGE_VQA", "answer": "Yes — built-up or surface change increased, covering ~18.4% of the area across 6 detected regions.", "confidence": 0.91 }
  },
  "answer": "Yes — built-up or surface change increased, covering ~18.4% of the area across 6 detected regions.",
  "confidence": 0.85,
  "evidence": {
    "change_mask_url": "/api/v1/storage/sessions/3fa85f64.../step1_change_mask.png",
    "overlay_url": "/api/v1/storage/sessions/3fa85f64.../step1_overlay.png",
    "bboxes": [
      { "x1": 80.0, "y1": 60.0, "x2": 220.0, "y2": 240.0, "label": "change", "confidence": 0.75 }
    ],
    "geojson": [
      {
        "type": "Feature",
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[72.52, 23.02], [72.58, 23.02], [72.58, 23.08], [72.52, 23.08], [72.52, 23.02]]]
        },
        "properties": { "label": "change", "confidence": 0.75, "step": 1 }
      }
    ],
    "quantified_area_km2": 4.25,
    "quantified_area_hectares": 425.0,
    "change_percentage": 18.4
  },
  "timings_ms": {
    "step1": 12.5,
    "step2": 7.8,
    "total": 22.3
  },
  "errors": [],
  "created_at": "2026-08-30T10:00:00Z",
  "completed_at": "2026-08-30T10:00:01Z"
}
```
