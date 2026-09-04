from django.contrib import admin
from apps.satellite.models import (
    AcquisitionRequest,
    AcquisitionCandidate,
    DataProvider,
    SatelliteCollection,
    AreaOfInterest,
    SatelliteScene,
    SatelliteAsset,
    TemporalObservation,
    ChangeEvent,
    DerivedRaster,
    AOIMonitoring,
    DataSyncJob,
)


@admin.register(DataProvider)
class DataProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "stac_endpoint", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "base_url")


@admin.register(SatelliteCollection)
class SatelliteCollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "collection_id", "provider", "sensor_type", "platform", "spatial_resolution_meters", "is_active")
    list_filter = ("sensor_type", "provider", "is_active")
    search_fields = ("name", "collection_id", "platform", "instrument")


@admin.register(AreaOfInterest)
class AreaOfInterestAdmin(admin.ModelAdmin):
    list_display = ("name", "area_sqkm", "crs", "session", "created_at")
    search_fields = ("name", "description")


class SatelliteAssetInline(admin.TabularInline):
    model = SatelliteAsset
    extra = 0
    readonly_fields = ("asset_key", "asset_type", "is_downloaded", "byte_size")


@admin.register(SatelliteScene)
class SatelliteSceneAdmin(admin.ModelAdmin):
    list_display = ("external_id", "platform", "sensor", "acquisition_datetime", "cloud_cover", "availability_status")
    list_filter = ("platform", "sensor", "availability_status", "collection")
    search_fields = ("external_id", "platform", "mission")
    date_hierarchy = "acquisition_datetime"
    inlines = [SatelliteAssetInline]


@admin.register(SatelliteAsset)
class SatelliteAssetAdmin(admin.ModelAdmin):
    list_display = ("scene", "asset_key", "asset_type", "is_downloaded", "byte_size")
    list_filter = ("asset_key", "is_downloaded")
    search_fields = ("scene__external_id", "asset_key")


@admin.register(TemporalObservation)
class TemporalObservationAdmin(admin.ModelAdmin):
    list_display = ("aoi", "observation_date", "year", "month", "cloud_cover", "quality_score", "is_preferred")
    list_filter = ("year", "is_preferred")
    search_fields = ("aoi__name", "scene__external_id")
    date_hierarchy = "observation_date"


@admin.register(ChangeEvent)
class ChangeEventAdmin(admin.ModelAdmin):
    list_display = ("aoi", "change_type", "area_hectares", "change_percentage", "confidence", "algorithm", "created_at")
    list_filter = ("change_type", "algorithm")
    search_fields = ("aoi__name", "scene_before__external_id", "scene_after__external_id")


@admin.register(DerivedRaster)
class DerivedRasterAdmin(admin.ModelAdmin):
    list_display = ("scene", "index_type", "min_val", "max_val", "mean_val", "created_at")
    list_filter = ("index_type",)
    search_fields = ("scene__external_id", "index_type")


@admin.register(AOIMonitoring)
class AOIMonitoringAdmin(admin.ModelAdmin):
    list_display = ("aoi", "cadence", "alert_on_change_pct", "target_sensor", "is_active", "last_checked_at")
    list_filter = ("cadence", "is_active", "target_sensor")


@admin.register(DataSyncJob)
class DataSyncJobAdmin(admin.ModelAdmin):
    list_display = ("provider", "status", "scenes_discovered", "scenes_ingested", "start_time", "end_time")
    list_filter = ("provider", "status")


@admin.register(AcquisitionRequest)
class AcquisitionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "sensor", "date_start", "date_end", "status", "created_at")
    list_filter = ("sensor", "status")


@admin.register(AcquisitionCandidate)
class AcquisitionCandidateAdmin(admin.ModelAdmin):
    list_display = ("stac_item_id", "request", "collection", "acquisition_date", "cloud_cover_pct", "selected")
    list_filter = ("collection", "selected")
