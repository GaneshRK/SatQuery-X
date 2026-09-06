"""
SatQuery-X satellite intelligence data models.

This module stores catalogue metadata, acquisition requests, AOIs, satellite
scenes/assets, temporal observations, derived products, change events,
monitoring schedules, and synchronization jobs.

Scientific measurements are nullable unless they are actually supplied by the
source catalogue or an analysis pipeline. The models intentionally do not
invent coordinates, resolutions, cloud percentages, confidence values, or
analysis results.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# =============================================================================
# ACQUISITION
# =============================================================================


class AcquisitionRequest(models.Model):
    """A user/session request for finding satellite observations."""

    SENSOR_CHOICES = [
        ("SENTINEL-1", "Sentinel-1 (SAR)"),
        ("SENTINEL-2", "Sentinel-2 (Optical)"),
        ("BOTH", "Optical + SAR"),
    ]

    STATUS_CHOICES = [
        ("SEARCHING", "Searching"),
        ("RESULTS_READY", "Results Ready"),
        ("RETRIEVING", "Retrieving"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    session = models.ForeignKey(
        "analysis_sessions.Session",
        on_delete=models.CASCADE,
        related_name="satellite_requests",
    )

    aoi_geometry = models.JSONField(
        help_text="GeoJSON geometry supplied by the user or map context.",
    )

    sensor = models.CharField(
        max_length=32,
        choices=SENSOR_CHOICES,
        default="SENTINEL-2",
    )

    date_start = models.DateField()

    date_end = models.DateField()

    max_cloud_cover = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum requested cloud cover percentage, if specified.",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="SEARCHING",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["session", "-created_at"],
                name="sat_acq_session_created_idx",
            ),
            models.Index(
                fields=["sensor", "date_start", "date_end"],
                name="sat_acq_sensor_dates_idx",
            ),
            models.Index(
                fields=["status", "-created_at"],
                name="sat_acq_status_created_idx",
            ),
        ]

    def clean(self):
        if self.date_start and self.date_end:
            if self.date_start > self.date_end:
                raise ValidationError(
                    {"date_end": "End date must be on or after start date."}
                )

        if self.max_cloud_cover is not None:
            if not 0 <= self.max_cloud_cover <= 100:
                raise ValidationError(
                    {"max_cloud_cover": "Cloud cover must be between 0 and 100."}
                )

    def __str__(self):
        return (
            f"AcquisitionRequest {self.id} "
            f"({self.sensor}): {self.status}"
        )


class AcquisitionCandidate(models.Model):
    """A catalogue scene returned for an acquisition request."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    request = models.ForeignKey(
        AcquisitionRequest,
        on_delete=models.CASCADE,
        related_name="candidates",
    )

    stac_item_id = models.CharField(
        max_length=255,
        db_index=True,
    )

    collection = models.CharField(
        max_length=128,
    )

    acquisition_date = models.DateField(
        db_index=True,
    )

    cloud_cover_pct = models.FloatField(
        null=True,
        blank=True,
    )

    footprint_geom = models.JSONField(
        null=True,
        blank=True,
        help_text="Footprint returned by the remote catalogue.",
    )

    selected = models.BooleanField(
        default=False,
    )

    retrieved_image = models.ForeignKey(
        "imagery.ImageAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="from_candidate",
    )

    assets_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Remote STAC asset metadata returned during discovery.",
    )

    thumbnail_url = models.URLField(
        max_length=1024,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            models.F("cloud_cover_pct").asc(nulls_last=True),
            "-acquisition_date",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "stac_item_id"],
                name="sat_candidate_request_item_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["request", "selected"],
                name="sat_candidate_req_selected_idx",
            ),
            models.Index(
                fields=["stac_item_id"],
                name="sat_candidate_stac_idx",
            ),
        ]

    def clean(self):
        if self.cloud_cover_pct is not None:
            if not 0 <= self.cloud_cover_pct <= 100:
                raise ValidationError(
                    {"cloud_cover_pct": "Cloud cover must be between 0 and 100."}
                )

    def __str__(self):
        cloud = (
            f"{self.cloud_cover_pct}%"
            if self.cloud_cover_pct is not None
            else "unknown cloud"
        )

        return (
            f"{self.stac_item_id} "
            f"({self.collection}, {cloud})"
        )


