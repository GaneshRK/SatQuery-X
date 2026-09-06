from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


def image_upload_path(instance: "ImageAsset", filename: str) -> str:
    """
    Store original uploaded imagery under the owning analysis session.

    UUID prefix prevents filename collisions and avoids trusting the
    user-provided filename as a storage identifier.
    """
    safe_name = (filename or "imagery").replace("\\", "_").replace("/", "_")
    return f"sessions/{instance.session_id}/images/{uuid.uuid4()}_{safe_name}"


class ImageAsset(models.Model):
    """
    Scientific imagery asset uploaded or derived inside an analysis session.

    Important design rule:
    - Metadata is populated from the actual raster/file whenever possible.
    - Unknown metadata remains NULL/UNKNOWN.
    - The system must never fabricate CRS, bounds, resolution, sensor,
      acquisition date, or other scientific properties.
    """

    FORMAT_CHOICES = [
        ("GEOTIFF", "GeoTIFF"),
        ("TIFF", "TIFF"),
        ("PNG", "PNG"),
        ("JPEG", "JPEG"),
    ]

    SENSOR_CHOICES = [
        ("UNKNOWN", "Unknown"),
        ("SENTINEL-1", "Sentinel-1"),
        ("SENTINEL-2", "Sentinel-2"),
        ("CARTOSAT-2S", "Cartosat-2S"),
        ("RISAT", "RISAT"),
    ]

    MODALITY_CHOICES = [
        ("UNKNOWN", "Unknown"),
        ("OPTICAL", "Optical"),
        ("MULTISPECTRAL", "Multispectral"),
        ("SAR", "Synthetic Aperture Radar"),
        ("THERMAL", "Thermal"),
        ("PAN", "Panchromatic"),
        ("HYPERSPECTRAL", "Hyperspectral"),
    ]

    STATUS_CHOICES = [
        ("UPLOADED", "Uploaded"),
        ("VALIDATING", "Validating"),
        ("VALIDATED", "Validated"),
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
        related_name="imagery_assets",
    )

    file = models.FileField(
        upload_to=image_upload_path,
    )

    original_filename = models.CharField(
        max_length=255,
    )

    content_type = models.CharField(
        max_length=128,
        default="application/octet-stream",
    )

    file_format = models.CharField(
        max_length=32,
        choices=FORMAT_CHOICES,
        default="GEOTIFF",
    )

    # ------------------------------------------------------------------
    # Raster dimensions
    # ------------------------------------------------------------------

    width = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    height = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    band_count = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    dtype = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Geospatial metadata
    # ------------------------------------------------------------------

    # CRS is stored as a string representation such as:
    # "EPSG:4326", "EPSG:32643", or WKT.
    #
    # NULL means the source imagery does not provide usable CRS metadata.
    crs = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    # Affine transform represented as JSON-compatible values.
    #
    # Example:
    # [a, b, c, d, e, f]
    #
    # NULL means no trustworthy transform is available.
    affine_transform = models.JSONField(
        null=True,
        blank=True,
    )

    # Native CRS bounds:
    # {
    #     "left": ...,
    #     "bottom": ...,
    #     "right": ...,
    #     "top": ...
    # }
    bounds_native = models.JSONField(
        null=True,
        blank=True,
    )

    # WGS84 bounds only when a real CRS transformation was possible.
    #
    # {
    #     "west": ...,
    #     "south": ...,
    #     "east": ...,
    #     "north": ...
    # }
    bounds_wgs84 = models.JSONField(
        null=True,
        blank=True,
    )

    # Pixel resolution in metres when it can actually be determined.
    resolution_m = models.FloatField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Sensor / modality
    # ------------------------------------------------------------------

    sensor = models.CharField(
        max_length=64,
        choices=SENSOR_CHOICES,
        default="UNKNOWN",
    )

    modality = models.CharField(
        max_length=64,
        choices=MODALITY_CHOICES,
        default="UNKNOWN",
    )

    # ------------------------------------------------------------------
    # Acquisition metadata
    # ------------------------------------------------------------------

    acquisition_date = models.DateField(
        null=True,
        blank=True,
    )

    cloud_cover_pct = models.FloatField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Processing state
    # ------------------------------------------------------------------

    is_georeferenced = models.BooleanField(
        default=False,
    )

    preview_url = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
    )

    processing_status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="UPLOADED",
    )

    # Machine-readable validation / ingestion report.
    #
    # Example:
    # {
    #     "valid": true,
    #     "warnings": [],
    #     "errors": [],
    #     "metadata_source": "rasterio"
    # }
    validation_report = models.JSONField(
        default=dict,
        blank=True,
    )

    # Full provenance chain.
    #
    # This should record things such as:
    # - upload
    # - parent asset
    # - preprocessing operation
    # - AOI clipping
    # - source metadata
    # - processing software/version
    provenance = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["sensor"]),
            models.Index(fields=["modality"]),
            models.Index(fields=["acquisition_date"]),
            models.Index(fields=["is_georeferenced"]),
        ]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def has_valid_dimensions(self) -> bool:
        return bool(
            self.width is not None
            and self.height is not None
            and self.width > 0
            and self.height > 0
        )

    @property
    def has_geospatial_reference(self) -> bool:
        return bool(
            self.is_georeferenced
            and self.crs
            and self.affine_transform
        )

    @property
    def has_wgs84_bounds(self) -> bool:
        return isinstance(self.bounds_wgs84, dict) and all(
            key in self.bounds_wgs84
            for key in ("west", "south", "east", "north")
        )

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        # --------------------------------------------------------------
        # Dimensions
        # --------------------------------------------------------------

        if self.width is not None and self.width <= 0:
            errors["width"] = "Width must be greater than zero."

        if self.height is not None and self.height <= 0:
            errors["height"] = "Height must be greater than zero."

        if self.band_count is not None and self.band_count <= 0:
            errors["band_count"] = "Band count must be greater than zero."

        # --------------------------------------------------------------
        # Resolution
        # --------------------------------------------------------------

        if self.resolution_m is not None:
            if self.resolution_m <= 0:
                errors["resolution_m"] = (
                    "Resolution must be greater than zero when provided."
                )

        # --------------------------------------------------------------
        # Cloud cover
        # --------------------------------------------------------------

        if self.cloud_cover_pct is not None:
            if not 0 <= self.cloud_cover_pct <= 100:
                errors["cloud_cover_pct"] = (
                    "Cloud cover must be between 0 and 100 percent."
                )

        # --------------------------------------------------------------
        # Georeferencing consistency
        # --------------------------------------------------------------

        if self.is_georeferenced:
            if not self.crs:
                errors["crs"] = (
                    "A georeferenced asset must contain a CRS."
                )

            if not self.affine_transform:
                errors["affine_transform"] = (
                    "A georeferenced asset must contain an affine transform."
                )

        # Never claim WGS84 bounds without a CRS.
        if self.bounds_wgs84 and not self.crs:
            errors["bounds_wgs84"] = (
                "WGS84 bounds require trustworthy CRS metadata."
            )

        # --------------------------------------------------------------
        # Bounds validation
        # --------------------------------------------------------------

        for field_name in ("bounds_native", "bounds_wgs84"):
            value = getattr(self, field_name)

            if value is None:
                continue

            if not isinstance(value, dict):
                errors[field_name] = (
                    "Bounds must be stored as a JSON object."
                )
                continue

            required_keys = (
                ("left", "bottom", "right", "top")
                if field_name == "bounds_native"
                else ("west", "south", "east", "north")
            )

            missing = [
                key for key in required_keys
                if key not in value
            ]

            if missing:
                errors[field_name] = (
                    f"Missing bound values: {', '.join(missing)}."
                )

        if errors:
            raise ValidationError(errors)


