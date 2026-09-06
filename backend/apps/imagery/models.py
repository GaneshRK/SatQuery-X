import uuid
from django.db import models


def image_upload_path(instance, filename):
    return f"sessions/{instance.session_id}/images/{uuid.uuid4()}_{filename}"


class ImageAsset(models.Model):
    FORMAT_CHOICES = [
        ("GEOTIFF", "GeoTIFF"),
        ("TIFF", "TIFF"),
        ("PNG", "PNG"),
        ("JPEG", "JPEG"),
    ]
    SENSOR_CHOICES = [
        ("SENTINEL-2", "Sentinel-2"),
        ("SENTINEL-1", "Sentinel-1"),
        ("CARTOSAT-2S", "Cartosat-2S"),
        ("RISAT", "RISAT"),
        ("UNKNOWN", "Unknown"),
    ]
    MODALITY_CHOICES = [
        ("OPTICAL", "Optical"),
        ("MULTISPECTRAL", "Multispectral"),
        ("SAR", "Synthetic Aperture Radar"),
        ("UNKNOWN", "Unknown"),
    ]
    STATUS_CHOICES = [
        ("UPLOADED", "Uploaded"),
        ("VALIDATING", "Validating"),
        ("VALIDATED", "Validated"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="imagery_assets"
    )
    file = models.FileField(upload_to=image_upload_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, default="application/octet-stream")
    file_format = models.CharField(max_length=32, choices=FORMAT_CHOICES, default="GEOTIFF")
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    band_count = models.IntegerField(default=1)
    dtype = models.CharField(max_length=64, default="uint8")
    crs = models.CharField(max_length=255, null=True, blank=True)
    affine_transform = models.JSONField(null=True, blank=True)
    bounds_native = models.JSONField(null=True, blank=True)
    bounds_wgs84 = models.JSONField(null=True, blank=True)
    resolution_m = models.FloatField(null=True, blank=True)
    sensor = models.CharField(max_length=64, choices=SENSOR_CHOICES, default="UNKNOWN")
    modality = models.CharField(max_length=64, choices=MODALITY_CHOICES, default="OPTICAL")
    acquisition_date = models.DateField(null=True, blank=True)
    cloud_cover_pct = models.FloatField(null=True, blank=True)
    is_georeferenced = models.BooleanField(default=False)
    preview_url = models.CharField(max_length=512, null=True, blank=True)
    processing_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="UPLOADED")
    validation_report = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.sensor}, {self.modality})"


class ImagePair(models.Model):
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="image_pairs"
    )
    image_a = models.ForeignKey(
        ImageAsset, on_delete=models.CASCADE, related_name="pairs_as_first"
    )
    image_b = models.ForeignKey(
        ImageAsset, on_delete=models.CASCADE, related_name="pairs_as_second"
    )
    pair_type = models.CharField(max_length=32, choices=PAIR_TYPE_CHOICES)
    compatibility_status = models.CharField(
        max_length=32, choices=COMPATIBILITY_CHOICES, default="PENDING"
    )
    compatibility_report = models.JSONField(default=dict, blank=True)
    coregistration_status = models.CharField(
        max_length=32, choices=COREGISTRATION_CHOICES, default="NOT_NEEDED"
    )
    coregistered_a_file = models.FileField(upload_to="coregistered/", null=True, blank=True)
    coregistered_b_file = models.FileField(upload_to="coregistered/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pair {self.pair_type}: {self.image_a.original_filename} & {self.image_b.original_filename}"


class ImageryArtifact(models.Model):
    """
    Explicitly tracks all scientific and visual asset derivatives for an observation or analysis pair.
    Decouples raw scientific GeoTIFFs from browser-native visual assets (RGB WebP/PNG, Thumbnails, Change Masks, GeoJSON).
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image_asset = models.ForeignKey(
        ImageAsset, on_delete=models.CASCADE, related_name="artifacts", null=True, blank=True
    )
    image_pair = models.ForeignKey(
        ImagePair, on_delete=models.CASCADE, related_name="pair_artifacts", null=True, blank=True
    )
    artifact_type = models.CharField(max_length=50, choices=ARTIFACT_TYPES)
    file = models.FileField(upload_to="artifacts/")
    mime_type = models.CharField(max_length=100, default="image/webp")
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    bounds = models.JSONField(null=True, blank=True, help_text="Bounding envelope [west, south, east, north]")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.artifact_type} ({self.file.name})"
