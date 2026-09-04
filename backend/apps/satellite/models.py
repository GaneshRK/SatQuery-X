import uuid
from django.db import models


class AcquisitionRequest(models.Model):
    SENSOR_CHOICES = [
        ("SENTINEL-1", "Sentinel-1 (SAR)"),
        ("SENTINEL-2", "Sentinel-2 (Optical L2A)"),
        ("BOTH", "Both (Optical + SAR)"),
    ]
    STATUS_CHOICES = [
        ("SEARCHING", "Searching"),
        ("RESULTS_READY", "Results Ready"),
        ("RETRIEVING", "Retrieving"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="satellite_requests"
    )
    aoi_geometry = models.JSONField()
    sensor = models.CharField(max_length=32, choices=SENSOR_CHOICES, default="SENTINEL-2")
    date_start = models.DateField()
    date_end = models.DateField()
    max_cloud_cover = models.FloatField(null=True, blank=True, default=20.0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="SEARCHING")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AcquisitionRequest {self.id} ({self.sensor}): {self.status}"


class AcquisitionCandidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        AcquisitionRequest, on_delete=models.CASCADE, related_name="candidates"
    )
    stac_item_id = models.CharField(max_length=255)
    collection = models.CharField(max_length=128)
    acquisition_date = models.DateField()
    cloud_cover_pct = models.FloatField(null=True, blank=True)
    footprint_geom = models.JSONField()
    selected = models.BooleanField(default=False)
    retrieved_image = models.ForeignKey(
        "imagery.ImageAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="from_candidate"
    )

    class Meta:
        ordering = ["cloud_cover_pct", "-acquisition_date"]

    def __str__(self):
        return f"{self.stac_item_id} ({self.collection}, cloud={self.cloud_cover_pct}%)"
