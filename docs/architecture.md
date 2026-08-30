# SatQuery-X Architecture & System Blueprint

**SatQuery-X** is an Agentic Geospatial Intelligence Engine for Multimodal Satellite Reasoning (SIH26167). It enables natural-language querying over satellite imagery across **4 core input modes**, powered by an agentic orchestrator, specialist model registry, real GeoTIFF coordinate handling, visual evidence engine, exportable reports, and modern web interface.

---

## 1. High-Level System Architecture

```
                             SATQUERY-X
                                  │
                         USER (Web UI / API)
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │   API GATEWAY (FastAPI) │  <- JWT auth, rate limiting, Pydantic v2
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │  INGESTION & VALIDATION │  <- GeoTIFF/PNG/JPEG parsing,
                     │  (rasterio/GDAL/Pillow) │     CRS extraction, mode detection,
                     └────────────┬────────────┘     co-registration check
                                  │
                     ┌────────────▼────────────┐
                     │  QUERY UNDERSTANDER     │  <- Intent & entity extraction,
                     └────────────┬────────────┘     modality classification, Mission Mode
                                  │
                     ┌────────────▼────────────┐
                     │  AGENTIC PLANNER        │  <- Tool-calling loop, registry lookup,
                     │  (Deterministic FSM)    │     sequential dependencies, parallel fan-out
                     └────────────┬────────────┘
                                  │
        ┌───────────┬─────────┼─────────┬──────────────┐
        ▼           ▼         ▼         ▼              ▼
   RS-VQA       RS-CAPTION  RS-GROUND  CHANGE-DET   OPTICAL-SAR
   MODEL        MODEL       MODEL      + CHANGE-VQA  FUSION MODEL
        │           │         │         │              │
        └───────────┴─────────┼─────────┴──────────────┘
                              ▼
                 ┌─────────────────────────┐
                 │   EVIDENCE ENGINE        │ <- Overlays, masks, GeoJSON (EPSG:4326),
                 └────────────┬────────────┘    confidence aggregation, metric area km²
                              │
                 ┌────────────▼────────────┐
                 │  RESPONSE COMPOSER      │ <- Answer + trace + evidence JSON
                 └────────────┬────────────┘
                              │
                 ┌────────────▼────────────┐
                 │  PERSISTENCE & JOBS     │ <- PostgreSQL + PostGIS, S3/MinIO,
                 └────────────┬────────────┘    Celery + Redis
                              │
                 ┌────────────▼────────────┐
                 │  FRONTEND (Next.js/TS)  │ <- MapLibre/Leaflet, Chat, Trace,
                 └─────────────────────────┘    Evidence Drawer, PDF/HTML Report
```

---

## 2. The Four Input Modes

1. **Mode 1 — Single Image**: One optical/multispectral image or one SAR image + free-text query $\rightarrow$ RS-VQA, RS-Captioning, or Text-Guided Grounding.
2. **Mode 2 — Cross-Modal Pair**: Co-registered optical + SAR image of the same geographic footprint + query $\rightarrow$ Fused cross-modal land cover analysis.
3. **Mode 3 — Bi-Temporal Pair**: Image $T_1$ + Image $T_2$ (same area, different acquisition dates) + query $\rightarrow$ Pixel-level change map, bounding box regions, and change description.
4. **Mode 4 — Change-Based VQA**: $T_1$ + $T_2$ + specific yes/no or quantitative question $\rightarrow$ Direct reasoned answer over detected changes with quantified area ($\text{km}^2$ and hectares).

---

## 3. Specialist Model Registry (§4 Contract)

| Model ID | Task Type | Accepted Input Modes | Architecture | Backing Corpora | Output Contract |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `RS_VQA` | Visual Question Answering | `single_image` | BLIP-VQA RS-Adapted | RSVQA, VRSBench-VQA | `{answer: str, confidence: float, attention_region}` |
| `RS_CAPTION` | Image Captioning | `single_image` | BLIP RS-Caption | VRSBench-Caption, BigEarthNet | `{caption: str, confidence: float}` |
| `RS_GROUNDING` | Text-Guided Grounding | `single_image` | Spectral Saliency & Region Proposal | VRSBench-Grounding | `{boxes: [bbox], masks, confidence: float}` |
| `CHANGE_DETECTION` | Bi-temporal Change Map | `bi_temporal` | Siamese Feature Difference Encoder | LEVIR-CD, CDVQA | `{change_mask: mask, change_regions: [bbox]}` |
| `CHANGE_VQA` | Change-Based VQA | `bi_temporal` | Reasoned Change Classifier Head | CDVQA | `{answer: str, confidence: float, supporting_regions}` |
| `OPTICAL_SAR_FUSION` | Cross-Modal Analysis | `cross_modal_pair` | Dual-Branch Cross-Attention Head | BigEarthNet (S1+S2) | `{answer: str, class_map, confidence: float}` |

---

## 4. Agentic Planner & Execution Trace (§5 Contract)

Every query executed by SatQuery-X produces an auditable, structured execution trace conforming to:

```json
{
  "query": "Has built-up area increased between these two images?",
  "detected_mode": "bi_temporal",
  "task_classification": "change_vqa",
  "plan": [
    {"step": 1, "tool": "CHANGE_DETECTION", "version": "v0.1-baseline", "params": {}},
    {"step": 2, "tool": "CHANGE_VQA", "version": "v0.1-baseline", "params": {"question": "built-up area trend", "change_mask_ref": "step1.change_mask"}}
  ],
  "outputs": {
    "step1": { "model_id": "CHANGE_DETECTION", "answer": "Detected change covering 18.4% of area", "confidence": 0.85 },
    "step2": { "model_id": "CHANGE_VQA", "answer": "Yes — built-up area increased across 6 detected regions.", "confidence": 0.91 }
  },
  "answer": "Yes — built-up area increased across 6 detected regions.",
  "confidence": 0.85,
  "evidence": {
    "change_mask_url": "/v1/storage/sessions/.../step1_change_mask.png",
    "overlay_url": "/v1/storage/sessions/.../step1_overlay.png",
    "bboxes": [{"x1": 50, "y1": 60, "x2": 180, "y2": 200, "label": "change", "confidence": 0.75}],
    "geojson": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [...]}}],
    "quantified_area_km2": 4.25,
    "quantified_area_hectares": 425.0,
    "change_percentage": 18.4
  },
  "timings_ms": {
    "step1": 14.2,
    "step2": 8.5,
    "total": 24.1
  },
  "errors": []
}
```

---

## 5. Geospatial Coordinate Pipeline

1. **Ingestion & Validation**:
   - Detects GeoTIFF vs plain PNG/JPEG.
   - Extracts CRS (`EPSG:4326`, `EPSG:3857`, UTM projections), affine transformation matrix `[a, b, c, d, e, f]`, band count, nodata value, and resolution.
2. **Co-Registration Verification**:
   - For paired inputs (optical+SAR or $T_1+T_2$), verifies spatial bounding box overlap and resolution compatibility.
3. **Pixel-to-GeoJSON Transformation**:
   - Transforms pixel coordinates $[x_1, y_1, x_2, y_2]$ via the affine transformation into geographic coordinates (Longitude/Latitude, SRID 4326) and exports valid GeoJSON polygons for map rendering.
4. **Metric Area Calculation**:
   - Calculates real surface area in $\text{km}^2$ and hectares using Ground Sample Distance (GSD) derived from the GeoTIFF affine matrix.
