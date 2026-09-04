from django.contrib import admin
from .models import ExecutionStep, Query


class ExecutionStepInline(admin.TabularInline):
    model = ExecutionStep
    extra = 0
    readonly_fields = ("step_number", "tool_name", "model_version", "status", "latency_ms", "started_at", "completed_at")
    can_delete = False


@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session",
        "detected_mode",
        "detected_task",
        "status",
        "confidence",
        "created_at",
    )
    list_filter = ("detected_mode", "detected_task", "status", "created_at")
    search_fields = ("id", "text", "answer", "user__username")
    readonly_fields = ("id", "created_at", "completed_at")
    inlines = [ExecutionStepInline]


@admin.register(ExecutionStep)
class ExecutionStepAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "query",
        "step_number",
        "tool_name",
        "model_version",
        "status",
        "latency_ms",
        "completed_at",
    )
    list_filter = ("status", "tool_name", "model_version")
    search_fields = ("query__id", "tool_name")
    readonly_fields = ("id", "started_at", "completed_at")
