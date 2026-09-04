# SatQuery AI — Database Architecture V2
## Global Earth Observation Temporal Intelligence Database

**Document Version:** 2.0  
**Status:** Architecture Specification & Migration Roadmap  
**Target Engine:** PostgreSQL 16+ with PostGIS 3.4+ (with SQLite spatial fallback for dev/demo)  

---

## 1. Executive Summary & Core Principle

SatQuery AI transitions from a single-session image upload tool into a **Global Earth Observation Temporal Intelligence Database**.

### The Fundamental Rule
**The database does NOT store the planetary archive of raw satellite files.**  
Instead, it operates a **hybrid catalogue**:
1. **Persistent Metadata & Spatial Footprints:** All discovered scenes, orbits, cloud covers, geometries, and temporal attributes are stored permanently in PostgreSQL/PostGIS.
2. **On-Demand Remote Assets:** High-resolution multi-band rasters remain in remote provider object storage (e.g., Copernicus Data Space Ecosystem, AWS, USGS) until explicitly requested.
3. **Smart Tiered Cache:** Active session rasters are cached locally (Hot/Warm) and automatically purged according to configurable lifecycle policies.
4. **Permanent Derived Intelligence:** Vectorized change events, spectral indices, calculated statistics, and AI evidence regions are persisted indefinitely.

---

## 2. Complete Entity-Relationship Hierarchy

```text
Organization (apps.accounts)
   │
   └── Project (apps.accounts)
         │
         ├── AreaOfInterest [AOI] (apps.satellite)
         │     │
         │     ├── TemporalObservation (apps.satellite)
         │     │     │
         │     │     └── SatelliteScene (apps.satellite)
         │     │           ├── SatelliteAsset (apps.satellite)
         │     │           └── DerivedRaster (apps.satellite)
         │     │
         │     ├── AOIMonitoring (apps.satellite)
         │     │
         │     └── ChangeEvent (apps.satellite)
         │           ├── before_scene (SatelliteScene)
         │           └── after_scene (SatelliteScene)
         │
         └── Session (apps.sessions)
               │
               ├── ImageAsset (apps.imagery - local/active raster)
               │
               └── Query (apps.queries)
                     ├── ExecutionStep (apps.queries)
                     ├── EvidenceRegion (apps.evidence)
                     └── Report (apps.reports)
```

---

## 3. Detailed Data Models

### 3.1. `DataProvider`
Manages external Earth Observation catalogue connections.
* `id`: UUID (PK)
* `name`: CharField (e.g., "Copernicus Data Space Ecosystem", "Microsoft Planetary Computer", "NASA Earthdata")
* `provider_type`: CharField ("STAC", "ODATA", "WMS", "S3")
* `base_url`: URLField (`https://stac.dataspace.copernicus.eu/v1/`)
* `authentication_type`: CharField ("OAUTH2", "API_KEY", "ANONYMOUS")
* `is_enabled`: BooleanField (default: True)
* `status`: CharField ("HEALTHY", "DEGRADED", "UNAVAILABLE")
* `last_health_check`: DateTimeField (null=True)
* `configuration`: JSONField (client_id, token_endpoint, auth headers)

### 3.2. `SatelliteCollection`
Catalogue grouping for satellite missions, sensors, and processing levels.
* `id`: UUID (PK)
* `provider`: ForeignKey(`DataProvider`)
* `collection_id`: CharField (e.g., `sentinel-2-l2a`, `sentinel-1-grd`, `landsat-c2-l2`)
* `name`: CharField (e.g., "Sentinel-2 MSI Level-2A BOA Reflectance")
* `mission`: CharField ("SENTINEL-2", "SENTINEL-1", "LANDSAT-8/9")
* `platform`: CharField ("Sentinel-2A", "Sentinel-2B", "Sentinel-1A")
* `instrument`: CharField ("MSI", "C-SAR")
* `spatial_resolution`: FloatField (meters, e.g. 10.0)
* `temporal_start`: DateField
* `temporal_end`: DateField (null=True)
* `status`: CharField ("ACTIVE", "DECOMMISSIONED")
* `metadata`: JSONField (spectral band definitions, wavelengths)

