from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Organization, Project, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tier", "created_at")
    list_filter = ("tier", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "created_at", "updated_at")
    list_filter = ("organization", "created_at")
    search_fields = ("name", "description", "organization__name")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "organization", "is_staff", "is_active", "date_joined")
    list_filter = ("role", "organization", "is_staff", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("SatQuery Roles & Multi-Tenancy", {"fields": ("role", "organization")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("SatQuery Roles & Multi-Tenancy", {"fields": ("role", "organization")}),
    )
