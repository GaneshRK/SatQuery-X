from __future__ import annotations

from rest_framework import serializers

from .models import ImageAsset, ImagePair, ImageryArtifact


class ImageAssetSerializer(serializers.ModelSerializer):
    """
    API serializer for scientific imagery assets.

    Client applications may provide the original file and basic upload
    information. Scientific metadata is read-only because it must come from
    actual raster inspection / ingestion rather than user-entered values.
    """

    has_geospatial_reference = serializers.BooleanField(
        read_only=True
    )

    has_valid_dimensions = serializers.BooleanField(
        read_only=True
    )

    has_wgs84_bounds = serializers.BooleanField(
        read_only=True
    )

    class Meta:
        model = ImageAsset
        fields = "__all__"

        read_only_fields = (
            # Identity / ownership
            "id",
            "session",

            # Raster metadata discovered during ingestion
            "width",
            "height",
            "band_count",
            "dtype",

            # Geospatial metadata
            "crs",
            "affine_transform",
            "bounds_native",
            "bounds_wgs84",
            "resolution_m",
            "is_georeferenced",

            # Sensor / modality must be determined from actual metadata
            # or explicitly verified ingestion information.
            "sensor",
            "modality",

            # Acquisition metadata discovered from the source where
            # available.
            "acquisition_date",
            "cloud_cover_pct",

            # Generated assets / processing state
            "preview_url",
            "processing_status",
            "validation_report",

            # Audit / provenance
            "provenance",
            "created_at",

            # Computed API properties
            "has_geospatial_reference",
            "has_valid_dimensions",
            "has_wgs84_bounds",
        )

    def validate(self, attrs):
        """
        Validate user-supplied upload metadata without allowing the client
        to override scientific metadata.
        """

        uploaded_file = attrs.get("file")

        if uploaded_file is not None:
            if getattr(uploaded_file, "size", 0) <= 0:
                raise serializers.ValidationError(
                    {"file": "The uploaded file is empty."}
                )

        original_filename = attrs.get("original_filename")

        if original_filename is not None:
            cleaned = str(original_filename).strip()

            if not cleaned:
                raise serializers.ValidationError(
                    {
                        "original_filename":
                        "A valid original filename is required."
                    }
                )

            if len(cleaned) > 255:
                raise serializers.ValidationError(
                    {
                        "original_filename":
                        "Filename cannot exceed 255 characters."
                    }
                )

        return attrs


class ImagePairSerializer(serializers.ModelSerializer):
    """
    API serializer for image-pair analysis.

    Pair compatibility and coregistration are server-derived and therefore
    cannot be changed directly by the client.
    """

    image_a_detail = ImageAssetSerializer(
        source="image_a",
        read_only=True,
    )

    image_b_detail = ImageAssetSerializer(
        source="image_b",
        read_only=True,
    )

    class Meta:
        model = ImagePair

        fields = "__all__"

        read_only_fields = (
            "id",

            # Scientific validation results
            "compatibility_status",
            "compatibility_report",
            "coregistration_status",

            # Generated/coregistered files
            "coregistered_a_file",
            "coregistered_b_file",

            "created_at",

            # Nested details are always read-only
            "image_a_detail",
            "image_b_detail",
        )

    def validate(self, attrs):
        image_a = attrs.get("image_a")
        image_b = attrs.get("image_b")

        if image_a is not None and image_b is not None:
            if image_a.pk == image_b.pk:
                raise serializers.ValidationError(
                    {
                        "image_b":
                        "Image A and Image B must be different assets."
                    }
                )

            if image_a.session_id != image_b.session_id:
                raise serializers.ValidationError(
                    {
                        "image_b":
                        "Both imagery assets must belong to the same session."
                    }
                )

        pair_type = attrs.get("pair_type")

        if pair_type not in {
            "BI_TEMPORAL",
            "CROSS_MODAL",
        }:
            raise serializers.ValidationError(
                {
                    "pair_type":
                    "Unsupported imagery pair type."
                }
            )

        return attrs


class ImageryArtifactSerializer(serializers.ModelSerializer):
    """
    Serializer for derived imagery artifacts.

    Artifacts can represent browser previews, thumbnails, scientific masks,
    GeoJSON outputs, or evidence dossiers.
    """

    class Meta:
        model = ImageryArtifact

        fields = "__all__"

        read_only_fields = (
            "id",
            "created_at",
        )

    def validate(self, attrs):
        image_asset = attrs.get("image_asset")
        image_pair = attrs.get("image_pair")

        if not image_asset and not image_pair:
            raise serializers.ValidationError(
                "An artifact must belong to an image asset or an image pair."
            )

        width = attrs.get("width")
        height = attrs.get("height")

        if width is not None and width <= 0:
            raise serializers.ValidationError(
                {"width": "Width must be greater than zero."}
            )

        if height is not None and height <= 0:
            raise serializers.ValidationError(
                {"height": "Height must be greater than zero."}
            )

        bounds = attrs.get("bounds")

        if bounds is not None:
            if not isinstance(bounds, (list, tuple)):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "Bounds must be [west, south, east, north]."
                    }
                )

            if len(bounds) != 4:
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "Bounds must contain exactly four values."
                    }
                )

            try:
                numeric_bounds = [float(value) for value in bounds]
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "All bound values must be numeric."
                    }
                )

            west, south, east, north = numeric_bounds

            if west > east:
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "West must not be greater than east."
                    }
                )

            if south > north:
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "South must not be greater than north."
                    }
                )

            if not (-180 <= west <= 180):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "West must be between -180 and 180."
                    }
                )

            if not (-180 <= east <= 180):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "East must be between -180 and 180."
                    }
                )

            if not (-90 <= south <= 90):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "South must be between -90 and 90."
                    }
                )

            if not (-90 <= north <= 90):
                raise serializers.ValidationError(
                    {
                        "bounds":
                        "North must be between -90 and 90."
                    }
                )

        return attrs