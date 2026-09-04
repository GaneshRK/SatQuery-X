# SATQUERY-X V2 — MASSIVE PRODUCTION UPGRADE AUDIT

**Date:** September 2026  
**Auditor:** Lead AI Architect & Geospatial Systems Engineer  
**Specification:** SIH PS 26167 (ISRO / Dept. of Space) — V2 Production Directive  
**Status:** Comprehensive Baseline Assessment  

---

## 1. System Component Audit Matrix

| Feature | Current State | Status | Dependencies | Priority | Files Affected |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CDSE STAC Search** | Custom `CopernicusProvider` hits `catalogue.dataspace.copernicus.eu/stac/search` with fallback | **PARTIAL** | `urllib`, STAC API | **P0** | `backend/apps/satellite/providers/copernicus.py`, `views.py` |
| **CDSE Authentication** | No OAuth2 TokenManager; queries anonymous STAC only | **MISSING** | `requests`/`urllib`, CDSE Identity Realm | **P0** | `backend/apps/satellite/providers/auth.py` |
| **Real Satellite Scene Ingestion** | Mock scene generator creates GeoTIFF on selection; live download task is not wired to CDSE OData/S3 | **PARTIAL** | Celery, CDSE TokenManager, `storage` | **P0** | `backend/apps/satellite/tasks.py`, `views.py` |
| **Unified Raster Engine** | Scattered functions across `math.py`, `indices.py`, `cv_engine.py` | **PARTIAL** | `rasterio`, `numpy`, `scipy` | **P0** | `backend/apps/geospatial/raster_engine.py` |
| **Dynamic XYZ Raster Tiles** | Static preview PNG generation only; no XYZ map tile endpoint | **MISSING** | `rasterio`, Pillow, Cache | **P1** | `backend/apps/imagery/tiles.py`, `backend/apps/imagery/views.py` |
| **MapLibre GL GIS Canvas** | WebGL Map with Esri, Carto, OSM basemaps, raster overlay, GeoJSON evidence polygons | **IMPLEMENTED** | `maplibre-gl`, React | **P0** | `frontend/src/components/MapViewer.tsx` |
| **AOI Drawing Engine** | Viewer renders raster and evidence, but lacks interactive polygon/rectangle drawing controls | **MISSING** | MapLibre Draw / Canvas handlers | **P1** | `frontend/src/components/MapViewer.tsx`, `frontend/src/components/AoiDrawer.tsx` |
| **"Ask This Area" Workflow** | User can ask general queries, but cannot clip active imagery to a drawn AOI directly from map | **MISSING** | AOI Engine, `RasterEngine.clip` | **P1** | `frontend/src/components/MapViewer.tsx`, `backend/apps/agent/` |
| **AI Provider Abstraction** | Hardcoded baseline wrappers (`RS_VQA`, `RS_CAPTION`, `CHANGE_DETECTION`) in model registry | **PARTIAL** | `transformers`, `torch`, `openai` | **P1** | `backend/apps/ai_providers/`, `backend/apps/models/` |
| **Server-Side LLM/VLM Key Security** | No OpenAI or HuggingFace remote provider configured; keys absent | **MISSING** | `openai`, `huggingface_hub` | **P1** | `backend/apps/ai_providers/openai_provider.py`, `hf_provider.py` |
| **Model Registry 2.0 & Health Check** | Static list in `registry.py`; no dynamic `health_check()` or GPU detection | **PARTIAL** | `torch.cuda`, system check | **P2** | `backend/apps/models/registry.py`, `views.py` |
| **Deterministic CV Pipelines** | Otsu binarization, NDWI, NDVI, Sobel structural edge contour counting | **IMPLEMENTED** | `numpy`, `scipy`, `cv_engine.py` | **P0** | `backend/apps/geospatial/cv_engine.py` |
| **Structured Answer Contract** | Query returns answer string, confidence float, execution steps, and evidence regions | **PARTIAL** | DRF serializers, Agent | **P0** | `backend/apps/queries/models.py`, `backend/apps/agent/executor.py` |
| **Confidence & Data Quality Engine** | Fixed or heuristic confidence; no multi-signal composite quality score (0-100) | **MISSING** | DataQualityScore, heuristics | **P1** | `backend/apps/agent/confidence.py` |
| **Provenance Graph & Audit Trail** | Basic audit log exists in `apps/audit`; lacks step-by-step lineage DAG | **PARTIAL** | `apps/audit`, `apps/evidence` | **P1** | `backend/apps/evidence/provenance.py` |
| **Conversational Memory & Follow-ups** | `Session.conversation_history` stores messages; ChatConsole displays them; reference resolution basic | **PARTIAL** | Understander FSM | **P1** | `backend/apps/agent/understander.py`, `ChatConsole.tsx` |
| **PostGIS Spatial Intersect Engine** | Polygons stored in JSON/EvidenceRegion; no raw PostGIS spatial geometry operations | **PARTIAL** | `django.contrib.gis`, PostGIS | **P1** | `backend/apps/geospatial/spatial_db.py` |
| **Official PDF & HTML Dossiers** | ReportLab PDF and styled HTML generation implemented with honest model labeling | **IMPLEMENTED** | `reportlab`, Django templates | **P0** | `backend/apps/reports/tasks.py`, `views.py` |
| **Exportable Geo Data (GeoJSON/CSV)** | Evidence regions queryable via API; lacks single-click bundle export endpoints | **PARTIAL** | DRF APIView, GeoJSON | **P2** | `backend/apps/evidence/views.py` |
| **System Health & Observability** | No central `/api/v1/health/` dashboard verifying PostGIS, Redis, Celery, Providers | **MISSING** | Django DB, Redis, Celery | **P1** | `backend/apps/system/views.py` |
| **Live Showcase Demonstrations** | `seed_sih_demos` populates 5 realistic remote sensing showcases | **IMPLEMENTED** | Django ORM, Rasterio | **P0** | `backend/apps/sessions/management/commands/seed_sih_demos.py` |

