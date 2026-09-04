# SatQuery-X Architecture V2: Earth-from-Orbit & Temporal Intelligence Platform

## 1. System Overview

SatQuery-X transforms raw Earth Observation (EO) satellite streams into actionable, explainable geospatial intelligence. Moving beyond conventional flat street-map paradigms, SatQuery-X delivers an orbital-first experience:
```text
SATELLITE / ORBIT
      ↓
3D EARTH (WebGL Globe)
      ↓
ZOOM THROUGH SPACE (Orbital Camera Hierarchy)
      ↓
CONTINENT / COUNTRY / REGION
      ↓
AREA OF INTEREST (AOI)
      ↓
REAL SATELLITE OBSERVATION (Sentinel-1 / Sentinel-2 / Cartosat)
      ↓
TEMPORAL HISTORY ARCHIVE (2015 → 2026)
      ↓
MULTI-STAGE CHANGE DETECTION
      ↓
AI MULTIMODAL REASONING (Evidence-First VLM / LLM)
      ↓
REPORT & EXPORT DOSSIER
```

---

## 2. Core Architectural Principles

1. **Earth Observation First:** The primary visual canvas is authentic satellite observations and a 3D Earth from orbit. Road maps, borders, and place names exist strictly as secondary annotations.
2. **Hybrid Spatial Database:** PostgreSQL/PostGIS stores persistent metadata, footprints, orbits, temporal observations, and derived vector masks. Massive raw satellite rasters reside in remote provider storage (CDSE STAC) and are fetched on-demand into a tiered local cache.
3. **Deterministic Remote Sensing Engine:** Area measurements, spectral index calculations (NDVI, NDWI, NDBI, SAVI, EVI), and Otsu binarization are computed deterministically with Rasterio/GDAL/NumPy/Shapely—never approximated by an LLM.
4. **Evidence-First AI Contract:** Every AI response satisfies a standardized 10-key contract with traceable provenance, data quality scoring, and explicit limitations.

---

## 3. High-Level Subsystems

```text
                                SATQUERY-X V2
                                      │
                      ┌───────────────┴───────────────┐
                      ▼                               ▼
            Frontend (Next.js 14)           Backend (Django REST 5.1)
            - 3D WebGL Globe                 - DataProvider & STAC Client
            - Orbital Camera Engine          - Unified RasterEngine
            - Timeline Slider & Playback     - ModelRouter & ToolRegistry
            - Dynamic Raster Tiles           - Celery NRT Synchronizer
            - Evidence Drawer                - PostGIS Spatial Archive
                      │                               │
                      └───────────────┬───────────────┘
                                      ▼
                        Storage & Infrastructure
                        - PostgreSQL / PostGIS 16+
                        - Redis 7+ (Broker & Cache)
                        - Local Media / S3 / MinIO
                        - Live Copernicus Data Space Ecosystem (CDSE)
```

---

## 4. Camera Hierarchy & Transition Engine

```text
Level 0: Space / Orbit (Altitude > 10,000 km, Pitch 0-45°, 3D Globe with Atmosphere)
   ↓
Level 1: Continent (Altitude 3,000 - 8,000 km)
   ↓
Level 2: Country / State (Altitude 800 - 2,500 km)
   ↓
Level 3: District / City (Altitude 100 - 600 km)
   ↓
Level 4: AOI Envelope (Altitude 10 - 80 km)
   ↓
Level 5: High-Resolution Satellite Raster (10m Sentinel-2 / SAR Backscatter)
```

Transitions use sinusoidal easing with pitch adjustments to create a cinematic descent from orbit to the target observation site.
