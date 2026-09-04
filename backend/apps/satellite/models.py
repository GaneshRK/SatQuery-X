import uuid
from django.db import models
from django.utils import timezone


class AcquisitionRequest(models.Model):
    SENSOR_CHOICES = [
        ("SENTINEL-1", "Sentinel-1 (SAR)"),
        ("SENTINEL-2", "Sentinel-2 (Optical L2A)"),
        ("BOTH", "Both (Optical + SAR)"),
    ]
    STATUS_CHOICES = [
        ("SEARCHING", "Searching"),
        ("RESULTS_READY", "Results Ready"),
        ("RETRIEVING", "Retrieving"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="satellite_requests"
    )
    aoi_geometry = models.JSONField()
    sensor = models.CharField(max_length=32, choices=SENSOR_CHOICES, default="SENTINEL-2")
    date_start = models.DateField()
    date_end = models.DateField()
    max_cloud_cover = models.FloatField(null=True, blank=True, default=20.0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="SEARCHING")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AcquisitionRequest {self.id} ({self.sensor}): {self.status}"


class AcquisitionCandidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        AcquisitionRequest, on_delete=models.CASCADE, related_name="candidates"
    )
    stac_item_id = models.CharField(max_length=255)
    collection = models.CharField(max_length=128)
    acquisition_date = models.DateField()
    cloud_cover_pct = models.FloatField(null=True, blank=True)
    footprint_geom = models.JSONField()
    selected = models.BooleanField(default=False)
    retrieved_image = models.ForeignKey(
        "imagery.ImageAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="from_candidate"
    )

    class Meta:
        ordering = ["cloud_cover_pct", "-acquisition_date"]

    def __str__(self):
        return f"{self.stac_item_id} ({self.collection}, cloud={self.cloud_cover_pct}%)"


# ==============================================================================
# DATABASE V2: GLOBAL EARTH OBSERVATION & TEMPORAL SATELLITE INTELLIGENCE MODELS
# ==============================================================================

class DataProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    base_url = models.URLField(max_length=512)
    stac_endpoint = models.URLField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.slug})"