---

## 2. Priority Implementation Queues

### **Priority 0 (P0): Core Foundations & Critical Real-Data Bridges**
1. **Copernicus CDSE V1 STAC & TokenManager:**
   - Upgrade endpoint to `https://stac.dataspace.copernicus.eu/v1/` and add OData query layer.
   - Implement `CDSETokenManager` with automatic OAuth2 refresh using `CDSE_USERNAME`, `CDSE_PASSWORD`, `CDSE_CLIENT_ID`.
   - Implement asynchronous Celery download job with checksum, storage write, and rasterio validation.
2. **Unified `RasterEngine` Architecture:**
   - Consolidate raster operations (`open`, `inspect`, `read_window`, `resize`, `reproject`, `clip`, `band_math`, `tile`, `thumbnail`) into `apps/geospatial/raster_engine.py` with chunked windowed I/O.
3. **Full Structured Answer Contract:**
   - Update agent executor to emit strictly conformant V2 output:
     `{ answer, confidence, findings, measurements, regions, evidence, sources, models, methods, limitations }`.

### **Priority 1 (P1): Interactive GIS & Geospatial Intelligence Workflows**
1. **Interactive AOI Engine & "Ask This Area":**
   - Add drawing tools (Rectangle, Polygon, Circle, Point) to `MapViewer.tsx`.
   - Implement "Ask This Area" frontend button and backend clipping endpoint (`/api/v1/imagery/{id}/clip_aoi/`).
2. **Dynamic XYZ Raster Tile Server:**
   - Endpoint: `/api/v1/imagery/{id}/tiles/{z}/{x}/{y}/` supporting RGB, False Color, NDVI, NDWI, NDBI with tile caching.
3. **Pluggable `AIProvider` Framework:**
   - Abstract `AIProvider` with `LocalProvider`, `HuggingFaceProvider`, and `OpenAIProvider`.
   - Server-side API key handling without frontend leakage.
4. **Data Quality & Confidence Engine:**
   - Implement composite `DataQualityScore` (cloud cover, resolution, CRS, nodata percentage, registration quality) mapped to 0–100 scale.
5. **System Health & Observability:**
   - Create `/api/v1/health/` endpoint checking PostGIS, Redis, Celery, CDSE, and AI provider status.

### **Priority 2 (P2): Advanced Visuals, Provenance & Export Ecosystem**
1. **Provenance Graph Visualization:**
   - Generate interactive execution lineage (Scene -> Asset -> Process -> Tool -> Evidence -> Answer).
2. **Multi-Format Export Suite:**
   - One-click export for GeoJSON, GeoTIFF, CSV evidence tables, and PNG crops.
3. **Conversational Pronoun & Filter Resolution:**
   - Enhance `understander.py` to resolve contextual follow-ups ("Which parts decreased?", "How much?", "Where?").

### **Priority 3 (P3): Commercial SaaS Polish & Documentation**
1. **Commercial Role-Based Access Control (RBAC):**
   - Enforce Owner, Admin, Analyst, Viewer, Judge permissions on all mutation endpoints.
2. **Documentation Suite:**
   - Update `README.md`, `ARCHITECTURE.md`, `API.md`, `DEPLOYMENT.md`, `SECURITY.md`, `DEMO.md`.
