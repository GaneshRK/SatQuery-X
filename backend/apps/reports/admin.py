from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "query", "format", "status", "generated_at")
    list_filter = ("format", "status", "generated_at")
    search_fields = ("id", "session__name", "query__id")
    readonly_fields = ("id", "generated_at")
