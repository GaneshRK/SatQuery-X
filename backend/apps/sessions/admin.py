from django.contrib import admin
from .models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "project", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at", "project")
    search_fields = ("name", "user__username", "id", "project__name")
    readonly_fields = ("id", "created_at", "updated_at")
