"""
Django REST Framework serializers for the SatQuery-X satellite subsystem.

Design goals:
- Expose only actual persisted/provider-derived satellite information.
- Never fabricate scientific metadata.
- Validate ownership-sensitive relationships through serializer context.
- Keep the serializer contracts aligned with apps.satellite.models.
- Support acquisition requests, catalogue scenes, observations,
  change events, monitoring configuration, and synchronization records.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    AcquisitionCandidate,
    AcquisitionRequest,
    AOIMonitoring,
    AreaOfInterest,
    ChangeEvent,
    DataProvider,
    DataSyncJob,
    DerivedRaster,
    SatelliteAsset,
    SatelliteCollection,
    SatelliteScene,
    TemporalObservation,
)


# =============================================================================
# HELPERS
# =============================================================================


def _clean_geometry(value):
    """
    Basic GeoJSON validation.

    This validates structure only.

    It does NOT:
    - transform coordinates,
    - assign a CRS,
    - calculate area,
    - invent a geometry,
    - modify user/provider coordinates.
    """
    if value is None:
        return value

    if not isinstance(value, dict):
        raise serializers.ValidationError(
            "Geometry must be a GeoJSON object."
        )

    geometry_type = value.get("type")

    if geometry_type not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }:
        raise serializers.ValidationError(
            "Unsupported or missing GeoJSON geometry type."
        )

    return value


def _clean_bbox(value):
    """
    Validate a four-coordinate bounding box.
    """
    if value is None:
        return value

    if not isinstance(value, (list, tuple)):
        raise serializers.ValidationError(
            "Bounding box must be an array of four coordinates."
        )

    if len(value) != 4:
        raise serializers.ValidationError(
            "Bounding box must contain exactly four coordinates."
        )

    cleaned = []

    for coordinate in value:
        try:
            cleaned.append(float(coordinate))
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                "Bounding box coordinates must be numeric."
            )

    if cleaned[0] > cleaned[2]:
        raise serializers.ValidationError(
            "Bounding box minimum X cannot exceed maximum X."
        )

    if cleaned[1] > cleaned[3]:
        raise serializers.ValidationError(
            "Bounding box minimum Y cannot exceed maximum Y."
        )

    return cleaned


# =============================================================================
# PROVIDERS
# =============================================================================


class DataProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataProvider
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "base_url",
            "stac_endpoint",
            "is_active",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


# =============================================================================
# COLLECTIONS
# =============================================================================


class SatelliteCollectionSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(
        source="provider.name",
        read_only=True,
    )

    class Meta:
        model = SatelliteCollection
        fields = [
            "id",
            "provider",
            "provider_name",
            "collection_id",
            "name",
            "description",
            "sensor_type",
            "platform",
            "instrument",
            "spatial_resolution_meters",
            "temporal_revisit_days",
            "is_active",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "provider_name",
            "created_at",
            "updated_at",
        ]

    def validate_spatial_resolution_meters(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Spatial resolution must be greater than zero."
            )

        return value

    def validate_temporal_revisit_days(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Temporal revisit must be greater than zero."
            )

        return value


# =============================================================================
# AREAS OF INTEREST
# =============================================================================


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
            "properties",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "area_sqkm",
            "created_at",
            "updated_at",
        ]

    def validate_geometry(self, value):
        return _clean_geometry(value)

    def validate_bbox(self, value):
        return _clean_bbox(value)

    def validate_area_sqkm(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Area cannot be negative."
            )

        return value

    def validate_crs(self, value):
        if value is not None:
            value = str(value).strip()

            if not value:
                raise serializers.ValidationError(
                    "CRS cannot be an empty string."
                )

        return value


# =============================================================================
# SATELLITE SCENES
# =============================================================================


class SatelliteSceneSerializer(serializers.ModelSerializer):
    asset_count = serializers.SerializerMethodField()

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
            "asset_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "asset_count",
            "created_at",
            "updated_at",
        ]

    def get_asset_count(self, obj):
        return obj.assets.count()

    def validate_geometry(self, value):
        return _clean_geometry(value)

    def validate_bbox(self, value):
        return _clean_bbox(value)

    def validate_cloud_cover(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Cloud cover must be between 0 and 100."
            )

        return value

    def validate_resolution(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Resolution must be greater than zero."
            )

        return value


# =============================================================================
# SATELLITE ASSETS
# =============================================================================


class SatelliteAssetSerializer(serializers.ModelSerializer):
    scene_external_id = serializers.CharField(
        source="scene.external_id",
        read_only=True,
    )

    class Meta:
        model = SatelliteAsset
        fields = [
            "id",
            "scene",
            "scene_external_id",
            "asset_key",
            "asset_type",
            "href",
            "local_path",
            "is_downloaded",
            "byte_size",
            "checksum",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "scene_external_id",
            "created_at",
            "updated_at",
        ]

    def validate_byte_size(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Byte size cannot be negative."
            )

        return value

    def validate(self, attrs):
        downloaded = attrs.get(
            "is_downloaded",
            getattr(
                self.instance,
                "is_downloaded",
                False,
            ),
        )

        local_path = attrs.get(
            "local_path",
            getattr(
                self.instance,
                "local_path",
                "",
            ),
        )

        if downloaded and not local_path:
            raise serializers.ValidationError(
                {
                    "local_path": (
                        "A downloaded asset must have "
                        "a local path."
                    )
                }
            )

        return attrs


# =============================================================================
# ACQUISITION REQUEST
# =============================================================================


class AcquisitionRequestSerializer(
    serializers.ModelSerializer
):
    candidate_count = serializers.SerializerMethodField()

    class Meta:
        model = AcquisitionRequest
        fields = [
            "id",
            "session",
            "aoi_geometry",
            "sensor",
            "date_start",
            "date_end",
            "max_cloud_cover",
            "status",
            "candidate_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "candidate_count",
            "created_at",
            "updated_at",
        ]

    def validate_aoi_geometry(self, value):
        return _clean_geometry(value)

    def validate_max_cloud_cover(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Maximum cloud cover must be between 0 and 100."
            )

        return value

    def validate(self, attrs):
        start = attrs.get(
            "date_start",
            getattr(
                self.instance,
                "date_start",
                None,
            ),
        )

        end = attrs.get(
            "date_end",
            getattr(
                self.instance,
                "date_end",
                None,
            ),
        )

        if start and end and start > end:
            raise serializers.ValidationError(
                {
                    "date_end": (
                        "End date must be on or after "
                        "start date."
                    )
                }
            )

        return attrs

    def get_candidate_count(self, obj):
        return obj.candidates.count()


class AcquisitionRequestCreateSerializer(
    serializers.ModelSerializer
):
    """
    Serializer used when creating an acquisition request.

    The session is resolved from the authenticated user in the view.

    This serializer deliberately does not create:
    - scenes,
    - candidates,
    - imagery,
    - measurements,
    - fake catalogue records.
    """

    class Meta:
        model = AcquisitionRequest
        fields = [
            "id",
            "session",
            "aoi_geometry",
            "sensor",
            "date_start",
            "date_end",
            "max_cloud_cover",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_aoi_geometry(self, value):
        return _clean_geometry(value)

    def validate_max_cloud_cover(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Maximum cloud cover must be between 0 and 100."
            )

        return value

    def validate(self, attrs):
        start = attrs.get("date_start")
        end = attrs.get("date_end")

        if start and end and start > end:
            raise serializers.ValidationError(
                {
                    "date_end": (
                        "End date must be on or after "
                        "start date."
                    )
                }
            )

        request = self.context.get("request")

        if request is not None and request.user.is_authenticated:
            session = attrs.get("session")

            if session is not None:
                session_user = getattr(
                    session,
                    "user",
                    None,
                )

                if session_user != request.user:
                    raise serializers.ValidationError(
                        {
                            "session": (
                                "The session does not belong "
                                "to the authenticated user."
                            )
                        }
                    )

        return attrs


# =============================================================================
# ACQUISITION CANDIDATES
# =============================================================================


class AcquisitionCandidateSerializer(
    serializers.ModelSerializer
):
    request_id = serializers.UUIDField(
        source="request.id",
        read_only=True,
    )

    request_session_id = serializers.UUIDField(
        source="request.session_id",
        read_only=True,
    )

    retrieved_image_id = serializers.UUIDField(
        source="retrieved_image.id",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AcquisitionCandidate
        fields = [
            "id",
            "request",
            "request_id",
            "request_session_id",
            "stac_item_id",
            "collection",
            "acquisition_date",
            "cloud_cover_pct",
            "footprint_geom",
            "selected",
            "retrieved_image",
            "retrieved_image_id",
            "assets_summary",
            "thumbnail_url",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "request_id",
            "request_session_id",
            "retrieved_image_id",
            "created_at",
        ]

    def validate_footprint_geom(self, value):
        if value is None:
            return value

        return _clean_geometry(value)

    def validate_cloud_cover_pct(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Cloud cover must be between 0 and 100."
            )

        return value


# =============================================================================
# TEMPORAL OBSERVATIONS
# =============================================================================


class TemporalObservationSerializer(
    serializers.ModelSerializer
):
    scene_external_id = serializers.CharField(
        source="scene.external_id",
        read_only=True,
    )

    aoi_name = serializers.CharField(
        source="aoi.name",
        read_only=True,
    )

    class Meta:
        model = TemporalObservation
        fields = [
            "id",
            "aoi",
            "aoi_name",
            "scene",
            "scene_external_id",
            "observation_date",
            "year",
            "month",
            "cloud_cover",
            "quality_score",
            "thumbnail_url",
            "is_preferred",
            "derived_image",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "aoi_name",
            "scene_external_id",
            "year",
            "month",
            "created_at",
            "updated_at",
        ]

    def validate_cloud_cover(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Cloud cover must be between 0 and 100."
            )

        return value

    def validate_quality_score(self, value):
        if value is not None and not 0 <= value <= 1:
            raise serializers.ValidationError(
                "Quality score must be between 0 and 1."
            )

        return value


# =============================================================================
# CHANGE EVENTS
# =============================================================================


class ChangeEventSerializer(
    serializers.ModelSerializer
):
    aoi_name = serializers.CharField(
        source="aoi.name",
        read_only=True,
    )

    scene_before_id = serializers.UUIDField(
        source="scene_before.id",
        read_only=True,
    )

    scene_after_id = serializers.UUIDField(
        source="scene_after.id",
        read_only=True,
    )

    class Meta:
        model = ChangeEvent
        fields = [
            "id",
            "aoi",
            "aoi_name",
            "scene_before",
            "scene_before_id",
            "scene_after",
            "scene_after_id",
            "change_type",
            "change_polygon",
            "area_hectares",
            "change_percentage",
            "confidence",
            "algorithm",
            "evidence_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "aoi_name",
            "scene_before_id",
            "scene_after_id",
            "created_at",
            "updated_at",
        ]

    def validate_change_polygon(self, value):
        if value is None:
            return value

        return _clean_geometry(value)

    def validate_area_hectares(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Area cannot be negative."
            )

        return value

    def validate_change_percentage(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Change percentage must be between 0 and 100."
            )

        return value

    def validate_confidence(self, value):
        if value is not None and not 0 <= value <= 1:
            raise serializers.ValidationError(
                "Confidence must be between 0 and 1."
            )

        return value

    def validate(self, attrs):
        before = attrs.get(
            "scene_before",
            getattr(
                self.instance,
                "scene_before",
                None,
            ),
        )

        after = attrs.get(
            "scene_after",
            getattr(
                self.instance,
                "scene_after",
                None,
            ),
        )

        if before and after and before.pk == after.pk:
            raise serializers.ValidationError(
                {
                    "scene_after": (
                        "Before and after scenes must "
                        "be different."
                    )
                }
            )

        if before and after:
            before_aoi_id = getattr(
                before.aoi,
                "id",
                None,
            )

            after_aoi_id = getattr(
                after.aoi,
                "id",
                None,
            )

            event_aoi = attrs.get(
                "aoi",
                getattr(
                    self.instance,
                    "aoi",
                    None,
                ),
            )

            if (
                event_aoi is not None
                and before_aoi_id != event_aoi.id
            ):
                raise serializers.ValidationError(
                    {
                        "scene_before": (
                            "Before scene must belong "
                            "to the selected AOI."
                        )
                    }
                )

            if (
                event_aoi is not None
                and after_aoi_id != event_aoi.id
            ):
                raise serializers.ValidationError(
                    {
                        "scene_after": (
                            "After scene must belong "
                            "to the selected AOI."
                        )
                    }
                )

        return attrs


# =============================================================================
# DERIVED RASTERS
# =============================================================================


class DerivedRasterSerializer(
    serializers.ModelSerializer
):
    scene_external_id = serializers.CharField(
        source="scene.external_id",
        read_only=True,
    )

    class Meta:
        model = DerivedRaster
        fields = [
            "id",
            "scene",
            "scene_external_id",
            "index_type",
            "raster_asset",
            "thumbnail_url",
            "min_val",
            "max_val",
            "mean_val",
            "std_val",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "scene_external_id",
            "created_at",
            "updated_at",
        ]

    def validate_std_val(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Standard deviation cannot be negative."
            )

        return value

    def validate(self, attrs):
        minimum = attrs.get(
            "min_val",
            getattr(
                self.instance,
                "min_val",
                None,
            ),
        )

        maximum = attrs.get(
            "max_val",
            getattr(
                self.instance,
                "max_val",
                None,
            ),
        )

        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
            raise serializers.ValidationError(
                {
                    "max_val": (
                        "Maximum value cannot be lower "
                        "than minimum value."
                    )
                }
            )

        return attrs


# =============================================================================
# AOI MONITORING
# =============================================================================


class AOIMonitoringSerializer(
    serializers.ModelSerializer
):
    aoi_name = serializers.CharField(
        source="aoi.name",
        read_only=True,
    )

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
            "last_observation_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "aoi_name",
            "last_checked_at",
            "last_observation_at",
            "created_at",
            "updated_at",
        ]

    def validate_alert_on_change_pct(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Alert threshold must be between 0 and 100."
            )

        return value


# =============================================================================
# DATA SYNCHRONIZATION
# =============================================================================


class DataSyncJobSerializer(
    serializers.ModelSerializer
):
    duration_seconds = serializers.SerializerMethodField()

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
            "duration_seconds",
            "error_message",
            "metadata",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "start_time",
            "end_time",
            "duration_seconds",
            "updated_at",
        ]

    def validate_scenes_discovered(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Scene count cannot be negative."
            )

        return value

    def validate_scenes_ingested(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Scene count cannot be negative."
            )

        return value

    def validate(self, attrs):
        discovered = attrs.get(
            "scenes_discovered",
            getattr(
                self.instance,
                "scenes_discovered",
                0,
            ),
        )

        ingested = attrs.get(
            "scenes_ingested",
            getattr(
                self.instance,
                "scenes_ingested",
                0,
            ),
        )

        if ingested > discovered:
            raise serializers.ValidationError(
                {
                    "scenes_ingested": (
                        "Ingested scenes cannot exceed "
                        "discovered scenes."
                    )
                }
            )

        return attrs

    def get_duration_seconds(self, obj):
        if not obj.start_time or not obj.end_time:
            return None

        return max(
            0.0,
            (
                obj.end_time - obj.start_time
            ).total_seconds(),
        )


# =============================================================================
# COMPACT READ-ONLY SERIALIZERS
# =============================================================================


class SatelliteSceneCompactSerializer(
    serializers.ModelSerializer
):
    """
    Small scene representation for timelines and map interfaces.
    """

    class Meta:
        model = SatelliteScene
        fields = [
            "id",
            "external_id",
            "provider",
            "collection",
            "platform",
            "mission",
            "acquisition_datetime",
            "sensor",
            "modality",
            "cloud_cover",
            "crs",
            "resolution",
            "thumbnail_url",
            "availability_status",
        ]


class AcquisitionCandidateCompactSerializer(
    serializers.ModelSerializer
):
    """
    Compact catalogue candidate representation.
    """

    class Meta:
        model = AcquisitionCandidate
        fields = [
            "id",
            "stac_item_id",
            "collection",
            "acquisition_date",
            "cloud_cover_pct",
            "footprint_geom",
            "selected",
            "thumbnail_url",
        ]


class TemporalObservationCompactSerializer(
    serializers.ModelSerializer
):
    """
    Compact temporal record for timeline/map interfaces.
    """

    scene_external_id = serializers.CharField(
        source="scene.external_id",
        read_only=True,
    )

    class Meta:
        model = TemporalObservation
        fields = [
            "id",
            "observation_date",
            "year",
            "month",
            "cloud_cover",
            "quality_score",
            "is_preferred",
            "thumbnail_url",
            "scene_external_id",
        ]


__all__ = [
    "DataProviderSerializer",
    "SatelliteCollectionSerializer",
    "AreaOfInterestSerializer",
    "SatelliteSceneSerializer",
    "SatelliteAssetSerializer",
    "AcquisitionRequestSerializer",
    "AcquisitionRequestCreateSerializer",
    "AcquisitionCandidateSerializer",
    "TemporalObservationSerializer",
    "ChangeEventSerializer",
    "DerivedRasterSerializer",
    "AOIMonitoringSerializer",
    "DataSyncJobSerializer",
    "SatelliteSceneCompactSerializer",
    "AcquisitionCandidateCompactSerializer",
    "TemporalObservationCompactSerializer",
]