# SatQuery AI — Temporal Intelligence & Earth Observation Engine Architecture

**Document Version:** 2.0  
**Domain:** Temporal Earth Observation, Bi-Temporal Change Detection, & Multi-Decadal Time Series  

---

## 1. Vision: "Earth Change Explorer"

SatQuery AI elevates geospatial intelligence from static snapshots to **multi-temporal continuous observation**.
The user should seamlessly transition through time:
```text
Select AOI (e.g. Pollachi / Kaziranga / Sundarbans)
      ↓
Query Historical Archive (2015 → 2026)
      ↓
Timeline Browser & Time-Lapse View
      ↓
Compare T1 & T2 ("What Changed?")
      ↓
Multi-Stage Change Detection Pipeline
      ↓
Vectorized Ground Truth Change Polygons & Metric Areas
      ↓
AI Reasoning & Explanation
```

---

## 2. Near-Real-Time Catalogue Synchronization Engine

### Honest Synchronization Definition
"Real-time" in remote sensing never means live 24/7 video streaming from space. Rather, it means:
1. **Near-Real-Time (NRT) Catalogue Indexing:** Polling external provider STAC endpoints (CDSE) every 15–60 minutes to discover new satellite overpasses as soon as ESA or Copernicus publishes them.
2. **Latest Available Observation:** Querying the database for the freshest observation with valid cloud metrics.
3. **Transparent Synchronization Timestamps:** Exposing:
   * `acquisition_datetime`: exact UTC moment the sensor captured the ground.
   * `processing_datetime`: generation of L2A BOA / GRD product.
   * `indexed_at`: timestamp SatQuery AI catalogued the scene.

### Sync Architecture:
```text
[Celery Beat Scheduler]
         │ (every 30 mins)
         ▼
[RealtimeCatalogueSynchronizer]
         │
         ├── Fetch Last Watermark (last_seen_acquisition)
         │
         ├── STAC Search: datetime = [last_seen .. NOW]
         │
         ├── Filter: Target Monitoring AOIs or Global Bounding Envelopes
         │
         ├── Deduplicate: (provider, collection, external_id)
         │
         ├── Extract: Geometry, Cloud Cover, Platform, Assets Summary
         │
         └── Bulk Upsert: SatelliteScene & SatelliteAsset records
```

---

## 3. Multi-Stage Change Detection Pipeline

Change detection must never be a naive raw pixel subtraction. It executes through an 11-stage rigorous remote sensing pipeline:

```text
1. Scene Selection: T1 (Baseline) and T2 (Current) with minimal cloud cover.
         ↓
2. CRS Harmonization: Ensure identical EPSG projected coordinate reference system.
         ↓
3. Coregistration & Grid Alignment: Spatial sub-pixel alignment using affine transforms.
         ↓
4. Cloud & Shadow Masking: Exclude pixels where SCL (Scene Classification Layer) flags clouds.
         ↓
5. Radiometric Normalization: Harmonize BOA reflectance distributions across dates.
         ↓
6. Differencing Math:
      Optical: ΔNDVI = NDVI(T2) - NDVI(T1), ΔNDWI = NDWI(T2) - NDWI(T1)
      SAR: ΔBackscatter = 10 * log10(σ0_T2 / σ0_T1)
         ↓
7. Adaptive Binarization: Otsu's optimal thresholding on difference magnitude.
         ↓
8. Morphological Cleanup: Binary opening (remove salt noise) & closing (fill holes).
         ↓
9. Connected Component Polygonization: Vectorize contiguous pixel clusters into GeoJSON.
         ↓
10. Metric Area Quantification: Project into local Cylindrical Equal Area (CEA) for true ground m²/ha/km².
         ↓
11. AI Causal Interpretation: Classify change into categories:
      - URBAN_EXPANSION
      - VEGETATION_LOSS
      - VEGETATION_GAIN
      - WATER_EXPANSION
      - WATER_REDUCTION
      - ROAD_DEVELOPMENT
```

---

## 4. Frontend Temporal Navigation & Exploration

### 4.1. Timeline Slider & Keyframe Indicators
* A chronological bar at the bottom of the map displaying dots for every observation date from 2015 to 2026.
* Color-coded by sensor: Sentinel-2 (Green/Cyan), Sentinel-1 (Violet).
* Hovering displays scene thumbnail, acquisition date, and cloud cover percentage.

### 4.2. Time-Lapse Player
* Controls: `[⏮ Prev] [▶ Play / ⏸ Pause] [⏭ Next]` with speed multiplier (`0.5x`, `1x`, `2x`).
* Automatically cycles through historical observations, updating the WebGL raster canvas smoothly.

### 4.3. "What Changed?" Quick Action
* Selecting two timeline dates triggers the bi-temporal change pipeline automatically.
* Highlights change polygons on the map and delivers the 10-key Answer Contract in the AI console.

---

## 5. Continuous AOI Monitoring Engine

* Users can subscribe an AOI to **Continuous Monitoring**.
* When `RealtimeCatalogueSynchronizer` discovers a new scene covering the AOI with cloud cover below the threshold, it:
  1. Creates a new `TemporalObservation`.
  2. Compares against the baseline scene.
  3. If change magnitude exceeds the trigger threshold (e.g. >5% vegetation loss), creates a `ChangeEvent`.
  4. Dispatches an alert via the UI notification stream.
