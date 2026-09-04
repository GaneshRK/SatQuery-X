# SatQuery AI — Production API Reference (v2.0)

Base URL: `http://localhost:8000/api/v1/`

---

## 1. System Health & Observability

### `GET /api/v1/health/`
Performs comprehensive operational health checks across all platform subsystems.
* **Permissions:** Public
* **Response:**
```json
{
  "status": "UP",
  "subsystems": {
    "django": { "status": "healthy", "version": "5.1", "mode": "production" },
    "database": { "engine": "postgresql", "status": "healthy", "postgis_available": true },
    "redis": { "status": "healthy", "broker": "redis://localhost:6379/0" },
    "celery": { "status": "configured", "fallback_mode": "SYNCHRONOUS_DEV_FALLBACK_READY" },
    "copernicus": { "status": "healthy", "primary_endpoint": "https://stac.dataspace.copernicus.eu/v1/search" },
    "ai_providers": { "active_reasoning_provider": "local" },
    "storage": { "status": "healthy", "free_disk_gb": 120.4 },
    "map_provider": { "status": "healthy", "basemaps": ["esri_satellite", "carto_dark", "osm_standard"] }
  }
}
```

---

## 2. Dynamic Raster Tile Server

### `GET /api/v1/imagery/{image_id}/tiles/{z}/{x}/{y}/`
Renders standard 256x256 Web Mercator PNG tiles on the fly directly from the GeoTIFF raster using windowed I/O.
* **Query Parameters:**
  * `layer`: `rgb` (default), `false_color`, `ndvi`, `ndwi`, `ndbi`
* **Response:** `image/png` binary stream.

---

## 3. Satellite Data Acquisition (CDSE STAC v1)

### `POST /api/v1/satellite/search/`
Searches Copernicus Data Space Ecosystem for Sentinel-1 and Sentinel-2 scenes.
* **Body:**
```json
{
  "session_id": "uuid",
  "sensor": "SENTINEL-2",
  "date_start": "2026-08-01",
  "date_end": "2026-08-30",
  "max_cloud_cover": 15.0,
  "aoi_geometry": { "type": "Polygon", "coordinates": [...] }
}
```

### `GET /api/v1/satellite/search/{request_id}/candidates/`
Lists scenes matching search criteria with acquisition date, cloud cover, and footprints.

### `POST /api/v1/satellite/search/{request_id}/select/`
Triggers background ingestion, checksum verification, and `RasterEngine` validation for the selected scene.

---

## 4. AOI Operations & "Ask This Area"

### `POST /api/v1/sessions/{session_id}/images/{image_id}/clip_aoi/`
Clips raster by a user-drawn AOI geometry polygon and creates a derived `ImageAsset`.
* **Body:**
```json
{
  "aoi_geometry": {
    "type": "Polygon",
    "coordinates": [[[93.0, 26.5], [93.1, 26.5], [93.1, 26.6], [93.0, 26.6], [93.0, 26.5]]]
  }
}
```

---

## 5. Multi-Format Query Exports

### `GET /api/v1/sessions/{session_id}/queries/{query_id}/export/{export_format}/`
Exports analysis findings and evidence in standard geospatial formats.
* **Formats:**
  * `geojson`: GeoJSON FeatureCollection of all detected evidence regions.
  * `csv`: Tabular spreadsheet with metrics, classes, and areas.
  * `json`: Full 10-Key canonical Answer Contract.
  * `geotiff`: Downloadable underlying GeoTIFF raster.
  * `png`: High-resolution preview image.

---

## 6. Query Execution & SSE Streaming

### `POST /api/v1/sessions/{session_id}/queries/`
Submits a query to the agent planner and execution engine.

### `GET /api/v1/sessions/{session_id}/queries/{query_id}/stream/`
Server-Sent Events (SSE) live progress stream broadcasting step execution events.
