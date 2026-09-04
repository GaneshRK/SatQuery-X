import uuid
from django.db import models


class EvidenceRegion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(
        "queries.Query", on_delete=models.CASCADE, related_name="evidence_regions"
    )
    # GeoJSON polygon/multipolygon geometry representation (SRID 4326)
    geojson_geometry = models.JSONField()
    class_name = models.CharField(max_length=128, default="detected_feature")
    confidence = models.FloatField(default=0.0)
    area_m2 = models.FloatField(default=0.0)
    area_ha = models.FloatField(default=0.0)
    area_km2 = models.FloatField(default=0.0)
    source_step = models.ForeignKey(
        "queries.ExecutionStep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="produced_evidence",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-area_km2"]

    def __str__(self):
        return f"{self.class_name} ({self.area_km2:.3f} km², conf={self.confidence:.2f})"