class SatelliteCollection(models.Model):
    SENSOR_TYPES = [
        ("OPTICAL", "Multispectral / Optical"),
        ("SAR", "Synthetic Aperture Radar (SAR)"),
        ("HYPERSPECTRAL", "Hyperspectral"),
        ("THERMAL", "Thermal Infrared"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(DataProvider, on_delete=models.CASCADE, related_name="collections")
    collection_id = models.CharField(max_length=128)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    sensor_type = models.CharField(max_length=32, choices=SENSOR_TYPES, default="OPTICAL")
    platform = models.CharField(max_length=64, default="Sentinel-2")
    instrument = models.CharField(max_length=64, default="MSI")
    spatial_resolution_meters = models.FloatField(default=10.0)
    temporal_revisit_days = models.FloatField(default=5.0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("provider", "collection_id")

    def __str__(self):
        return f"{self.name} [{self.collection_id}] ({self.provider.slug})"


class AreaOfInterest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.SET_NULL, null=True, blank=True, related_name="aois"
    )
    geometry = models.JSONField(help_text="GeoJSON Polygon/MultiPolygon coordinates")
    bbox = models.JSONField(help_text="[min_lon, min_lat, max_lon, max_lat]")
    centroid = models.JSONField(null=True, blank=True, help_text="[lon, lat]")
    area_sqkm = models.FloatField(default=0.0)
    crs = models.CharField(max_length=32, default="EPSG:4326")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AOI: {self.name} ({self.area_sqkm:.2f} sq km)"


class SatelliteScene(models.Model):
    SENSOR_CHOICES = [
        ("OPTICAL", "Optical"),
        ("SAR", "Synthetic Aperture Radar"),
    ]
    AVAILABILITY_CHOICES = [
        ("CATALOGUED", "Catalogued in Remote STAC"),
        ("INDEXED", "Metadata Locally Indexed"),
        ("CACHED", "Assets Cached Locally / MinIO"),
        ("ARCHIVED", "Archived in Cold Storage"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64, default="copernicus")
    collection = models.CharField(max_length=128, default="sentinel-2-l2a")
    external_id = models.CharField(max_length=255, db_index=True)
    platform = models.CharField(max_length=64, default="Sentinel-2A")
    mission = models.CharField(max_length=64, default="Sentinel-2")
    instrument = models.CharField(max_length=64, default="MSI")
    acquisition_datetime = models.DateTimeField(db_index=True)
    processing_level = models.CharField(max_length=64, default="LEVEL2A")
    cloud_cover = models.FloatField(null=True, blank=True)
    geometry = models.JSONField(help_text="GeoJSON footprint")
    bbox = models.JSONField(help_text="[minx, miny, maxx, maxy]")
    crs = models.CharField(max_length=32, default="EPSG:4326")
    resolution = models.FloatField(default=10.0)
    sensor = models.CharField(max_length=32, choices=SENSOR_CHOICES, default="OPTICAL")
    modality = models.CharField(max_length=32, default="MULTISPECTRAL")
    metadata = models.JSONField(default=dict, blank=True)
    stac_item_url = models.URLField(max_length=512, blank=True)
    thumbnail_url = models.URLField(max_length=512, blank=True)
    availability_status = models.CharField(max_length=32, choices=AVAILABILITY_CHOICES, default="CATALOGUED")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-acquisition_datetime"]
        unique_together = ("provider", "collection", "external_id")

    def __str__(self):
        return f"{self.external_id} [{self.acquisition_datetime.strftime('%Y-%m-%d')}] ({self.cloud_cover or 0.0}% clouds)"


class SatelliteAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scene = models.ForeignKey(SatelliteScene, on_delete=models.CASCADE, related_name="assets")
    asset_key = models.CharField(max_length=64, help_text="e.g. B02, B03, B04, B08, visual, VV, VH")
    asset_type = models.CharField(max_length=128, default="image/tiff; application=geotiff; profile=cloud-optimized")
    href = models.TextField()
    local_path = models.CharField(max_length=512, blank=True)
    is_downloaded = models.BooleanField(default=False)
    byte_size = models.BigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("scene", "asset_key")

    def __str__(self):
        return f"{self.scene.external_id} -> {self.asset_key} ({'CACHED' if self.is_downloaded else 'REMOTE'})"


class TemporalObservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aoi = models.ForeignKey(AreaOfInterest, on_delete=models.CASCADE, related_name="observations")
    scene = models.ForeignKey(SatelliteScene, on_delete=models.CASCADE, related_name="temporal_observations")
    observation_date = models.DateField(db_index=True)
    year = models.IntegerField(db_index=True)
    month = models.IntegerField()
    cloud_cover = models.FloatField(null=True, blank=True)
    quality_score = models.FloatField(default=1.0)
    thumbnail_url = models.TextField(blank=True)
    is_preferred = models.BooleanField(default=False)
    derived_image = models.ForeignKey(
        "imagery.ImageAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="temporal_source"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["observation_date"]
        unique_together = ("aoi", "scene")

    def __str__(self):
        return f"Obs {self.aoi.name} [{self.observation_date}] {self.scene.platform}"


class ChangeEvent(models.Model):
    CHANGE_TYPES = [
        ("URBAN_EXPANSION", "Urban Expansion"),
        ("VEGETATION_LOSS", "Vegetation Loss"),
        ("VEGETATION_GAIN", "Vegetation Gain"),
        ("WATER_EXPANSION", "Water Expansion"),
        ("WATER_REDUCTION", "Water Reduction"),
        ("CONSTRUCTION", "Construction"),
        ("ROAD_DEVELOPMENT", "Road Development"),
        ("LAND_CLEARING", "Land Clearing"),
        ("BURN_SCAR", "Burn Scar"),
        ("UNKNOWN", "Unknown / Anomaly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aoi = models.ForeignKey(AreaOfInterest, on_delete=models.CASCADE, related_name="change_events")
    scene_before = models.ForeignKey(SatelliteScene, on_delete=models.CASCADE, related_name="changes_as_before")
    scene_after = models.ForeignKey(SatelliteScene, on_delete=models.CASCADE, related_name="changes_as_after")
    change_type = models.CharField(max_length=64, choices=CHANGE_TYPES, default="URBAN_EXPANSION")
    change_polygon = models.JSONField(help_text="GeoJSON Feature/Geometry of the detected change boundary")
    area_hectares = models.FloatField(default=0.0)
    change_percentage = models.FloatField(default=0.0)
    confidence = models.FloatField(default=0.85)
    algorithm = models.CharField(max_length=128, default="NDVI_DIFFERENCING+CANNY_CONTOURS")
    evidence_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.change_type} in {self.aoi.name} ({self.area_hectares:.1f} ha, {self.confidence*100:.0f}% conf)"


class DerivedRaster(models.Model):
    INDEX_TYPES = [
        ("NDVI", "Normalized Difference Vegetation Index"),
        ("NDWI", "Normalized Difference Water Index"),
        ("NDBI", "Normalized Difference Built-up Index"),
        ("NBR", "Normalized Burn Ratio"),
        ("FALSE_COLOR", "False Color (NIR-Red-Green)"),
        ("SAR_RGB", "SAR Dual-Pol (VV/VH/Ratio)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scene = models.ForeignKey(SatelliteScene, on_delete=models.CASCADE, related_name="derived_rasters")
    index_type = models.CharField(max_length=32, choices=INDEX_TYPES, default="NDVI")
    raster_asset = models.ForeignKey(
        "imagery.ImageAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="from_derived_raster"
    )
    thumbnail_url = models.TextField(blank=True)
    min_val = models.FloatField(default=-1.0)
    max_val = models.FloatField(default=1.0)
    mean_val = models.FloatField(default=0.0)
    std_val = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("scene", "index_type")

    def __str__(self):
        return f"{self.scene.external_id} -> {self.index_type} (mean={self.mean_val:.2f})"


class AOIMonitoring(models.Model):
    CADENCE_CHOICES = [
        ("DAILY", "Daily"),
        ("WEEKLY", "Weekly"),
        ("MONTHLY", "Monthly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aoi = models.ForeignKey(AreaOfInterest, on_delete=models.CASCADE, related_name="monitoring_schedules")
    cadence = models.CharField(max_length=16, choices=CADENCE_CHOICES, default="WEEKLY")
    alert_on_change_pct = models.FloatField(default=5.0)
    target_sensor = models.CharField(max_length=32, default="SENTINEL-2")
    is_active = models.BooleanField(default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Monitoring {self.aoi.name} ({self.cadence}, active={self.is_active})"


class DataSyncJob(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64, default="copernicus")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="PENDING")
    scenes_discovered = models.IntegerField(default=0)
    scenes_ingested = models.IntegerField(default=0)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_time"]

    def __str__(self):
        return f"Sync [{self.provider}] {self.status}: {self.scenes_ingested} ingested at {self.start_time.strftime('%Y-%m-%d %H:%M')}"
