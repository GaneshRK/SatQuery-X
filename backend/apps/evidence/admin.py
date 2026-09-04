from django.contrib import admin
from .models import EvidenceRegion


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
    list_filter = ("class_name", "created_at")
    search_fields = ("id", "query__id", "class_name")
    readonly_fields = ("id", "created_at")
