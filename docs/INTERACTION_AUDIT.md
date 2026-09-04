# SatQuery-X — Interaction & Conversational Architecture Audit

## 1. Executive Summary
This document provides a comprehensive audit of the human–AI interaction model in **SatQuery-X** prior to the Conversational Earth Analyst upgrade. It examines user flow, query processing, multi-turn state retention, visual grounding, and API interaction paradigms.

---

## 2. Interaction Gap Analysis

| Capability | Current State | Target Conversational State |
| :--- | :--- | :--- |
| **Interaction Paradigm** | Query $\to$ Classifier $\to$ Tool $\to$ Static Result | Dynamic, multi-turn dialogue with continuous context memory |
| **Terminology Burden** | User must understand GIS terms (AOI, NDWI, NDVI, CRS, SAR) | "Chat with the Earth" in plain natural language; automatic technical translation |
| **Pronoun & Reference Resolution** | "Focus on the construction" or "Were they there before?" fails | Context engine resolves "they", "this area", "here" from past conversational turns |
| **Ambiguity Handling** | System guesses or defaults without asking | Asks minimal smart clarification (e.g. "Is this place growing?" $\to$ urban vs vegetation vs water) |
| **Visual Interaction** | View map, manually upload images, submit text query | **Point-and-Ask**, **Draw-and-Ask**, **Hover Intelligence**, **Click-to-Explain** |
| **Natural Language UI Control** | UI only controlled via clicks on dropdowns/toggles | Commands like *"Show vegetation"*, *"Zoom into changes"*, *"Show 2020"* control map live |
| **Context Awareness** | Session stores last 10 query/answer strings | Explicit `conversation_context` object tracking active AOI, entities, dates, visual state |
| **Explanation Modes** | Fixed single-length narrative | Adaptive Simple Mode (plain English) vs Expert Mode (spectral bands, CRS, thresholds) |
| **Input Modalities** | Text input only | Text input + Browser Web Speech voice input + Direct map clicking/drawing |

---

## 3. Current Query Flow vs Target Query Flow

### Current Query Flow
```
User Types Text 
  ▼
SessionQueryListCreateView (Validates image/pair, creates Query)
  ▼
run_query_task (Celery async / Sync fallback)
  ▼
execute_plan:
  - Understander classifies intent
  - Planner creates tool steps
  - Executor runs CV/Rasterio steps
  - GeoReason synthesizes static answer
  - Appends query/answer pair to session.conversation_history
```

### Target Conversational Flow
```
User Speaks, Types, or Clicks Map
  ▼
Context Engine:
  - Ingests visual state (viewport, active polygon, active layer)
  - Loads multi-turn conversation context from Session
  ▼
Query Optimizer & Reference Resolver:
  - Resolves pronouns and references ("they", "here", "the construction")
  - Detects ambiguities; if high, emits CLARIFICATION_REQUIRED with interactive options
  - Translates natural questions into deterministic Earth observation pipelines
  ▼
Planner Agent & Executor:
  - Reuses existing satellite overpasses and spectral measurements when relevant
  - Retrieves additional historical/temporal scenes automatically if queried
  - Synthesizes findings using GeoReasonAgent & Calibrated Confidence Engine
  ▼
Answer Composer:
  - Emits multi-layered response (Direct answer, Evidence, Measurement, Confidence, Uncertainty)
  - Emits structured UI actions (ZOOM_TO_REGION, SHOW_LAYER, SET_TIMELINE)
  - Emits 4 context-relevant follow-up inquiry pills
  ▼
Conversational UI:
  - Executes UI actions on MapLibre map
  - Renders interactive follow-up chips
  - Updates ContextBar live
```

---

## 4. Architectural Rules for the Upgrade
1. **Preserve Existing Backend & API Stability**: All existing REST routes, serializers, models, and tests remain intact.
2. **Deterministic Computation First**: Spectral indices (NDVI, NDWI, NDBI), polygonization, and area quantification remain 100% deterministic via Rasterio and GDAL.
3. **No Fabricated Data**: If an observation does not exist for an exact date, the system communicates the closest available observation honestly.
4. **Untrusted External Content**: Web-augmented research remains treated as evidence data, protected by SSRF guards and SHA-256 content hashing.