# =============================================================================
# DATA PROVIDERS AND COLLECTIONS
# =============================================================================


class DataProvider(models.Model):
    """Remote Earth-observation catalogue/data provider."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=128,
        unique=True,
    )

    slug = models.SlugField(
        max_length=64,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    base_url = models.URLField(
        max_length=512,
    )

    stac_endpoint = models.URLField(
        max_length=512,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class SatelliteCollection(models.Model):
    """A satellite data collection exposed by a provider."""

    SENSOR_TYPES = [
        ("OPTICAL", "Multispectral / Optical"),
        ("SAR", "Synthetic Aperture Radar"),
        ("HYPERSPECTRAL", "Hyperspectral"),
        ("THERMAL", "Thermal Infrared"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    provider = models.ForeignKey(
        DataProvider,
        on_delete=models.CASCADE,
        related_name="collections",
    )

    collection_id = models.CharField(
        max_length=128,
    )

    name = models.CharField(
        max_length=128,
    )

    description = models.TextField(
        blank=True,
    )

    sensor_type = models.CharField(
        max_length=32,
        choices=SENSOR_TYPES,
    )

    platform = models.CharField(
        max_length=64,
        blank=True,
    )

    instrument = models.CharField(
        max_length=64,
        blank=True,
    )

    spatial_resolution_meters = models.FloatField(
        null=True,
        blank=True,
        help_text="Catalogue-provided nominal spatial resolution.",
    )

    temporal_revisit_days = models.FloatField(
        null=True,
        blank=True,
        help_text="Catalogue-provided revisit interval, if available.",
    )

    is_active = models.BooleanField(
        default=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["provider", "collection_id"],
                name="sat_collection_provider_id_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["sensor_type", "is_active"],
                name="sat_coll_sensor_act_idx",
            ),
        ]

    def clean(self):
        if self.spatial_resolution_meters is not None:
            if self.spatial_resolution_meters <= 0:
                raise ValidationError(
                    {
                        "spatial_resolution_meters":
                            "Spatial resolution must be greater than zero."
                    }
                )

        if self.temporal_revisit_days is not None:
            if self.temporal_revisit_days <= 0:
                raise ValidationError(
                    {
                        "temporal_revisit_days":
                            "Temporal revisit must be greater than zero."
                    }
                )

    def __str__(self):
        return (
            f"{self.name} "
            f"[{self.collection_id}] "
            f"({self.provider.slug})"
        )


# =============================================================================
# AREAS OF INTEREST
# =============================================================================


class AreaOfInterest(models.Model):
    """User or system-defined geographic analysis area."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
    )

    session = models.ForeignKey(
        "analysis_sessions.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aois",
    )

    geometry = models.JSONField(
        help_text="GeoJSON Polygon/MultiPolygon geometry.",
    )

    bbox = models.JSONField(
        null=True,
        blank=True,
        help_text="[min_x, min_y, max_x, max_y].",
    )

    centroid = models.JSONField(
        null=True,
        blank=True,
        help_text="[x, y] derived from the supplied geometry.",
    )

    area_sqkm = models.FloatField(
        null=True,
        blank=True,
        help_text="Area only when calculated from valid geospatial data.",
    )

    crs = models.CharField(
        max_length=64,
        default="EPSG:4326",
    )

    properties = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["session", "-created_at"],
                name="sat_aoi_session_created_idx",
            ),
        ]

    def clean(self):
        if self.area_sqkm is not None and self.area_sqkm < 0:
            raise ValidationError(
                {"area_sqkm": "Area cannot be negative."}
            )

        if self.bbox is not None:
            if not isinstance(self.bbox, (list, tuple)) or len(self.bbox) != 4:
                raise ValidationError(
                    {"bbox": "Bounding box must contain four coordinates."}
                )

    def __str__(self):
        area = (
            f"{self.area_sqkm:.2f} sq km"
            if self.area_sqkm is not None
            else "area unavailable"
        )

        return f"AOI: {self.name} ({area})"


