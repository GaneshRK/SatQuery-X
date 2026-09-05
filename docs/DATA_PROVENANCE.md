# SatQuery-X — Data Provenance & Lineage Specification

## 1. Provenance Requirements
Every quantitative claim in an answer (e.g. area in hectares, change percentage, spectral index value) must trace back through an immutable audit trail:

```text
Claim in Answer
      ↓
EvidenceRegion record (Polygon geometry, area_km2, geodesic bounds)
      ↓
Measurement Dictionary (pixel counts, threshold, formula)
      ↓
Geospatial Tool (e.g. CHANGE_DETECTION, AREA_QUANTIFIER, SPECTRAL_INDEX)
      ↓
Processed Multi-Band Raster (resampled, cloud-masked, coregistered)
      ↓
Primary Satellite Scenes (STAC Item ID, Platform, Acquisition Timestamp, Sun Elevation)
      ↓
Earth Observation Provider (Copernicus Data Space Ecosystem / AWS Element84)
```

## 2. Sensor Profiles & Spectral Calibration
To prevent hardcoded band indices (e.g. assuming Band 4 is always Red), SatQuery-X employs strict `SensorProfile` mapping:
* **Sentinel-2 MSI (Level-2A):** 13 bands; B04 (Red, 665nm, 10m), B08 (NIR, 842nm, 10m), B11 (SWIR-1, 1610nm, 20m), B12 (SWIR-2, 2190nm, 20m).
* **Landsat 8/9 OLI/TIRS:** 11 bands; B4 (Red, 655nm, 30m), B5 (NIR, 865nm, 30m), B6 (SWIR-1, 1609nm, 30m).
* **ISRO Cartosat-2S:** Sub-meter Panchromatic (0.65m) + 4-band Multispectral (1.6m).
* **ISRO RISAT-1/1A:** C-band Synthetic Aperture Radar (SAR) with HH/HV dual polarization.

## 3. External Web Knowledge Provenance
External data (e.g. disaster management advisories, meteorological reports) are stored with:
* `source_url` & `source_domain`
* `publisher`
* `trust_tier` (GOVERNMENT, ACADEMIC, OFFICIAL_WEATHER, UNVERIFIED)
* `trust_score` (0.0 to 1.0)
* `content_hash` (SHA-256 for immutability)
* `ttl_expires_at` (strict cache lifecycle)
