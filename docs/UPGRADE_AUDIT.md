# SatQuery-X System Upgrade Audit

**Platform**: SatQuery AI — Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Text Queries  
**Problem Statement**: SIH 26167  
**Audit Date**: September 2026  
**Auditor**: Lead AI Architect, Senior Geospatial/Remote Sensing Engineers, and DevOps Team  

---

## 1. Executive Summary

This audit assesses the active state of the **SatQuery-X** repository prior to executing the **Agentic Earth Observation Intelligence Platform** upgrade. The repository already features a robust foundation:
- Python 3.11 + Django 5.1 + Django REST Framework backend with Celery/Redis tasks.
- Next.js 14 + React 18 + MapLibre GL JS frontend with 3D Earth from Orbit view and interactive timeline controls.
- Comprehensive GDAL / Rasterio / OpenCV / Shapely geospatial processing engine with windowed reading and spectral indices.
- Copernicus Data Space Ecosystem (CDSE) STAC v1 integration with OAuth2 token manager and deterministic offline mock fallback.
- 51 automated backend pytest tests (100% passing) covering agents, CV engine, spectral math, satellite providers, and temporal APIs.

---

## 2. Current Working Functionality (Preserved & Active)

| Component | Working Functionality | Status |
| :--- | :--- | :--- |
| **Authentication** | Custom User model, JWT login/refresh, analyst/admin credentials, RBAC | **Active & Tested** |
| **Sessions** | Project/analysis session management (`/api/v1/sessions/`), multi-session isolation | **Active & Tested** |
| **Imagery Ingestion** | GeoTIFF/PNG/JPEG upload, GDAL metadata extraction, CRS detection, bounds, preview generation | **Active & Tested** |
| **Dynamic XYZ Tiles** | `/api/v1/imagery/<id>/tiles/<z>/<x>/<y>/` windowed raster tile streaming via RasterEngine | **Active & Tested** |
| **Spectral Indices** | In-memory chunked computation of NDVI, NDWI, NDBI, SAVI, EVI, MNDWI, NBR | **Active & Tested** |
| **CV Engine** | Otsu thresholding, morphological filtering, water/vegetation segmentation, structure counting | **Active & Tested** |
| **Satellite STAC** | Copernicus CDSE STAC v1 querying, candidate scene discovery, token refresh manager | **Active & Tested** |
| **Database V2 Models** | `DataProvider`, `SatelliteScene`, `SatelliteAsset`, `AreaOfInterest`, `TemporalObservation`, `ChangeEvent`, `DerivedRaster`, `AOIMonitoring`, `DataSyncJob` | **Migrated & Active** |
| **Temporal APIs** | AOI timeline endpoint (2016–2026), bi-temporal change analysis, sync status, monitoring | **Active & Tested** |
| **Frontend 3D Globe** | WebGL 3D Earth from Orbit (`EarthObservatory.tsx`), orbital camera descent, location search, timeline slider | **Active & Tested** |
| **Model Registry** | 7 remote sensing models registered (`RS_VQA`, `RS_CAPTION`, `CHANGE_DETECTION`, etc.) | **Active & Tested** |
| **Exports** | Multi-format query exports: GeoJSON, CSV, JSON, GeoTIFF, PNG | **Active & Tested** |
| **Observability** | Structured logging, request IDs, `/api/v1/health/` multi-subsystem probe | **Active & Tested** |

---

## 3. Current Limitations & Incomplete Elements

1. **Agent Tool Orchestration**:
   - The current `understander.py` and `planner.py` use regex and heuristic pattern matching. It needs a formal `QueryOptimizer` producing structured JSON plans (`intent`, `aoi`, `time_range`, `modalities`, `analysis`, `external_evidence_required`).
2. **Web-Augmented Reasoning**:
   - Currently, if satellite data lacks external context (e.g. verifying flood damage against meteorological warnings or agricultural loss against drought reports), the agent cannot retrieve verified external evidence.
   - Requires a dedicated `WebResearchAgent` with SSRF protection, domain trust tiers (Tier 1 Gov/Science to Tier 4 General), and TTL-based audit caching without permanently storing arbitrary websites.
3. **GeoReason Agent & Unified Evidence Graph**:
   - While spatial `EvidenceRegion` records are generated, external evidence nodes are not yet linked into a composite graph.