class ImagePair(models.Model):
    """
    Relationship between two imagery assets used for comparison/fusion.

    BI_TEMPORAL:
        Same/sufficiently compatible observation type at different times.

    CROSS_MODAL:
        Different modalities, e.g. optical + SAR.

    Pair compatibility is computed by the imagery/geospatial pipeline;
    it is never assumed merely because two files were uploaded.
    """

    PAIR_TYPE_CHOICES = [
        ("CROSS_MODAL", "Cross-Modal (Optical + SAR)"),
        ("BI_TEMPORAL", "Bi-Temporal (Time T1 + T2)"),
    ]

    COMPATIBILITY_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPATIBLE", "Compatible"),
        ("INCOMPATIBLE", "Incompatible"),
    ]

    COREGISTRATION_CHOICES = [
        ("NOT_NEEDED", "Not Needed"),
        ("PENDING", "Pending"),
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
        related_name="image_pairs",
    )

    image_a = models.ForeignKey(
        ImageAsset,
        on_delete=models.CASCADE,
        related_name="pairs_as_first",
    )

    image_b = models.ForeignKey(
        ImageAsset,
        on_delete=models.CASCADE,
        related_name="pairs_as_second",
    )

    pair_type = models.CharField(
        max_length=32,
        choices=PAIR_TYPE_CHOICES,
    )

    compatibility_status = models.CharField(
        max_length=32,
        choices=COMPATIBILITY_CHOICES,
        default="PENDING",
    )

    compatibility_report = models.JSONField(
        default=dict,
        blank=True,
    )

    coregistration_status = models.CharField(
        max_length=32,
        choices=COREGISTRATION_CHOICES,
        default="NOT_NEEDED",
    )

    coregistered_a_file = models.FileField(
        upload_to="coregistered/",
        null=True,
        blank=True,
    )

    coregistered_b_file = models.FileField(
        upload_to="coregistered/",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["pair_type"]),
            models.Index(fields=["compatibility_status"]),
            models.Index(fields=["coregistration_status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(image_a=models.F("image_b")),
                name="imagery_pair_distinct_assets",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.pair_type}: "
            f"{self.image_a.original_filename} ↔ "
            f"{self.image_b.original_filename}"
        )

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        if self.image_a_id and self.image_b_id:
            if self.image_a_id == self.image_b_id:
                errors["image_b"] = (
                    "An imagery pair must contain two different assets."
                )

        # Both assets must belong to the same analysis session.
        if (
            self.session_id
            and self.image_a_id
            and self.image_a.session_id != self.session_id
        ):
            errors["image_a"] = (
                "Image A does not belong to the selected session."
            )

        if (
            self.session_id
            and self.image_b_id
            and self.image_b.session_id != self.session_id
        ):
            errors["image_b"] = (
                "Image B does not belong to the selected session."
            )

        if errors:
            raise ValidationError(errors)


