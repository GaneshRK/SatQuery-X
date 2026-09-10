# Stage 8 — Real Satellite Asset Ingestion

Stage 8 closes the gap between **catalogue discovery** and **actual raster data**.

The provider layer already searches the real Copernicus Data Space Ecosystem.
This stage adds a durable download/validation path for a selected STAC asset.

## Guarantees

- Provider URLs are used as supplied by the catalogue.
- No fake scene or raster is created.
- Download success is verified by checking the local file and byte count.
- Every downloaded file receives a SHA-256 checksum.
- Geospatial raster assets are opened with Rasterio.
- Missing CRS or affine transform causes validation failure.
- Provider failures are returned as explicit task failures.

## Task

```text
apps.satellite.tasks.download_satellite_asset_task(asset_id)
```

The task updates `SatelliteAsset.local_path`, `is_downloaded`, `byte_size`,
and `checksum`, and records validation/provenance metadata.

## Scientific data flow

```text
AOI + dates + sensor
        ↓
Copernicus STAC search
        ↓
real SatelliteScene
        ↓
real SatelliteAsset / provider href
        ↓
authenticated provider download
        ↓
local bytes
        ↓
SHA-256 + Rasterio validation
        ↓
analysis-ready asset
```

This is distinct from catalogue indexing: a catalogue record alone is not
imagery evidence.
