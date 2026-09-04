from django.contrib import admin
from .models import ImageAsset, ImagePair


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "session",
        "sensor",
        "modality",
        "file_format",
        "band_count",
        "resolution_m",
        "is_georeferenced",
        "processing_status",
        "created_at",
    )
    list_filter = ("sensor", "modality", "file_format", "processing_status", "is_georeferenced")
    search_fields = ("original_filename", "id", "session__name")
    readonly_fields = ("id", "created_at", "width", "height", "band_count", "crs", "affine_transform", "bounds_wgs84")


@admin.register(ImagePair)
class ImagePairAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "pair_type",
        "image_a",
        "image_b",
        "compatibility_status",
        "coregistration_status",
        "created_at",
    )
    list_filter = ("pair_type", "compatibility_status", "coregistration_status")
    search_fields = ("id", "session__name", "image_a__original_filename", "image_b__original_filename")
    readonly_fields = ("id", "created_at")
