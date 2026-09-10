# Stage 9 — Agentic Satellite Retrieval → Analysis

Stage 9 connects real satellite catalogue retrieval to downstream analysis.

## Flow

1. Query understanding resolves the requested task, AOI/location, sensor and time range.
2. Planner creates `search_satellite_imagery` using only explicit constraints.
3. For analysis requests without uploaded imagery, planner adds `acquire_satellite_imagery`.
4. Acquisition selects real catalogue observation(s), persists scene/asset provenance, downloads the provider asset, validates raster geospatial metadata, and attaches the resulting `ImageAsset` record to the active query.
5. Executor refreshes its live imagery context after acquisition.
6. Existing specialist models then consume the downloaded imagery.
7. Existing evidence validation/answer composition persists the execution trace.

## Scientific integrity

- Catalogue metadata is never treated as image evidence.
- No synthetic imagery is generated.
- No arbitrary date is invented for `latest` requests.
- A failed download remains a failed acquisition rather than a model fallback to fake data.
- Bi-temporal acquisition selects two distinct real catalogue observations when at least two are available in the requested search result set; downstream change validation remains responsible for spatial/temporal consistency.

## Runtime configuration

The provider is currently Copernicus Data Space Ecosystem through the existing CDSE configuration. Credentials must be configured according to the existing satellite provider documentation.

## Example conceptual query

`Analyze the latest Sentinel-2 image for this AOI and identify water.`

The resulting plan is conceptually:

`SATELLITE SEARCH → REAL ASSET ACQUISITION → GEO VALIDATION → SPECIALIST ANALYSIS → EVIDENCE VALIDATION → ANSWER`

The actual observation date, scene identifier, asset URL, checksum, CRS and raster properties come from the provider/downloaded file.
