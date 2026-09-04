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


class ExternalEvidence(models.Model):
    TIER_CHOICES = [
        ("TIER_1_GOV_AGENCY", "Tier 1: Government & Space Agencies"),
        ("TIER_2_ACADEMIC_RESEARCH", "Tier 2: Scientific & Academic Institutions"),
        ("TIER_3_TRUSTED_NEWS", "Tier 3: Reputable News & Verified Reports"),
        ("TIER_4_GENERAL_WEB", "Tier 4: General Web (Corroborating)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(
        "queries.Query", on_delete=models.CASCADE, related_name="external_evidence"
    )
    source_url = models.URLField(max_length=1024)
    source_domain = models.CharField(max_length=255, db_index=True)
    publisher = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=512)
    source_type = models.CharField(max_length=64, choices=TIER_CHOICES, default="TIER_1_GOV_AGENCY")
    trust_score = models.FloatField(default=0.85)
    published_date = models.DateField(null=True, blank=True)
    summary_facts = models.JSONField(default=list, help_text="List of atomic factual statements")
    content_hash = models.CharField(max_length=64, help_text="SHA-256 hash for audit integrity")
    retrieved_at = models.DateTimeField(auto_now_add=True)
    ttl_expires_at = models.DateTimeField(null=True, blank=True, help_text="Ephemeral TTL cache expiration")

    class Meta:
        ordering = ["-trust_score", "-retrieved_at"]

    def __str__(self):
        return f"{self.publisher} [{self.source_type}]: {self.title[:60]} (trust={self.trust_score:.2f})"
