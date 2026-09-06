from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "action",
        "target_type",
        "target_id",
    )

    list_filter = (
        "action",
        "target_type",
        "created_at",
    )

    search_fields = (
        "action",
        "target_type",
        "target_id",
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "id",
        "created_at",
        "user",
        "action",
        "target_type",
        "target_id",
        "metadata",
    )

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_per_page = 50

    def has_add_permission(self, request):
        """
        Audit records should be created by application code,
        not manually through Django Admin.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """
        Audit records are immutable.
        """
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Audit records should not be deleted through the admin UI.
        """
        return False