# =============================================================================
# SATELLITE SCENES
# =============================================================================


class SatelliteScene(models.Model):
    """Metadata for one satellite observation/scene."""

    SENSOR_CHOICES = [
        ("OPTICAL", "Optical"),
        ("SAR", "Synthetic Aperture Radar"),
        ("HYPERSPECTRAL", "Hyperspectral"),
        ("THERMAL", "Thermal"),
        ("UNKNOWN", "Unknown"),
    ]

    AVAILABILITY_CHOICES = [
        ("CATALOGUED", "Catalogued in Remote STAC"),
        ("INDEXED", "Metadata Locally Indexed"),
        ("CACHED", "Assets Cached Locally"),
        ("ARCHIVED", "Archived in Cold Storage"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    provider = models.CharField(
        max_length=64,
        blank=True,
    )

    collection = models.CharField(
        max_length=128,
        blank=True,
    )

    external_id = models.CharField(
        max_length=255,
        db_index=True,
    )

    platform = models.CharField(
        max_length=64,
        blank=True,
    )

    mission = models.CharField(
        max_length=64,
        blank=True,
    )

    instrument = models.CharField(
        max_length=64,
        blank=True,
    )

    acquisition_datetime = models.DateTimeField(
        db_index=True,
    )

    processing_level = models.CharField(
        max_length=64,
        blank=True,
    )

    cloud_cover = models.FloatField(
        null=True,
        blank=True,
    )

    geometry = models.JSONField(
        null=True,
        blank=True,
        help_text="Footprint supplied by the source catalogue.",
    )

    bbox = models.JSONField(
        null=True,
        blank=True,
        help_text="[min_x, min_y, max_x, max_y] when supplied.",
    )

    crs = models.CharField(
        max_length=64,
        blank=True,
    )

    resolution = models.FloatField(
        null=True,
        blank=True,
        help_text="Source-provided spatial resolution in metres.",
    )

    sensor = models.CharField(
        max_length=32,
        choices=SENSOR_CHOICES,
        default="UNKNOWN",
    )

    modality = models.CharField(
        max_length=64,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    stac_item_url = models.URLField(
        max_length=1024,
        blank=True,
    )

    thumbnail_url = models.URLField(
        max_length=1024,
        blank=True,
    )

    availability_status = models.CharField(
        max_length=32,
        choices=AVAILABILITY_CHOICES,
        default="CATALOGUED",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-acquisition_datetime"]

        constraints = [
            models.UniqueConstraint(
                fields=["provider", "collection", "external_id"],
                name="sat_scene_provider_collection_external_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["sensor", "-acquisition_datetime"],
                name="sat_scene_sensor_date_idx",
            ),
            models.Index(
                fields=["platform", "-acquisition_datetime"],
                name="sat_scene_platform_date_idx",
            ),
            models.Index(
                fields=["availability_status", "acquisition_datetime"],
                name="sat_scene_avail_date_idx",
            ),
        ]

    def clean(self):
        if self.cloud_cover is not None:
            if not 0 <= self.cloud_cover <= 100:
                raise ValidationError(
                    {"cloud_cover": "Cloud cover must be between 0 and 100."}
                )

        if self.resolution is not None:
            if self.resolution <= 0:
                raise ValidationError(
                    {"resolution": "Resolution must be greater than zero."}
                )

    def __str__(self):
        date_text = (
            self.acquisition_datetime.strftime("%Y-%m-%d")
            if self.acquisition_datetime
            else "unknown date"
        )

        return f"{self.external_id} [{date_text}] ({self.sensor})"


# =============================================================================
# SATELLITE ASSETS
# =============================================================================


class SatelliteAsset(models.Model):
    """A remotely hosted or locally cached asset belonging to a scene."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    scene = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="assets",
    )

    asset_key = models.CharField(
        max_length=128,
        help_text="STAC asset key such as B02, B03, B04, B08, VV, VH, visual.",
    )

    asset_type = models.CharField(
        max_length=256,
        blank=True,
    )

    href = models.TextField(
        help_text="Remote or source asset URL/path.",
    )

    local_path = models.CharField(
        max_length=1024,
        blank=True,
    )

    is_downloaded = models.BooleanField(
        default=False,
    )

    byte_size = models.BigIntegerField(
        null=True,
        blank=True,
    )

    checksum = models.CharField(
        max_length=128,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "asset_key"],
                name="sat_asset_scene_key_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["scene", "asset_key"],
                name="sat_asset_scene_key_idx",
            ),
            models.Index(
                fields=["is_downloaded"],
                name="sat_asset_downloaded_idx",
            ),
        ]

    def clean(self):
        if self.byte_size is not None and self.byte_size < 0:
            raise ValidationError(
                {"byte_size": "Byte size cannot be negative."}
            )

        if self.is_downloaded and not self.local_path:
            raise ValidationError(
                {
                    "local_path":
                        "A downloaded asset must have a local path."
                }
            )

    def __str__(self):
        state = "CACHED" if self.is_downloaded else "REMOTE"

        return (
            f"{self.scene.external_id} -> "
            f"{self.asset_key} ({state})"
        )


# =============================================================================
# TEMPORAL OBSERVATIONS
# =============================================================================


class TemporalObservation(models.Model):
    """A scene associated with an AOI for temporal analysis."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    aoi = models.ForeignKey(
        AreaOfInterest,
        on_delete=models.CASCADE,
        related_name="observations",
    )

    scene = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="temporal_observations",
    )

    observation_date = models.DateField(
        db_index=True,
    )

    year = models.IntegerField(
        db_index=True,
    )

    month = models.IntegerField()

    cloud_cover = models.FloatField(
        null=True,
        blank=True,
    )

    quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Only populated when a documented quality metric exists.",
    )

    thumbnail_url = models.TextField(
        blank=True,
    )

    is_preferred = models.BooleanField(
        default=False,
    )

    derived_image = models.ForeignKey(
        "imagery.ImageAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temporal_source",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["observation_date"]

        constraints = [
            models.UniqueConstraint(
                fields=["aoi", "scene"],
                name="sat_observation_aoi_scene_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["aoi", "observation_date"],
                name="sat_obs_aoi_date_idx",
            ),
            models.Index(
                fields=["aoi", "year"],
                name="sat_obs_aoi_year_idx",
            ),
        ]

    def clean(self):
        if not 1 <= self.month <= 12:
            raise ValidationError(
                {"month": "Month must be between 1 and 12."}
            )

        if self.cloud_cover is not None:
            if not 0 <= self.cloud_cover <= 100:
                raise ValidationError(
                    {"cloud_cover": "Cloud cover must be between 0 and 100."}
                )

        if self.quality_score is not None:
            if not 0 <= self.quality_score <= 1:
                raise ValidationError(
                    {"quality_score": "Quality score must be between 0 and 1."}
                )

    def save(self, *args, **kwargs):
        if self.observation_date:
            self.year = self.observation_date.year
            self.month = self.observation_date.month

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Obs {self.aoi.name} "
            f"[{self.observation_date}]"
        )


# =============================================================================
# CHANGE EVENTS
# =============================================================================


class ChangeEvent(models.Model):
    """
    Persisted result of a documented change-detection analysis.

    The numerical fields are nullable because an analysis may produce only a
    mask/geometry or qualitative evidence without a defensible physical area,
    percentage, or probability.
    """

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

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    aoi = models.ForeignKey(
        AreaOfInterest,
        on_delete=models.CASCADE,
        related_name="change_events",
    )

    scene_before = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="changes_as_before",
    )

    scene_after = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="changes_as_after",
    )

    change_type = models.CharField(
        max_length=64,
        choices=CHANGE_TYPES,
        default="UNKNOWN",
    )

    change_polygon = models.JSONField(
        null=True,
        blank=True,
        help_text="Evidence-derived GeoJSON feature or geometry.",
    )

    area_hectares = models.FloatField(
        null=True,
        blank=True,
        help_text="Physical area only when valid geospatial measurement exists.",
    )

    change_percentage = models.FloatField(
        null=True,
        blank=True,
        help_text="Percentage only when denominator and measurement are known.",
    )

    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="Model/evidence confidence when explicitly produced.",
    )

    algorithm = models.CharField(
        max_length=256,
        blank=True,
    )

    evidence_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["aoi", "-created_at"],
                name="sat_change_aoi_created_idx",
            ),
            models.Index(
                fields=["change_type", "-created_at"],
                name="sat_change_type_created_idx",
            ),
        ]

    def clean(self):
        if self.area_hectares is not None and self.area_hectares < 0:
            raise ValidationError(
                {"area_hectares": "Area cannot be negative."}
            )

        if self.change_percentage is not None:
            if not 0 <= self.change_percentage <= 100:
                raise ValidationError(
                    {
                        "change_percentage":
                            "Change percentage must be between 0 and 100."
                    }
                )

        if self.confidence is not None:
            if not 0 <= self.confidence <= 1:
                raise ValidationError(
                    {"confidence": "Confidence must be between 0 and 1."}
                )

        if (
            self.scene_before_id
            and self.scene_after_id
            and self.scene_before_id == self.scene_after_id
        ):
            raise ValidationError(
                "Before and after scenes must be different."
            )

    def __str__(self):
        area = (
            f"{self.area_hectares:.2f} ha"
            if self.area_hectares is not None
            else "area unavailable"
        )

        return (
            f"{self.change_type} in {self.aoi.name} "
            f"({area})"
        )