### 3.3. `SatelliteScene`
Granular remote-sensing acquisition record with spatial footprint and temporal stamp.
* `id`: UUID (PK)
* `provider`: ForeignKey(`DataProvider`)
* `collection`: ForeignKey(`SatelliteCollection`)
* `external_id`: CharField (STAC Item ID, e.g. `S2A_MSIL2A_20260815T043701_...`)
* `mission`: CharField ("SENTINEL-2")
* `platform`: CharField ("Sentinel-2A")
* `instrument`: CharField ("MSI")
* `acquisition_datetime`: DateTimeField (indexed)
* `processing_datetime`: DateTimeField
* `cloud_cover`: FloatField (null=True, optical only)
* `snow_cover`: FloatField (null=True)
* `resolution`: FloatField (meters)
* `product_level`: CharField ("L2A", "L1C", "GRD", "SLC")
* `orbit`: IntegerField (absolute orbit)
* `relative_orbit`: IntegerField
* `polarization`: CharField (e.g. "VV+VH", "HH+HV", null=True)
* `geometry`: JSONField (GeoJSON polygon footprint, indexed via PostGIS GiST)
* `bbox`: JSONField (`{west, south, east, north}`)
* `crs`: CharField (e.g., `EPSG:4326`, `EPSG:32646`)
* `status`: CharField ("INDEXED", "AVAILABLE", "QUEUED", "CACHED")
* `metadata`: JSONField (sun elevation, azimuth, tile ID)
* **Constraints:** `unique_together = ('provider', 'collection', 'external_id')`

### 3.4. `SatelliteAsset`
Downloadable band or asset constituent belonging to a `SatelliteScene`.
* `id`: UUID (PK)
* `scene`: ForeignKey(`SatelliteScene`, related_name='assets')
* `asset_key`: CharField (e.g., `B02`, `B03`, `B04`, `B08`, `B11`, `VV`, `VH`, `thumbnail`)
* `asset_type`: CharField ("BAND", "VISUAL", "THUMBNAIL", "METADATA", "MASK")
* `media_type`: CharField ("image/tiff; application=geotiff; profile=cloud-optimized", "image/png")
* `href`: URLField (remote access location)
* `size_bytes`: BigIntegerField (null=True)
* `checksum`: CharField (SHA-256 or MD5, null=True)
* `band_name`: CharField ("BLUE", "GREEN", "RED", "NIR", "SWIR1", "VV", "VH")
* `resolution`: FloatField (meters)
* `download_status`: CharField ("REMOTE", "QUEUED", "DOWNLOADING", "CACHED", "FAILED")
* `local_path`: CharField (relative path in media cache)
* `storage_uri`: CharField (S3/MinIO bucket path)

### 3.5. `AreaOfInterest` (AOI)
User-defined or system-registered geographic monitoring area.
* `id`: UUID (PK)
* `project`: ForeignKey(`Project`, null=True, blank=True)
* `user`: ForeignKey(`User`, on_delete=models.CASCADE)
* `name`: CharField (e.g., "Pollachi Agricultural District", "Kaziranga Wildlife Corridor")
* `geometry`: JSONField (GeoJSON Polygon/MultiPolygon, SRID 4326)
* `bbox`: JSONField (`{west, south, east, north}`)
* `area_km2`: FloatField
* `centroid`: JSONField (`[lng, lat]`)
* `created_at`: DateTimeField(auto_now_add=True)

### 3.6. `TemporalObservation`
Chronological link between an AOI and an intersecting `SatelliteScene`.
* `id`: UUID (PK)
* `aoi`: ForeignKey(`AreaOfInterest`, related_name='observations')
* `scene`: ForeignKey(`SatelliteScene`, related_name='aoi_observations')
* `observation_datetime`: DateTimeField
* `cloud_cover`: FloatField (null=True)
* `data_quality_score`: FloatField (0.0 to 100.0)
* `spatial_overlap_pct`: FloatField (intersection area / AOI area)
* `thumbnail_url`: CharField
* `status`: CharField ("CATALOGUE_ONLY", "PREVIEW_AVAILABLE", "CACHED", "ANALYZED")

