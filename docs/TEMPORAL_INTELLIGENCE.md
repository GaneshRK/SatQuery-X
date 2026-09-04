# SatQuery-X Temporal Intelligence Engine Specification

**Platform**: SatQuery AI — Multi-Decadal Earth Observation Intelligence  
**Specification Version**: 2.0  
**Status**: Approved Architecture  

---

## 1. Vision & Core Principles

The SatQuery-X Temporal Intelligence Engine transforms Earth observation from a single snapshot into an interactive 4D spacetime exploration:

```
2015 ──── 2017 ──── 2019 ──── 2021 ──── 2023 ──── 2026
                     ▲
             Detected Event
```

### Core Integrity Principles:
1. **Never Fabricate Observations**: Observations represent real physical overpasses catalogued by Sentinel-1 or Sentinel-2. If cloud cover or orbital revisit created a gap, the timeline explicitly notes: *"No cloud-free observation available."*
2. **Never Interpolate Imagery**: Pixels represent measured top-of-atmosphere or bottom-of-atmosphere reflectance/backscatter, never AI-hallucinated transitions.
3. **Temporal Quality Scoring**: Each observation is assigned a deterministic quality metric derived from cloud percentage, sensor resolution, and orbital geometry.

---

## 2. Chronological Observation Hierarchy

For every Area of Interest (AOI), the engine builds a persistent, indexed multi-year timeline:

- `EARLIEST AVAILABLE`: First verified cloud-free satellite acquisition over the target AOI (e.g. 2016-03-12).
- `LATEST AVAILABLE`: Most recent observation synchronized via near-real-time catalogue polling.
- `CADENCE SLICES`:
  - **Acquisition-Based**: Granular overpass list (5-day Sentinel-2 revisit).
  - **Seasonal / Annual**: Preferred baseline scenes selected for minimal cloud cover (<15%) and consistent sun angles.
- `GAP IDENTIFICATION`: Documented list of years/months lacking valid imagery, displayed transparently to the user.

---

## 3. Earth History Interaction Modes

### 3.1 Time-Lapse Playback
- Stepping through observations sequentially across the timeline track (`[Prev]`, `[Play/Pause]`, `[Next]`).
- Configurable playback speeds (`0.5x` = 2000ms, `1.0x` = 1200ms, `2.0x` = 600ms).
- Immediate raster texture update on the WebGL globe / 2D GIS canvas without full-page reloads.

### 3.2 Before / After Mode
- Side-by-side or split-screen comparison of two specific temporal milestones (e.g., *2018 Pre-Development* vs *2026 Post-Development*).
- Synchronized pan/zoom viewport keeping identical ground footprints aligned.
- Opacity slider and swipe comparison bar.

### 3.3 Multi-Temporal Change Detection
- Bi-temporal change analysis comparing Scene A (baseline) and Scene B (target).
- Generates categorized `ChangeEvent` records:
  - `URBAN_EXPANSION`
  - `VEGETATION_LOSS` / `VEGETATION_GAIN`
  - `WATER_EXPANSION` / `WATER_REDUCTION`
  - `CONSTRUCTION` / `ROAD_DEVELOPMENT`
  - `BURN_SCAR` / `FLOOD_EXTENT`
- Outputs vector polygons in GeoJSON format, metric area in hectares, and percentage of AOI affected.

---

## 4. Natural Language Temporal Resolution

The Query Optimizer translates conversational temporal phrases into precise ISO date ranges:

| User Natural Language | Resolved Start Date | Resolved End Date | Sensor Preference |
| :--- | :--- | :--- | :--- |
| *"What was this place like 5 years ago?"* | `now - 5 years - 30d` | `now - 5 years + 30d` | Sentinel-2 Optical |
| *"Compare 2018 and 2026"* | `2018-01-01` | `2026-12-31` | Sentinel-2 L2A |
| *"Show the earliest image"* | `2015-06-23` (Mission start) | Earliest valid overpass | Sentinel-2 / 1 |
| *"What changed recently?"* | `now - 90 days` | `now` | Sentinel-1/2 |
| *"Did flooding happen during the monsoon?"* | July 1 (target year) | September 30 | Sentinel-1 SAR (all-weather) |

---

## 5. API Endpoints

- `GET /api/v1/satellite/aoi/<id>/timeline/`: Returns full chronological observation metadata, quality scores, earliest/latest markers, and documented gaps.
- `POST /api/v1/satellite/change-analysis/`: Executes bi-temporal differencing between two scenes or date targets, returning vector change polygons and confidence.
- `GET /api/v1/satellite/change-events/`: Global change event catalogue for planetary exploration.