# =============================================================================
# DERIVED RASTERS
# =============================================================================


class DerivedRaster(models.Model):
    """A scientifically derived raster associated with a satellite scene."""

    INDEX_TYPES = [
        ("NDVI", "Normalized Difference Vegetation Index"),
        ("NDWI", "Normalized Difference Water Index"),
        ("NDBI", "Normalized Difference Built-up Index"),
        ("NBR", "Normalized Burn Ratio"),
        ("FALSE_COLOR", "False Color"),
        ("SAR_RGB", "SAR Dual-Polarization Visualization"),
        ("CHANGE_MASK", "Change Mask"),
        ("CUSTOM", "Custom Derived Raster"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    scene = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="derived_rasters",
    )

    index_type = models.CharField(
        max_length=32,
        choices=INDEX_TYPES,
    )

    raster_asset = models.ForeignKey(
        "imagery.ImageAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="from_derived_raster",
    )

    thumbnail_url = models.TextField(
        blank=True,
    )

    min_val = models.FloatField(
        null=True,
        blank=True,
    )

    max_val = models.FloatField(
        null=True,
        blank=True,
    )

    mean_val = models.FloatField(
        null=True,
        blank=True,
    )

    std_val = models.FloatField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["scene", "index_type"],
                name="sat_derived_scene_index_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["scene", "index_type"],
                name="sat_derived_scene_type_idx",
            ),
        ]

    def clean(self):
        values = [
            value
            for value in (
                self.min_val,
                self.max_val,
                self.mean_val,
                self.std_val,
            )
            if value is not None
        ]

        for value in values:
            if not isinstance(value, (int, float)):
                raise ValidationError(
                    "Derived raster statistics must be numeric."
                )

        if (
            self.min_val is not None
            and self.max_val is not None
            and self.min_val > self.max_val
        ):
            raise ValidationError(
                "Minimum value cannot exceed maximum value."
            )

        if self.std_val is not None and self.std_val < 0:
            raise ValidationError(
                {"std_val": "Standard deviation cannot be negative."}
            )

    def __str__(self):
        return (
            f"{self.scene.external_id} -> "
            f"{self.index_type}"
        )


