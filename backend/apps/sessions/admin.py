from django.contrib import admin
from .models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "user__username", "id")
    readonly_fields = ("id", "created_at", "updated_at")