class ImageryArtifact(models.Model):
    """
    Derived scientific or browser-facing asset.

    Raw imagery and derived artifacts are intentionally separated.

    Examples:
        GEOTIFF
        RGB_PREVIEW
        THUMBNAIL
        FALSE_COLOR
        CHANGE_MASK
        CHANGE_PROBABILITY
        GEOJSON
        EVIDENCE_JSON
    """

    ARTIFACT_TYPES = [
        ("GEOTIFF", "GeoTIFF"),
        ("RGB_PREVIEW", "RGB Preview"),
        ("THUMBNAIL", "Thumbnail"),
        ("FALSE_COLOR", "False Color"),
        ("CHANGE_MASK", "Change Mask"),
        ("CHANGE_PROBABILITY", "Change Probability"),
        ("GEOJSON", "GeoJSON Vector Polygons"),
        ("EVIDENCE_JSON", "Evidence JSON Dossier"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    image_asset = models.ForeignKey(
        ImageAsset,
        on_delete=models.CASCADE,
        related_name="artifacts",
        null=True,
        blank=True,
    )

    image_pair = models.ForeignKey(
        ImagePair,
        on_delete=models.CASCADE,
        related_name="pair_artifacts",
        null=True,
        blank=True,
    )

    artifact_type = models.CharField(
        max_length=50,
        choices=ARTIFACT_TYPES,
    )

    file = models.FileField(
        upload_to="artifacts/",
    )

    mime_type = models.CharField(
        max_length=100,
        default="application/octet-stream",
    )

    width = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    height = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Bounds are only populated when the artifact is genuinely
    # georeferenced.
    #
    # [west, south, east, north]
    bounds = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "WGS84 bounding envelope "
            "[west, south, east, north] when genuinely available."
        ),
    )

    # Additional provenance for the derivative itself.
    provenance = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["image_asset", "-created_at"]),
            models.Index(fields=["image_pair", "-created_at"]),
            models.Index(fields=["artifact_type"]),
        ]

    def __str__(self) -> str:
        filename = self.file.name if self.file else "unstored"
        return f"{self.artifact_type} ({filename})"

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        # An artifact must have a scientific/visual parent.
        if not self.image_asset_id and not self.image_pair_id:
            errors["image_asset"] = (
                "Artifact must belong to an image asset or image pair."
            )

        # Width/height must be positive if provided.
        if self.width is not None and self.width <= 0:
            errors["width"] = "Width must be greater than zero."

        if self.height is not None and self.height <= 0:
            errors["height"] = "Height must be greater than zero."

        # Validate WGS84 bounds structure.
        if self.bounds is not None:
            if not isinstance(self.bounds, (list, tuple)):
                errors["bounds"] = (
                    "Bounds must be a four-value array."
                )
            elif len(self.bounds) != 4:
                errors["bounds"] = (
                    "Bounds must contain "
                    "[west, south, east, north]."
                )

        if errors:
            raise ValidationError(errors)