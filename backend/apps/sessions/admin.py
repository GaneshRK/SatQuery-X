"""
Django admin configuration for SatQuery-X sessions.
"""

from django.contrib import admin

from .models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    """
    Administrative interface for conversational analysis sessions.
    """

    list_display = (
        "id",
        "name",
        "user",
        "project",
        "status",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "status",
        "created_at",
        "updated_at",
        "project",
    )

    search_fields = (
        "id",
        "name",
        "user__username",
        "user__email",
        "project__name",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "user",
        "project",
    )

    ordering = (
        "-updated_at",
    )

    date_hierarchy = "created_at"

    list_per_page = 50

    fieldsets = (
        (
            "Session",
            {
                "fields": (
                    "id",
                    "name",
                    "status",
                    "user",
                    "project",
                )
            },
        ),
        (
            "Conversation",
            {
                "fields": (
                    "conversation_history",
                    "conversation_context",
                ),
                "description": (
                    "Durable conversational and geospatial context. "
                    "Scientific measurements must come from actual "
                    "analysis/evidence records."
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        """
        Keep Django's normal admin deletion permission behavior.
        """
        return super().has_delete_permission(request, obj)