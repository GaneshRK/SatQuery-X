from rest_framework import serializers
from .models import ImageAsset, ImagePair


class ImageAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageAsset
        fields = "__all__"
        read_only_fields = (
            "id",
            "width",
            "height",
            "band_count",
            "dtype",
            "crs",
            "affine_transform",
            "bounds_native",
            "bounds_wgs84",
            "resolution_m",
            "sensor",
            "modality",
            "is_georeferenced",
            "preview_url",
            "processing_status",
            "validation_report",
            "created_at",
        )


class ImagePairSerializer(serializers.ModelSerializer):
    image_a_detail = ImageAssetSerializer(source="image_a", read_only=True)
    image_b_detail = ImageAssetSerializer(source="image_b", read_only=True)

    class Meta:
        model = ImagePair
        fields = "__all__"
        read_only_fields = (
            "id",
            "compatibility_status",
            "compatibility_report",
            "coregistration_status",
            "created_at",
        )
