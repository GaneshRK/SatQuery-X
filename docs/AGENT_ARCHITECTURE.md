# SatQuery-X Multi-Agent Architecture Specification

**Platform**: SatQuery AI — Agentic Earth Observation Intelligence Platform  
**Specification Version**: 2.0  
**Status**: Approved Architecture  

---

## 1. System Overview

SatQuery-X orchestrates a collaborative multi-agent architecture designed to transform natural language questions about Earth into auditable, scientifically grounded remote-sensing intelligence.

```
                    USER
                      │
                      ▼
              Natural Language Query
                      │
                      ▼
              ┌─────────────────┐
              │ Query Optimizer │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Planner Agent  │
              └────────┬────────┘
                       │
            ┌──────────┼──────────┐
            │          │          │
            ▼          ▼          ▼
        Satellite    Web       Conversation
        Retrieval    Agent       Memory
            │          │          │
            └──────────┼──────────┘
                       ▼
              ┌─────────────────┐
              │    GIS Agent    │
              └────────┬────────┘
                       │
              ┌────────┼─────────┐
              ▼        ▼         ▼
             VLM     Change     Detection
            Agent    Agent       Agent
              │        │         │
              └────────┼─────────┘
                       ▼
              ┌─────────────────┐
              │ GeoReason Agent │
              └────────┬────────┘
                       │
              ┌─────────────────┐
              │  Verification   │
              │  + Confidence   │
              └────────┬────────┘
                       │
              ┌─────────────────┐
              │ Answer Generator│
              └────────┬────────┘
                       ▼
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     Visual UI      Evidence       Report
```

---

## 2. Agent Catalog & Responsibilities

### 2.1 Query Optimizer Agent (`QueryOptimizer`)
- **Input**: Raw conversational user text + session context + active AOI.
- **Responsibilities**:
  - Normalize spatial references ("Chennai", "this lake", "surrounding forest").
  - Resolve temporal phrases ("between 2018 and 2026", "5 years ago", "since 2020", "recently", "earliest available") into ISO date ranges.
  - Classify intent into one of 17 standard remote-sensing tasks.
  - Determine whether external web knowledge is required (`external_evidence_required: bool`).
  - Output structured JSON plan conforming to schema.

### 2.2 Planner Agent (`PlannerAgent`)
- **Input**: Structured plan from Query Optimizer.
- **Responsibilities**:
  - Formulate dependency graph and tool execution sequence.
  - Select sensor modality (Optical Sentinel-2 for vegetation/urban, SAR Sentinel-1 for all-weather flood/structure).
  - Dispatch concurrent sub-tasks (e.g. satellite scene search + parallel weather/web context retrieval).

### 2.3 Satellite Retrieval Agent (`SatelliteRetrievalAgent`)
- **Responsibilities**:
  - Search Copernicus CDSE STAC v1 catalogue for matching scenes.
  - Rank candidates by spatial intersection, cloud coverage, and radiometric quality.
  - Stream or reference assets via COG / windowed reads without downloading entire planetary datasets.

### 2.4 GIS Agent (`GISAgent`)
- **Responsibilities**:
  - CRS normalization and reprojection (`EPSG:4326` <-> UTM).
  - Windowed raster clipping to exact AOI bounds.
  - Metric surface area and zonal statistics calculation using projection-aware math.

### 2.5 Computer Vision & VLM Agent (`VLMAgent`)
- **Responsibilities**:
  - Visual Question Answering (VQA) and multimodal scene description.
  - Semantic landcover segmentation and building/road structure detection.
  - Multi-spectral and SAR feature interpretation.

### 2.6 Change Detection Agent (`ChangeDetectionAgent`)
- **Responsibilities**:
  - Bi-temporal image differencing and spectral index deltas (NDVI, NDWI, NDBI).
  - Radiometric normalization and cloud/shadow masking.
  - Connected component polygonization and change event classification (`URBAN_EXPANSION`, `VEGETATION_LOSS`, `WATER_EXPANSION`, etc.).

### 2.7 Web Research Agent (`WebResearchAgent`)
- **Responsibilities**:
  - Automatically triggered when external contextual information is needed.
  - SSRF-guarded retrieval from verified domain trust tiers (Tier 1 Gov/Agency, Tier 2 Academic, Tier 3 Trusted News).
  - Extracts atomic factual evidence with content hashes and TTL-based caching.
  - Treats external text as DATA, not executable instructions.

### 2.8 GeoReason Agent (`GeoReasonAgent`)
- **Responsibilities**:
  - Unified synthesis of satellite findings, GIS measurements, temporal deltas, and external evidence.
  - Validates cross-source consistency; detects conflicts or unverified claims.
  - Strict honesty enforcement: never fabricates measurements or dates.

### 2.9 Confidence Engine (`ConfidenceEngine`)
- **Responsibilities**:
  - Calculates calibrated scientific confidence based on measurable factors:
    `Confidence = w_sensor * S_res + w_cloud * (1 - Cloud) + w_reg * R_qual + w_algo * A_score + w_ext * E_trust`
  - Explains confidence drivers and documents remaining uncertainties.

### 2.10 Evidence & Provenance Agent (`EvidenceAgent`)
- **Responsibilities**:
  - Generates immutable spatial GeoJSON features and external citation nodes.
  - Emits full provenance metadata (satellite mission, acquisition date, algorithm, model version, CRS).

### 2.11 Follow-Up Question Generator (`FollowUpGenerator`)
- **Responsibilities**:
  - Analyzes the final answer and executed intelligence graph to propose 3–5 contextually relevant next queries.

---

## 3. Tool Permission Model

| Tool Name | Authorized Agents | Input Schema | Output Schema |
| :--- | :--- | :--- | :--- |
| `search_satellite_catalogue` | Satellite Agent, Planner | AOI, Date Range, Sensor, Max Cloud | Candidate Scene List |
| `calculate_ndvi` | GIS Agent, Change Agent | NIR & Red Arrays | NDVI Array, Mean, Coverage % |
| `calculate_ndwi` | GIS Agent, Change Agent | Green & NIR Arrays | NDWI Array, Mean, Water % |
| `calculate_ndbi` | GIS Agent, Change Agent | SWIR & NIR Arrays | NDBI Array, Built-up % |
| `detect_change` | Change Agent | Scene A, Scene B, Threshold | Change Polygons, Area ha, Class |
| `search_web` | Web Research Agent | Query, Domain Tier, Max Results | Extracted Facts, Source URLs, Hashes |
| `verify_evidence` | GeoReason Agent | Fact List, Satellite Measurements | Verification Matrix, Conflict Flags |
| `generate_report` | Report Agent | Query Trace, Evidence, Charts | PDF / HTML Intelligence Report |

---

## 4. Structured Query Plan Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SatQueryExecutionPlan",
  "type": "object",
  "required": ["intent", "aoi", "time_range", "modalities", "analysis", "external_evidence_required"],
  "properties": {
    "intent": { "type": "string" },
    "aoi": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "bbox": { "type": "array", "items": { "type": "number" }, "minItems": 4, "maxItems": 4 },
        "geometry": { "type": "object" }
      }
    },
    "time_range": {
      "type": "object",
      "required": ["start", "end"],
      "properties": {
        "start": { "type": "string", "format": "date" },
        "end": { "type": "string", "format": "date" }
      }
    },
    "modalities": {
      "type": "array",
      "items": { "type": "string", "enum": ["optical", "sar", "cross_modal"] }
    },
    "analysis": {
      "type": "array",
      "items": { "type": "string" }
    },
    "external_evidence_required": { "type": "boolean" },
    "external_query": { "type": "string" }
  }
}
```
