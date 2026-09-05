# SatQuery-X — Final System Architecture (v2.5 Production)

## 1. Architectural Topology

```text
                                  +---------------------------------------+
                                  |     User Natural Language Query       |
                                  | (Text / Voice / Georeferenced Image)  |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |   Next.js 14 Web GIS Workstation      |
                                  |  - MapLibre GL (2D GIS Overlay)       |
                                  |  - CesiumJS (3D Orbital Globe)        |
                                  |  - Interactive AOI & Evidence Inspect |
                                  +-------------------+-------------------+
                                                      |
                                                      | HTTP / SSE / REST
                                                      v
                                  +---------------------------------------+
                                  |   Django 5.1 REST Framework Backend   |
                                  |  - JWT / Session Authentication       |
                                  |  - Tenant & Workspace RBAC            |
                                  |  - Query Lifecycle State Machine      |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |         Master Orchestrator           |
                                  |        (apps.agent.executor)          |
                                  +-------------------+-------------------+
                                                      |
         +--------------------+-----------------------+------------------------+--------------------+
         |                    |                       |                        |                    |
         v                    v                       v                        v                    v
+-----------------+  +-----------------+   +---------------------+   +-------------------+  +------------------+
| QueryOptimizer  |  | STAC Provider   |   | Preprocessing & CV  |   | AI Model Adapters |  | WebResearchAgent |
| (NL Intent &    |  | (Copernicus     |   | - Rasterio          |   | - RemoteCLIP      |  | - Authoritative  |
|  Location BBox) |  |  CDSE / AWS)    |   | - NDVI/NDWI/NDBI    |   | - RSVQA           |  |   Government /   |
|                 |  | - Sentinel-1/2  |   | - Geodesic Math     |   | - ChangeFormer    |  |   Weather Data   |
+-----------------+  +-----------------+   +---------------------+   +-------------------+  +------------------+
         |                    |                       |                        |                    |
         +--------------------+-----------------------+------------------------+--------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |            GeoReasonAgent             |
                                  | - Multi-Factor Confidence Calibration |
                                  | - Non-Hallucinatory Synthesis         |
                                  | - Evidence Region Graph Generation    |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |         Data & Persistence            |
                                  | - PostgreSQL 16 + PostGIS             |
                                  | - Redis 7 (Pub/Sub & Cache)           |
                                  | - MinIO / S3 (Cloud-Optimized Rasters)|
                                  +---------------------------------------+
```

## 2. Core Execution Principles
1. **Zero Hallucination:** No metrics, bounding boxes, or dates are synthesized out of thin air. If imagery is absent, the system halts with `SATELLITE_DATA_UNAVAILABLE`.
2. **First-Class Natural Language:** Users can type place names, coordinates, or spatial queries without being forced to upload rasters or pick predefined demo scenarios.
3. **Evidence-Backed Answers:** All statements reference verifiable pixel statistics, geodesic polygon boundaries, sensor profiles, or authoritative citations.
