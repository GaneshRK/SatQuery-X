# SatQuery-X External Services & Providers

## 1. Required Services

| Service | Purpose | Credentials | Fallback Strategy |
| :--- | :--- | :--- | :--- |
| **Copernicus Data Space (CDSE)** | Live Sentinel-1 & Sentinel-2 STAC catalogue search & product downloads | `CDSE_USERNAME`, `CDSE_PASSWORD`, `CDSE_CLIENT_ID` | Automatically falls back to `MockSatelliteProvider` with transparent `demo_data` labeling if unconfigured or offline |
| **PostgreSQL / PostGIS** | Spatial database, GiST indexing, footprints, change polygons, AOI intersections | `DATABASE_URL` | SQLite spatial fallback for development/demo |
| **Redis** | Celery task broker, results cache, and real-time SSE pub/sub | `REDIS_URL`, `CELERY_BROKER_URL` | Synchronous execution fallback in development |

---

## 2. Optional Enhancement Services

| Service | Purpose | Credentials | Fallback Strategy |
| :--- | :--- | :--- | :--- |
| **OpenAI** | Advanced natural-language planning & multimodal VLM reasoning | `OPENAI_API_KEY`, `OPENAI_MODEL` | Falls back to `LocalProvider` deterministic spatial computer vision |
| **Hugging Face** | Remote inference for specialized remote sensing models | `HF_TOKEN` | Local baseline inference models |
| **MapTiler** | Vector basemaps and high-resolution globe tiles | `MAPTILER_API_KEY` | Public Esri World Imagery, Carto Dark Matter, and OpenStreetMap tiles |
| **MinIO / AWS S3** | Production object storage for multi-band rasters and COGs | `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | Local filesystem storage under `MEDIA_ROOT` |
| **Sentry** | Production application performance & error monitoring | `SENTRY_DSN` | Standard Django structured file logging |
