from __future__ import annotations

from django.contrib import admin

from .models import ImageAsset, ImagePair, ImageryArtifact


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "session",
        "sensor",
        "modality",
        "file_format",
        "processing_status",
        "is_georeferenced",
        "created_at",
    )

    list_filter = (
        "processing_status",
        "sensor",
        "modality",
        "file_format",
        "is_georeferenced",
        "created_at",
    )

    search_fields = (
        "id",
        "original_filename",
        "session__id",
    )

    readonly_fields = (
        "id",
        "created_at",
        "width",
        "height",
        "band_count",
        "dtype",
        "crs",
        "affine_transform",
        "bounds_native",
        "bounds_wgs84",
        "resolution_m",
        "is_georeferenced",
        "validation_report",
        "provenance",
        "preview_url",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 50


@admin.register(ImagePair)
class ImagePairAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "image_a",
        "image_b",
        "pair_type",
        "compatibility_status",
        "coregistration_status",
        "created_at",
    )

    list_filter = (
        "pair_type",
        "compatibility_status",
        "coregistration_status",
        "created_at",
    )

    search_fields = (
        "id",
        "session__id",
        "image_a__original_filename",
        "image_b__original_filename",
    )

    readonly_fields = (
        "id",
        "compatibility_report",
        "coregistration_status",
        "coregistered_a_file",
        "coregistered_b_file",
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 50


@admin.register(ImageryArtifact)
class ImageryArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "image_asset",
        "artifact_type",
        "mime_type",
        "width",
        "height",
        "created_at",
    )

    list_filter = (
        "artifact_type",
        "mime_type",
        "created_at",
    )

    search_fields = (
        "id",
        "image_asset__id",
        "image_asset__original_filename",
    )

    readonly_fields = (
        "id",
        "created_at",
        "provenance",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 50