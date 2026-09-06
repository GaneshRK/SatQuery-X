from django.contrib import admin

from .models import EvidenceRegion, ExternalEvidence


@admin.register(EvidenceRegion)
class EvidenceRegionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "query",
        "class_name",
        "confidence",
        "area_km2",
        "area_ha",
        "created_at",
    )

    list_filter = (
        "class_name",
        "created_at",
    )

    search_fields = (
        "id",
        "query__id",
        "class_name",
    )

    readonly_fields = (
        "id",
        "created_at",
    )


@admin.register(ExternalEvidence)
class ExternalEvidenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "publisher",
        "source_domain",
        "source_type",
        "trust_score",
        "retrieved_at",
        "ttl_expires_at",
    )

    list_filter = (
        "source_type",
        "retrieved_at",
    )

    search_fields = (
        "publisher",
        "title",
        "source_domain",
        "source_url",
    )

    readonly_fields = (
        "id",
        "content_hash",
        "retrieved_at",
    )