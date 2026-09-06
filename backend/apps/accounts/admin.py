from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Organization, Project, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "tier",
        "member_count",
        "project_count",
        "created_at",
    )

    list_filter = (
        "tier",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    readonly_fields = (
        "id",
        "created_at",
        "member_count",
        "project_count",
    )

    fieldsets = (
        (
            "Organization",
            {
                "fields": (
                    "id",
                    "name",
                    "slug",
                    "tier",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "member_count",
                    "project_count",
                    "created_at",
                )
            },
        ),
    )

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = "Members"

    def project_count(self, obj):
        return obj.projects.count()

    project_count.short_description = "Projects"


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "organization",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "description",
        "organization__name",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "organization",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "role",
        "organization",
        "is_staff",
        "is_active",
        "date_joined",
    )

    list_filter = (
        "role",
        "organization",
        "is_staff",
        "is_superuser",
        "is_active",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "organization__name",
    )

    ordering = (
        "username",
    )

    readonly_fields = (
        "date_joined",
        "last_login",
    )

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "SatQuery-X Access",
            {
                "fields": (
                    "role",
                    "organization",
                )
            },
        ),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "SatQuery-X Access",
            {
                "fields": (
                    "role",
                    "organization",
                )
            },
        ),
    )

    autocomplete_fields = (
        "organization",
    )