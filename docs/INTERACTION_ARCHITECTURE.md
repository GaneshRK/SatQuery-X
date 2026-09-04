# SatQuery-X — Conversational Interaction Architecture

## 1. System Philosophy: "Chat with the Earth"
SatQuery-X transforms the human-in-the-loop remote sensing experience from a mechanical data processing pipeline into an intuitive conversation with an autonomous Earth Observation Analyst.

Users interact naturally without needing to know GIS jargon (NDVI, NDWI, B04, B08, CRS, GeoTIFF, EPSG, SAR backscatter). The system translates natural language queries into deterministic geospatial analyses and returns multi-layered, evidence-backed answers.

---

## 2. Multi-Turn Conversation State Schema

The conversation state is explicitly modeled as a structured JSON object maintained in `Session.conversation_context`:

```json
{
  "active_project": {
    "id": "proj-uuid",
    "name": "Chennai Coastal Monitoring"
  },
  "active_aoi": {
    "name": "Chennai Metropolitan Region",
    "bbox": [80.15, 12.95, 80.35, 13.15],
    "coords": [80.2707, 13.0827]
  },
  "active_scene": {
    "id": "S2A_MSIL2A_20231205",
    "sensor": "Sentinel-2",
    "date": "2023-12-05",
    "cloud_cover": 4.5
  },
  "active_region": {
    "type": "Polygon",
    "coordinates": [[[80.20, 13.00], [80.25, 13.00], [80.25, 13.05], [80.20, 13.05], [80.20, 13.00]]],
    "area_hectares": 1250.0,
    "label": "Ennore Inundation Zone"
  },
  "selected_dates": ["2020-01-01", "2023-12-31"],
  "selected_scenes": ["scene-1", "scene-2"],
  "active_analysis": {
    "mode": "BI_TEMPORAL",
    "task": "CHANGE_DETECTION",
    "layer": "change_mask"
  },
  "previous_questions": [
    "What is happening here?",
    "Focus on the construction.",
    "Were they there in 2019?"
  ],
  "previous_results": [
    {
      "summary": "Identified mixed urban-vegetation landscape with new built-up clusters.",
      "measurements": [{"metric": "Changed Area", "value": 18.2, "unit": "ha"}]
    }
  ],
  "user_intent": {
    "primary": "temporal_change_analysis",
    "target": "built_up"
  },
  "conversation_entities": [
    "Chennai Metropolitan Region",
    "Built-up clusters",
    "Ennore industrial corridor",
    "Vegetation canopy"
  ],
  "current_visual_state": {
    "center": [80.25, 13.05],
    "zoom": 11,
    "active_layer": "rgb"
  },
  "available_evidence": [
    {
      "type": "VECTOR_POLYGON",
      "count": 3
    }
  ]
}
```

---

## 3. UI Action Protocol
The GeoReason Agent generates validated UI actions executed directly by the map and viewport:

```json
{
  "actions": [
    {
      "type": "ZOOM_TO_REGION",
      "coordinates": [80.2707, 13.0827],
      "zoom": 13
    },
    {
      "type": "SHOW_LAYER",
      "layer": "change_mask"
    },
    {
      "type": "SET_TIMELINE",
      "date": "2020-01-01"
    },
    {
      "type": "HIGHLIGHT_FEATURE",
      "feature_id": "feature_0"
    }
  ]
}
```

---

## 4. Multi-Layer Answer Contract
Responses are delivered with calibrated layers of depth:
* **Layer 1: Direct Answer** — Concise, plain-English finding.
* **Layer 2: Ground Evidence** — Exact satellite overpasses and spectral indicators.
* **Layer 3: Quantitative Measurement** — Geodesic area in hectares/km² and delta percentage.
* **Layer 4: Calibrated Confidence** — Evidence-derived score and uncertainty boundary.
* **Layer 5: Actions & Next Steps** — Dynamic follow-up questions and layer toggles.