### 3.7. `ChangeEvent`
Empirically detected and vectorized bi-temporal or multi-temporal ground change.
* `id`: UUID (PK)
* `aoi`: ForeignKey(`AreaOfInterest`, related_name='change_events')
* `before_scene`: ForeignKey(`SatelliteScene`, related_name='changes_as_before')
* `after_scene`: ForeignKey(`SatelliteScene`, related_name='changes_as_after')
* `change_type`: CharField ("URBAN_EXPANSION", "VEGETATION_LOSS", "VEGETATION_GAIN", "WATER_EXPANSION", "WATER_REDUCTION", "ROAD_DEVELOPMENT", "CONSTRUCTION", "LAND_CLEARING", "BURN_SCAR", "UNKNOWN")
* `geometry`: JSONField (GeoJSON MultiPolygon in EPSG:4326)
* `area_m2`: FloatField
* `area_km2`: FloatField
* `percentage_of_aoi`: FloatField
* `confidence`: FloatField (calibrated from sensor & algorithm agreement)
* `detection_method`: CharField (e.g., "Bi-temporal Differencing + Morphological Filtering")
* `model`: CharField
* `model_version`: CharField
* `created_at`: DateTimeField(auto_now_add=True)

### 3.8. `DerivedRaster`
Precomputed spectral index, calibrated SAR, or segmented mask to avoid redundant compute.
* `id`: UUID (PK)
* `source_scene`: ForeignKey(`SatelliteScene`, related_name='derived_rasters')
* `product_type`: CharField ("RGB", "FALSE_COLOR", "NDVI", "NDWI", "NDBI", "SAVI", "EVI", "CHANGE_MAP", "SEGMENTATION")
* `algorithm`: CharField
* `algorithm_version`: CharField
* `storage_uri`: CharField (path to GeoTIFF)
* `checksum`: CharField
* `crs`: CharField
* `resolution`: FloatField
* `bounds`: JSONField
* `statistics`: JSONField (`{min, max, mean, median, std, valid_pct}`)
* `created_at`: DateTimeField(auto_now_add=True)

### 3.9. `AOIMonitoring`
Automated recurrent surveillance subscription for a designated area.
* `id`: UUID (PK)
* `aoi`: ForeignKey(`AreaOfInterest`, related_name='monitoring_configs')
* `satellite_collection`: ForeignKey(`SatelliteCollection`)
* `monitoring_frequency`: CharField ("DAILY", "WEEKLY", "NEW_ACQUISITION")
* `max_cloud_cover`: FloatField (default: 20.0)
* `is_active`: BooleanField (default: True)
* `last_checked`: DateTimeField(null=True)
* `last_notified`: DateTimeField(null=True)

### 3.10. `DataSyncJob`
Audit log for catalogue indexer and synchronizer runs.
* `id`: UUID (PK)
* `provider`: ForeignKey(`DataProvider`)
* `started_at`: DateTimeField
* `finished_at`: DateTimeField(null=True)
* `status`: CharField ("RUNNING", "COMPLETED", "FAILED")
* `scenes_discovered`: IntegerField(default=0)
* `scenes_indexed`: IntegerField(default=0)
* `error_log`: TextField(blank=True, default="")

---

## 4. Indexing & Query Optimization Strategy

1. **Spatial Indexes:**
   * GiST spatial index on `SatelliteScene.geometry` and `AreaOfInterest.geometry`.
   * Fast bounding box overlap filtering using `ST_Intersects(scene.geom, aoi.geom)`.
2. **Temporal Indexes:**
   * B-Tree index on `SatelliteScene.acquisition_datetime`.
   * Composite index on `(collection, acquisition_datetime)` and `(provider, acquisition_datetime)`.
   * Composite index on `TemporalObservation(aoi, observation_datetime)`.
3. **Compound Filtering:**
   * Enables sub-millisecond retrieval of:
     *"Find all Sentinel-2 scenes intersecting AOI between 2018-01-01 and 2026-09-01 with cloud_cover < 10% sorted by acquisition date."*

---

## 5. Non-Destructive Migration Plan

* **No Data Loss:** All existing tables (`accounts_organization`, `accounts_project`, `analysis_sessions_session`, `imagery_imageasset`, `queries_query`, `evidence_evidenceregion`, `reports_report`) remain 100% active and untouched.
* **Compatibility Layer:** Existing `AcquisitionRequest` and `AcquisitionCandidate` models continue to function as transient UI search wrappers, seamlessly linking to `SatelliteScene` records.
* **Unified Foreign Keys:** New models plug cleanly into `accounts.Project`, `accounts.User`, and `analysis_sessions.Session`.
