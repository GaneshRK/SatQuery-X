# SatQuery-X: Agentic Geospatial Intelligence Engine for Multimodal Satellite Reasoning
**ISRO Smart India Hackathon (SIH 2026) — Problem Statement 26167**

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/Django-5.1-092e20.svg)](https://www.djangoproject.com/)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://reactjs.org/)
[![MapLibre GL](https://img.shields.io/badge/MapLibre_GL-6.7-blueviolet.svg)](https://maplibre.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.4+-blue.svg)](https://postgis.net/)
[![Tests](https://img.shields.io/badge/Tests-91%2F91%20Passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

SatQuery-X is a production-grade remote-sensing AI platform enabling analysts, planners, and judges to ingest satellite imagery (**Single Optical Image, Optical+SAR Cross-Modal Pair, or Bi-Temporal Pair**) and ask natural-language questions. An agentic Small Language Model (SLM) orchestrator routes questions across 25 remote-sensing specialist tools, executes models, and delivers verifiable answers with visual evidence overlays, geodesic area quantification ($\text{ha} / \text{km}^2$), and a complete execution trace.

---

## 🛰️ Key Capabilities & 4 Core Operating Modes

| Mode | Modality | Primary Capabilities | Specialist Models & Tools |
|---|---|---|---|
| **Mode 1: Single Image** | Optical / Multispectral (Sentinel-2, Landsat, Cartosat) | Scene captioning, visual question answering, visual grounding, spectral indices (NDVI/NDWI/NDBI/NBR) | GeoChat / BLIP VQA, RemoteCLIP Captioner, Grounding DINO Object Proposal |
| **Mode 2: Cross-Modal Fusion** | Optical + SAR (Sentinel-2 + RISAT-1A / Sentinel-1) | Penetrates cloud, haze, and smoke; cross-modal agreement confidence; joint built-up and waterbody segmentation | Dual-Branch Fusion Head, Lee Speckle Filter, Decibel Log Transform, Cross-Modal Agreement Scorer |
| **Mode 3: Bi-Temporal Change Detection** | Multi-date ($T_1 \rightarrow T_2$) | Surface change mapping, segmented change masks, connected components, geodesic area quantification | ChangeFormer, Calibrated Otsu Thresholding, Morphological Filtering, PyProj Equal-Area Engine |
| **Mode 4: Change-Based VQA** | Multi-date ($T_1 \rightarrow T_2$) | Natural-language reasoning over detected changes, directional sector analysis, quantitative change attribution | Grounded Change Reasoner, Temporal Sector Partitioning, Geodesic Area Attribution |

---

## 🏛️ System Architecture

```
                                  SATQUERY-X
                                       │
                              USER (Web UI / API)
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │ API GATEWAY (Django / DRF)│  <- Auth, RBAC, Rate Limiting, Audit Log
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │   INGESTION & METADATA    │  <- Magic-byte MIME, SensorProfile registry,
                         │   (Rasterio / PyProj)     │     WGS84 reproject, windowed XYZ tiling
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │ SLM QUERY ROUTER & AGENT  │  <- Pydantic StructuredTaskPlan schema,
                         │ (Qwen3-SLM / Understander)│     Input compatibility validator (§8)
                         └─────────────┬─────────────┘
                                       │
    ┌────────────────────────┬─────────┴────────┬────────────────────────┐
    ▼                        ▼                  ▼                        ▼
RS-VQA & CAPTION        RS-GROUNDING      CHANGE-DETECTION        OPTICAL-SAR FUSION
(GeoChat / RemoteCLIP)  (Grounding DINO)  (ChangeFormer / Otsu)   (Dual-Branch Cross-Modal)
    │                        │                  │                        │
    └────────────────────────┴─────────┬────────┴────────────────────────┘
                                       ▼
                         ┌───────────────────────────┐
                         │      EVIDENCE ENGINE      │  <- GeoJSON polygons, geodesic CEA math,
                         │ (Shapely / PyProj / Geod) │     bounding boxes, multi-source agreement
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │ RESPONSE & AUDIT COMPOSER │  <- Grounded natural language, trace steps,
                         │ (ReportLab PDF & HTML)    │     conflict alerts, zero hallucinations
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │ FRONTEND (React/MapLibre) │  <- Split swipe slider, vector GPU reticle,
                         │                           │     chat console, execution timeline
                         └───────────────────────────┘
```

---

## 🔬 25-Tool Remote Sensing Agentic Registry

SatQuery-X implements a typed `ToolRegistry` with strict JSON-schema parameters, timeouts, and resource metadata:
1. `rsvqa` — Remote Sensing Visual Question Answering
2. `rscaption` — Dense Remote Sensing Scene Captioning
3. `rsgrounding` — Open-Vocabulary Visual Feature Grounding
4. `changedetection` — Bi-Temporal Surface Change Detection
5. `changevqa` — Change Reasoning & Attribution VQA
6. `opticalsarfusion` — Optical + SAR Dual-Branch Fusion
7. `spectralindex` — Sensor-Calibrated Indices (NDVI, NDWI, NDBI, NBR)
8. `watersegmentation` — Calibrated Waterbody & Inundation Extraction
9. `vegetationsegmentation` — Calibrated Canopy & Vegetation Extraction
10. `structurecount` — Built-Up Structure & Building Counting
11. `rasterinspect` — Sub-Pixel Geotag & Band Metadata Inspection
12. `rastervalidation` — GeoTIFF Integrity & Georeference Validation
13. `windowedread` — Large-Scale Out-of-Core Windowed Chip Extraction
14. `tilerender` — Dynamic XYZ Slippy-Map Tile Generation
15. `geocoding` — Forward & Reverse Geospatial Coordinate Resolution
16. `aoiclip` — Arbitrary Polygonal AOI Raster Clipping
17. `histogramanalysis` — Radiometric Contrast & Histogram Distribution
18. `coregistration` — Sub-Pixel Feature Matching & Affine Alignment
19. `spatialrelation` — Directional & Topological Sector Analysis
20. `temporalcomparison` — Historical Multi-Pass Trajectory Analysis
21. `reportgeneration` — Production Intelligence Dossiers (PDF / HTML)
22. `evidenceexport` — Structured GeoJSON / SHP / TIFF Evidence Export
23. `webresearch` — SSRF-Guarded External Geospatial Fact Verification
24. `satellitesearch` — Copernicus CDSE Real-Time Scene Discovery
25. `modeldisagreement` — Multi-Model Conflict & Discordance Detection

---

## 🎯 7 Golden SIH Test Scenarios (One-Click Evaluator Demos)

SatQuery-X includes pre-configured, single-click demonstration scenarios accessible via API or the Web Dashboard:

| # | Scenario Key | Description | Endpoint |
|---|---|---|---|
| **1** | `scenario_1_caption` | Single-Image Scene Captioning over Sentinel-2 | `POST /api/v1/demo-scenarios/bootstrap/scenario_1_caption/` |
| **2** | `scenario_2_vqa` | Single-Image VQA with Geospatial Verification | `POST /api/v1/demo-scenarios/bootstrap/scenario_2_vqa/` |
| **3** | `scenario_3_grounding` | Single-Image Visual Grounding over Cartosat-2S | `POST /api/v1/demo-scenarios/bootstrap/scenario_3_grounding/` |
| **4** | `scenario_4_change_detection` | Bi-temporal Change Detection & Area Quantification | `POST /api/v1/demo-scenarios/bootstrap/scenario_4_change_detection/` |
| **5** | `scenario_5_change_vqa` | Bi-temporal Change Reasoning over Forest Cover | `POST /api/v1/demo-scenarios/bootstrap/scenario_5_change_vqa/` |
| **6** | `scenario_6_optical_sar_fusion` | Optical + SAR Joint Analysis under Cloud Cover | `POST /api/v1/demo-scenarios/bootstrap/scenario_6_optical_sar_fusion/` |
| **7** | `scenario_7_multiturn` | Multi-Turn Conversational Follow-Up ("Where?" -> "How much?") | `POST /api/v1/demo-scenarios/bootstrap/scenario_7_multiturn/` |

---

## 💻 Installation & Local Running Guide

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- GDAL / PROJ libraries (standard rasterio wheels bundle these)

### 1. Backend Setup (Django + DRF)
```bash
# Navigate to backend
cd backend

# Activate virtual environment
# Windows:
..\.venv\Scripts\activate
# Linux/macOS:
source ../.venv/bin/activate

# Apply migrations
python manage.py migrate

# Create superuser / analyst account
python manage.py createsuperuser

# Start Django development server
python manage.py runserver 0.0.0.0:8000
```

### 2. Frontend Setup (React + MapLibre GL)
```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start Next.js development server
npm run dev
```
The web dashboard will be available at `http://localhost:3000`.

### 3. Model Weights & Offline Check
```bash
# Check model inventory and hardware acceleration
python scripts/check_models.py

# Optional: Download local open-weight model weights
python scripts/download_models.py
```

### 4. Running the Test Suite
```bash
# Run full automated test suite (91 tests)
pytest -v

# Run golden SIH evaluation scenarios
pytest tests/test_golden_scenarios.py -v
```

---

## 🛡️ Honest AI & Responsible Geospatial Disclosure
- **Zero Hallucination Policy:** Surface areas, coordinates, and pixel metrics are strictly computed using geodesic projection-aware math (`pyproj.Geod` and Cylindrical Equal Area reprojection).
- **Truthful Model Attribution:** When running in low-hardware or lightweight environments, model outputs are explicitly labeled with `[CV Fallback]` or `[BASELINE]` provenance tags. We never claim models are fine-tuned when they are running zero-shot or baseline pipelines.
- **SSRF Guarded Web Research:** External search queries are validated against private IP ranges, cloud metadata endpoints (`169.254.169.254`), and non-HTTPS protocols.

---

## 📜 License & Compliance
This software is licensed under the MIT License. Embedded datasets and model weights comply with Apache-2.0, MIT, and CC-BY-NC-4.0 licenses. See `docs/MODEL_AND_DATA_LICENSES.md` for full details.
