from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


class EvidenceRegion(models.Model):
    """
    Evidence produced by an actual SatQuery-X analysis step.

    A region must represent geometry produced by an upstream analysis
    pipeline. The model intentionally does not create coordinates,
    measurements, or confidence values on its own.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    query = models.ForeignKey(
        "queries.Query",
        on_delete=models.CASCADE,
        related_name="evidence_regions",
    )

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    geojson_geometry = models.JSONField(
        help_text=(
            "GeoJSON geometry produced from verified source imagery. "
            "Coordinates must not be fabricated for unreferenced imagery."
        )
    )

    # ------------------------------------------------------------------
    # Semantic classification
    # ------------------------------------------------------------------

    class_name = models.CharField(
        max_length=128,
        default="detected_feature",
    )

    # ------------------------------------------------------------------
    # Analysis confidence
    # ------------------------------------------------------------------
    #
    # NULL means confidence was not supplied by the upstream model.
    # It is intentionally different from 0.0.
    # ------------------------------------------------------------------

    confidence = models.FloatField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    #
    # NULL means "not measured".
    # Zero means an actual measured zero.
    # ------------------------------------------------------------------

    area_m2 = models.FloatField(
        null=True,
        blank=True,
    )

    area_ha = models.FloatField(
        null=True,
        blank=True,
    )

    area_km2 = models.FloatField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    source_step = models.ForeignKey(
        "queries.ExecutionStep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="produced_evidence",
    )

    # ------------------------------------------------------------------
    # Additional provenance / measurement metadata
    # ------------------------------------------------------------------

    provenance = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Structured provenance describing the source imagery, "
            "model/tool, processing operation, and measurement origin."
        ),
    )

    measurements = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Actual measurements produced by the analysis pipeline. "
            "Do not use this field for generated estimates."
        ),
    )

    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Additional structured attributes associated with this "
            "evidence region."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at", "-area_km2"]

    def clean(self) -> None:
        """
        Validate evidence without inventing missing values.
        """

        errors: dict[str, str] = {}

        if not isinstance(self.geojson_geometry, dict):
            errors["geojson_geometry"] = (
                "Geometry must be a GeoJSON object."
            )

        if isinstance(self.geojson_geometry, dict):
            geometry_type = self.geojson_geometry.get("type")

            if geometry_type not in {
                "Point",
                "MultiPoint",
                "LineString",
                "MultiLineString",
                "Polygon",
                "MultiPolygon",
                "GeometryCollection",
            }:
                errors["geojson_geometry"] = (
                    "Geometry must contain a valid GeoJSON geometry type."
                )

        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                errors["confidence"] = (
                    "Confidence must be between 0 and 1."
                )

        for field_name in (
            "area_m2",
            "area_ha",
            "area_km2",
        ):
            value = getattr(self, field_name)

            if value is not None and value < 0:
                errors[field_name] = (
                    "Area measurements cannot be negative."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        area = (
            f"{self.area_km2:.3f} km²"
            if self.area_km2 is not None
            else "area unavailable"
        )

        confidence = (
            f"{self.confidence:.2f}"
            if self.confidence is not None
            else "n/a"
        )

        return (
            f"{self.class_name} "
            f"({area}, conf={confidence})"
        )


class ExternalEvidence(models.Model):
    """
    Evidence obtained from an external web/scientific source.

    The record stores provenance and atomic factual statements extracted
    from the actual source. It does not represent model-generated facts.
    """

    TIER_CHOICES = [
        (
            "TIER_1_GOV_AGENCY",
            "Tier 1: Government & Space Agencies",
        ),
        (
            "TIER_2_ACADEMIC_RESEARCH",
            "Tier 2: Scientific & Academic Institutions",
        ),
        (
            "TIER_3_TRUSTED_NEWS",
            "Tier 3: Reputable News & Verified Reports",
        ),
        (
            "TIER_4_GENERAL_WEB",
            "Tier 4: General Web (Corroborating)",
        ),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    query = models.ForeignKey(
        "queries.Query",
        on_delete=models.CASCADE,
        related_name="external_evidence",
    )

    # ------------------------------------------------------------------
    # Source identity
    # ------------------------------------------------------------------

    source_url = models.URLField(
        max_length=1024,
    )

    source_domain = models.CharField(
        max_length=255,
        db_index=True,
    )

    publisher = models.CharField(
        max_length=255,
        blank=True,
    )

    title = models.CharField(
        max_length=512,
    )

    # ------------------------------------------------------------------
    # Source trust classification
    # ------------------------------------------------------------------

    source_type = models.CharField(
        max_length=64,
        choices=TIER_CHOICES,
        default="TIER_4_GENERAL_WEB",
    )

    # Nullable because trust may not have been evaluated yet.
    trust_score = models.FloatField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Publication / retrieval metadata
    # ------------------------------------------------------------------

    published_date = models.DateField(
        null=True,
        blank=True,
    )

    retrieved_at = models.DateTimeField(
        auto_now_add=True,
    )

    ttl_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Extracted source facts
    # ------------------------------------------------------------------

    summary_facts = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Atomic factual statements extracted from the actual source."
        ),
    )

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    content_hash = models.CharField(
        max_length=64,
        help_text=(
            "SHA-256 hash of the retrieved source content."
        ),
    )

    # ------------------------------------------------------------------
    # Additional provenance
    # ------------------------------------------------------------------

    provenance = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Additional retrieval and provenance metadata."
        ),
    )

    class Meta:
        ordering = [
            "-retrieved_at",
            "-trust_score",
        ]

    def clean(self) -> None:
        errors: dict[str, str] = {}

        if self.trust_score is not None:
            if not 0.0 <= self.trust_score <= 1.0:
                errors["trust_score"] = (
                    "Trust score must be between 0 and 1."
                )

        if not self.content_hash:
            errors["content_hash"] = (
                "A SHA-256 content hash is required."
            )

        if self.summary_facts is not None:
            if not isinstance(self.summary_facts, list):
                errors["summary_facts"] = (
                    "summary_facts must be a list."
                )

        if self.provenance is not None:
            if not isinstance(self.provenance, dict):
                errors["provenance"] = (
                    "provenance must be an object."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        publisher = self.publisher or self.source_domain

        tier = self.source_type

        trust = (
            f"{self.trust_score:.2f}"
            if self.trust_score is not None
            else "n/a"
        )

        return (
            f"{publisher} [{tier}]: "
            f"{self.title[:60]} "
            f"(trust={trust})"
        )