4. **Follow-Up Question Generator**:
   - The UI displays answers, but does not yet emit context-aware suggested follow-up questions based on the executed intelligence graph.
5. **Region-Level Interactive Intelligence**:
   - Allow users to click or draw arbitrary bounding boxes/polygons on the active satellite raster and immediately trigger localized VLM/CV analysis on that sub-region.

---

## 4. What is Real vs Mocked

- **Real & Deterministic**:
  - All geospatial math (Rasterio, Shapely, PyProj, metric pixel area calculations).
  - All spectral index calculations (NDVI, NDWI, NDBI, NBR).
  - Copernicus CDSE STAC v1 integration (`https://stac.dataspace.copernicus.eu/v1/search`) with OAuth2 tokens.
  - Dynamic XYZ tile server reading windowed GeoTIFF rasters directly.
  - Database schema, PostGIS geometry types, UUID primary keys, and relations.
  - Calibrated confidence scoring based on cloud cover, resolution, and registration error.
- **Mock Fallbacks (Clearly Labeled & Safe)**:
  - `MockSatelliteProvider`: Automatically activates when Copernicus CDSE credentials are not set or when `SATQUERY_MOCK_SATELLITE=True`. Never claims mock data is live satellite data.
  - Baseline model weights for offline inference when Hugging Face / OpenAI keys are not configured.

---

## 5. Existing APIs & Frontend Component Inventory

### Backend APIs (`/api/v1/`)
- `/api/v1/auth/` (login, register, refresh)
- `/api/v1/health/` (database, redis, celery, storage, copernicus status)
- `/api/v1/sessions/` (CRUD sessions)
- `/api/v1/sessions/<id>/images/` (list/upload imagery)
- `/api/v1/sessions/<id>/pairs/` (bi-temporal and cross-modal image pairs)
- `/api/v1/imagery/<id>/tiles/<z>/<x>/<y>/` (dynamic XYZ raster tiles)
- `/api/v1/sessions/<id>/queries/` (submit natural language query)
- `/api/v1/sessions/<id>/queries/<id>/stream/` (SSE live execution stream)
- `/api/v1/sessions/<id>/queries/<id>/export/<format>/` (GeoJSON/CSV/GeoTIFF export)
- `/api/v1/sessions/<id>/reports/` (generate and download PDF/HTML reports)
- `/api/v1/satellite/search/` (STAC search)
- `/api/v1/satellite/scenes/` (catalogue scenes)
- `/api/v1/satellite/aoi/` (AOI list, create, and spatial auto-bounding)
- `/api/v1/satellite/aoi/<id>/timeline/` (multi-decadal observation timeline)
- `/api/v1/satellite/change-analysis/` (bi-temporal change analysis)
- `/api/v1/satellite/change-events/` (global change events)
- `/api/v1/satellite/sync-status/` (near-real-time synchronization watermark)
- `/api/v1/models/` (model registry list and detail)

### Frontend Components (`frontend/src/components/`)
- `EarthObservatory.tsx`: 3D WebGL Globe with orbital camera descent hierarchy and location search.
- `TimelineSlider.tsx`: Multi-decadal observation slider (2016–2026) with time-lapse playback and change triggers.
- `MapViewer.tsx`: 2D GIS raster tile viewer, band switcher, opacity slider, bounding box/polygon drawing tools.
- `ChatConsole.tsx`: Natural-language conversational console with streaming trace and preset suggestions.
- `ExecutionTraceTimeline.tsx`: Auditable timeline of executed agent tools.
- `EvidenceDrawer.tsx`: Spatial vector polygons and metric measurements.
- `ReportModal.tsx`: Comprehensive intelligence report viewer with export options.
- `UploadModal.tsx`: Drag-and-drop raster upload with client-side metadata preview.
- `SatelliteSearchModal.tsx`: STAC search modal with cloud cover and sensor filters.
- `Header.tsx`: Session switcher, system mode badge, new session trigger.

---

## 6. Migration & Preservation Strategy

- **Rule 1**: Zero data destruction. No `DROP TABLE`, `TRUNCATE`, or destructive schema alterations.
- **Rule 2**: All 51 existing pytest tests must pass after every upgrade phase.
- **Rule 3**: External web retrieval must be strictly guarded (SSRF protection, domain trust tiers, TTL caching) and never permanently mirror arbitrary websites.
- **Rule 4**: Transparent provenance and calibrated confidence must accompany every answer.
