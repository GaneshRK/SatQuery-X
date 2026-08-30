# SatQuery-X: Agentic Geospatial Intelligence Engine for Multimodal Satellite Reasoning
**SIH26167 — Production-Grade Implementation Specification**

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14.2+-black.svg)](https://nextjs.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.4+-blue.svg)](https://postgis.net/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

SatQuery-X enables analysts and decision-makers to upload satellite imagery (**Single Image, Optical+SAR Cross-Modal Pair, or Bi-Temporal Pair**) and ask natural-language questions. An agentic orchestrator routes the query to remote-sensing specialist models, fuses their outputs, and returns an auditable answer with visual evidence overlays, metric area quantification ($\text{km}^2$), and a full execution trace.

---

## 🛰️ Key Capabilities

| # | Capability | Mode | Description |
| :--- | :--- | :--- | :--- |
| **1** | **Single-Image RS-VQA** | Mode 1 | Visual Question Answering over high-resolution optical / multispectral imagery. |
| **2** | **RS-Captioning & Grounding** | Mode 1 | Descriptive scene summarization and text-guided bounding box region proposal. |
| **3** | **Bi-Temporal Change Detection** | Mode 3 | Siamese pixel-difference and region extraction between date $T_1$ and $T_2$. |
| **4** | **Change-Based VQA** | Mode 4 | Direct reasoned quantitative answers over detected changes with area in $\text{km}^2$. |
| **5** | **Cross-Modal Optical+SAR Fusion** | Mode 2 | Co-registered joint analysis fusing optical spectral reflection and SAR radar backscatter. |
| **6** | **GeoTIFF Coordinate Handling** | All | CRS extraction (`EPSG:4326`, `EPSG:3857`, UTM), affine transforms, and GeoJSON vectors. |
| **7** | **Auditable Execution Trace** | All | Zero hidden transcripts: structured steps, model IDs/versions, latencies, and confidences. |
| **8** | **Exportable Intelligence Reports** | All | One-click HTML and PDF intelligence report generator with map thumbnails and audit logs. |

---

## 🏛️ System Architecture

```
                             SATQUERY-X
                                  │
                         USER (Web UI / API)
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │   API GATEWAY (FastAPI) │  <- Auth, rate limit, validation
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │  INGESTION & VALIDATION │  <- GeoTIFF/PNG/JPEG parsing,
                     │  (rasterio/GDAL/Pillow) │     CRS extraction, mode detection
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │  QUERY UNDERSTANDER     │  <- Intent & entity extraction,
                     └────────────┬────────────┘     Mission Mode detection
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
                 │   EVIDENCE ENGINE        │ <- Overlays, masks, GeoJSON,
                 └────────────┬────────────┘    confidence aggregation, metric km²
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

## 🚀 Quickstart Guide

### Option 1: Run via Docker Compose (Recommended for Full Production Stack)

```bash
docker-compose -f infra/docker-compose.yml up --build
```

Services will be available at:
- **Web Dashboard**: `http://localhost:3000`
- **FastAPI Backend & Swagger**: `http://localhost:8000/docs`
- **MinIO Object Storage**: `http://localhost:9001`
- **PostgreSQL / PostGIS**: `localhost:5432`

---

### Option 2: Local Standalone Development

#### 1. Start the FastAPI Backend

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Launch backend server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Start the Next.js Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to interact with the mission control UI.

---

## 🧪 Running the Automated Test Suite

```bash
# Run all unit and integration tests across all 4 input modes
pytest backend/tests -v

# Run the benchmark evaluation suite
python training/scripts/evaluate_benchmarks.py --export-json docs/evaluation_results.json
```

---

## 📄 API Usage Example

```bash
# 1. Create analysis session
curl -X POST http://localhost:8000/v1/sessions

# 2. Upload bi-temporal image pair
curl -X POST http://localhost:8000/v1/sessions/{session_id}/images \
  -F "files=@pre_disaster.tif" \
  -F "files=@post_disaster.tif"

# 3. Submit question
curl -X POST http://localhost:8000/v1/sessions/{session_id}/query \
  -H "Content-Type: application/json" \
  -d '{"text": "Has built-up area increased between these two images?"}'
```

---

## 📚 Documentation Links
- [System Architecture Blueprint](docs/architecture.md)
- [REST API Specification](docs/api-spec.md)
- [Evaluation Plan & Benchmark Results](docs/evaluation-plan.md)
