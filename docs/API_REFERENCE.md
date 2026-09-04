# SatQuery-X API Reference

Base Endpoint: `/api/v1/`

All protected endpoints require an `Authorization: Bearer <jwt_access_token>` header, obtained via `/api/v1/auth/token/`.

---

## Endpoints Table

| Category | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/v1/auth/token/` | Obtain JWT access and refresh token pair |
| | `POST` | `/api/v1/auth/token/refresh/` | Refresh expired access token |
| **System** | `GET` | `/api/v1/health/` | Subsystem observability (Django, DB, PostGIS, Redis, CDSE, AI) |
| | `GET` | `/api/v1/satellite/sync-status/` | Near-real-time catalogue sync watermark and provider status |
| **Sessions** | `GET` | `/api/v1/sessions/` | List user sessions with associated project and metadata |
| | `POST` | `/api/v1/sessions/` | Create a new intelligence session |
| **Imagery** | `GET` | `/api/v1/sessions/{id}/images/` | List georeferenced raster image assets for session |
| | `POST` | `/api/v1/sessions/{id}/images/` | Upload and ingest raw GeoTIFF / satellite raster |
| | `GET` | `/api/v1/imagery/{id}/tiles/{z}/{x}/{y}/` | Dynamic XYZ tile stream (`?layer=rgb,ndvi,ndwi,ndbi`) |
| | `POST` | `/api/v1/sessions/{id}/images/{id}/clip_aoi/` | Clip raster by user-drawn AOI geometry |
| **Satellite** | `POST` | `/api/v1/satellite/search/` | Search CDSE STAC v1 catalogue for Sentinel-1 & 2 scenes |
| | `GET` | `/api/v1/satellite/search/{id}/candidates/` | List candidate scenes with cloud cover, dates, and footprints |
| | `POST` | `/api/v1/satellite/search/{id}/select/` | Ingest candidate scene via background Celery pipeline |
| | `GET` | `/api/v1/satellite/aoi/` | List user Areas of Interest (AOIs) |
| | `POST` | `/api/v1/satellite/aoi/` | Create a new AOI with GeoJSON boundary |
| | `GET` | `/api/v1/satellite/aoi/{id}/timeline/` | Chronological observations timeline (2015 → 2026) |
| | `POST` | `/api/v1/satellite/change-analysis/` | Execute 11-stage bi-temporal change detection |
| | `GET` | `/api/v1/satellite/change-events/` | Query historical change events with GeoJSON geometry |
| **Queries** | `POST` | `/api/v1/sessions/{id}/queries/` | Submit natural-language question to agent orchestrator |
| | `GET` | `/api/v1/sessions/{id}/queries/{id}/` | Retrieve query result and 10-key Answer Contract |
| | `GET` | `/api/v1/sessions/{id}/queries/{id}/stream/` | Server-Sent Events (SSE) live progress execution stream |
| | `GET` | `/api/v1/sessions/{id}/queries/{id}/export/{fmt}/` | Export in `geojson`, `csv`, `json`, `geotiff`, or `png` |
| **Reports** | `POST` | `/api/v1/sessions/{id}/reports/` | Generate PDF or HTML intelligence dossier |
| | `GET` | `/api/v1/sessions/{id}/reports/{id}/download/` | Stream generated PDF/HTML file |
| **Models** | `GET` | `/api/v1/models/` | Model registry listing status, baseline tasks, and licenses |
