from __future__ import annotations
from rest_framework import serializers
from apps.satellite.models import (
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


class DataProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataProvider
        fields = ["id", "name", "slug", "description", "base_url", "stac_endpoint", "is_active", "metadata"]


class SatelliteCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SatelliteCollection
        fields = [
            "id",
            "provider",
            "collection_id",
            "name",
            "description",
            "sensor_type",
            "platform",
            "instrument",
            "spatial_resolution_meters",
            "temporal_revisit_days",
            "is_active",
        ]


class SatelliteAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = SatelliteAsset
        fields = ["id", "asset_key", "asset_type", "href", "local_path", "is_downloaded", "byte_size"]


class SatelliteSceneSerializer(serializers.ModelSerializer):
    assets = SatelliteAssetSerializer(many=True, read_only=True)

    class Meta:
        model = SatelliteScene
        fields = [
            "id",
            "provider",
            "collection",
            "external_id",
            "platform",
            "mission",
            "instrument",
            "acquisition_datetime",
            "processing_level",
            "cloud_cover",
            "geometry",
            "bbox",
            "crs",
            "resolution",
            "sensor",
            "modality",
            "metadata",
            "stac_item_url",
            "thumbnail_url",
            "availability_status",
            "assets",
            "created_at",
        ]


class AreaOfInterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaOfInterest
        fields = [
            "id",
            "name",
            "description",
            "session",
            "geometry",
            "bbox",
            "centroid",
            "area_sqkm",
            "crs",
            "created_at",
            "updated_at",
        ]


class TemporalObservationSerializer(serializers.ModelSerializer):
    scene_id = serializers.CharField(source="scene.id", read_only=True)
    platform = serializers.CharField(source="scene.platform", read_only=True)
    sensor = serializers.CharField(source="scene.sensor", read_only=True)
    external_id = serializers.CharField(source="scene.external_id", read_only=True)

    class Meta:
        model = TemporalObservation
        fields = [
            "id",
            "aoi",
            "scene_id",
            "external_id",
            "platform",
            "sensor",
            "observation_date",
            "year",
            "month",
            "cloud_cover",
            "quality_score",
            "thumbnail_url",
            "is_preferred",
            "derived_image",
            "created_at",
        ]


class ChangeEventSerializer(serializers.ModelSerializer):
    aoi_name = serializers.CharField(source="aoi.name", read_only=True)
    before_date = serializers.DateTimeField(source="scene_before.acquisition_datetime", read_only=True)
    after_date = serializers.DateTimeField(source="scene_after.acquisition_datetime", read_only=True)
    before_scene_id = serializers.CharField(source="scene_before.external_id", read_only=True)
    after_scene_id = serializers.CharField(source="scene_after.external_id", read_only=True)

    class Meta:
        model = ChangeEvent
        fields = [
            "id",
            "aoi",
            "aoi_name",
            "scene_before",
            "before_scene_id",
            "before_date",
            "scene_after",
            "after_scene_id",
            "after_date",
            "change_type",
            "change_polygon",
            "area_hectares",
            "change_percentage",
            "confidence",
            "algorithm",
            "evidence_data",
            "created_at",
        ]


class DerivedRasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DerivedRaster
        fields = [
            "id",
            "scene",
            "index_type",
            "raster_asset",
            "thumbnail_url",
            "min_val",
            "max_val",
            "mean_val",
            "std_val",
            "metadata",
            "created_at",
        ]


class AOIMonitoringSerializer(serializers.ModelSerializer):
    aoi_name = serializers.CharField(source="aoi.name", read_only=True)

    class Meta:
        model = AOIMonitoring
        fields = [
            "id",
            "aoi",
            "aoi_name",
            "cadence",
            "alert_on_change_pct",
            "target_sensor",
            "is_active",
            "last_checked_at",
            "created_at",
        ]


class DataSyncJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSyncJob
        fields = [
            "id",
            "provider",
            "status",
            "scenes_discovered",
            "scenes_ingested",
            "start_time",
            "end_time",
            "error_message",
        ]
