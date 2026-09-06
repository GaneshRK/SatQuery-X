"""
Django admin configuration for SatQuery-X reports.
"""

from __future__ import annotations

from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """
    Administrative interface for generated intelligence reports.
    """

    list_display = (
        "id",
        "session",
        "query",
        "format",
        "status",
        "renderer_version",
        "generated_at",
        "completed_at",
    )

    list_filter = (
        "format",
        "status",
        "renderer_version",
        "generated_at",
        "completed_at",
    )

    search_fields = (
        "id",
        "session__name",
        "query__id",
        "query__text",
    )

    readonly_fields = (
        "id",
        "generated_at",
        "completed_at",
        "updated_at",
        "source_snapshot",
        "provenance",
        "renderer_version",
        "file",
    )

    list_select_related = (
        "session",
        "query",
    )

    ordering = (
        "-generated_at",
    )

    date_hierarchy = "generated_at"

    fieldsets = (
        (
            "Report",
            {
                "fields": (
                    "id",
                    "session",
                    "query",
                    "format",
                    "status",
                    "file",
                    "error",
                )
            },
        ),
        (
            "Provenance",
            {
                "fields": (
                    "renderer_version",
                    "source_snapshot",
                    "provenance",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "generated_at",
                    "completed_at",
                    "updated_at",
                )
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        """
        Keep the normal Django permission system.

        No custom deletion behavior is introduced here.
        """
        return super().has_delete_permission(request, obj)