# =============================================================================
# AOI MONITORING
# =============================================================================


class AOIMonitoring(models.Model):
    """Recurring monitoring configuration for an AOI."""

    CADENCE_CHOICES = [
        ("DAILY", "Daily"),
        ("WEEKLY", "Weekly"),
        ("MONTHLY", "Monthly"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    aoi = models.ForeignKey(
        AreaOfInterest,
        on_delete=models.CASCADE,
        related_name="monitoring_schedules",
    )

    cadence = models.CharField(
        max_length=16,
        choices=CADENCE_CHOICES,
        default="WEEKLY",
    )

    alert_on_change_pct = models.FloatField(
        null=True,
        blank=True,
        help_text="Optional user-defined alert threshold.",
    )

    target_sensor = models.CharField(
        max_length=64,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_observation_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["is_active", "cadence"],
                name="sat_monitor_active_cadence_idx",
            ),
            models.Index(
                fields=["aoi", "is_active"],
                name="sat_monitor_aoi_active_idx",
            ),
        ]

    def clean(self):
        if self.alert_on_change_pct is not None:
            if not 0 <= self.alert_on_change_pct <= 100:
                raise ValidationError(
                    {
                        "alert_on_change_pct":
                            "Alert threshold must be between 0 and 100."
                    }
                )

    def __str__(self):
        return (
            f"Monitoring {self.aoi.name} "
            f"({self.cadence}, active={self.is_active})"
        )


# =============================================================================
# CATALOGUE SYNCHRONIZATION
# =============================================================================


class DataSyncJob(models.Model):
    """Audit record for catalogue synchronization."""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    provider = models.CharField(
        max_length=128,
        blank=True,
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    scenes_discovered = models.PositiveIntegerField(
        default=0,
    )

    scenes_ingested = models.PositiveIntegerField(
        default=0,
    )

    start_time = models.DateTimeField(
        auto_now_add=True,
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-start_time"]

        indexes = [
            models.Index(
                fields=["provider", "-start_time"],
                name="sat_sync_provider_start_idx",
            ),
            models.Index(
                fields=["status", "-start_time"],
                name="sat_sync_status_start_idx",
            ),
        ]

    def clean(self):
        if self.scenes_ingested > self.scenes_discovered:
            raise ValidationError(
                {
                    "scenes_ingested":
                        "Ingested scenes cannot exceed discovered scenes."
                }
            )

        if self.end_time and self.start_time:
            if self.end_time < self.start_time:
                raise ValidationError(
                    {"end_time": "End time cannot precede start time."}
                )

    def mark_running(self):
        self.status = "RUNNING"
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

    def mark_completed(
        self,
        scenes_discovered: int | None = None,
        scenes_ingested: int | None = None,
    ):
        if scenes_discovered is not None:
            self.scenes_discovered = max(0, scenes_discovered)

        if scenes_ingested is not None:
            self.scenes_ingested = max(0, scenes_ingested)

        self.status = "COMPLETED"
        self.end_time = timezone.now()
        self.error_message = ""

        self.save(
            update_fields=[
                "status",
                "scenes_discovered",
                "scenes_ingested",
                "end_time",
                "error_message",
                "updated_at",
            ]
        )

    def mark_failed(self, error: str):
        self.status = "FAILED"
        self.end_time = timezone.now()
        self.error_message = str(error)[:10000]

        self.save(
            update_fields=[
                "status",
                "end_time",
                "error_message",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"Sync [{self.provider or 'unknown provider'}] "
            f"{self.status}: "
            f"{self.scenes_ingested}/{self.scenes_discovered}"
        )