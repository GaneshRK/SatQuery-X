"""
Django admin configuration for SatQuery-X query execution.
"""

from __future__ import annotations

from django.contrib import admin

from .models import ExecutionStep, Query


# ============================================================================
# Execution step inline
# ============================================================================

class ExecutionStepInline(admin.TabularInline):
    model = ExecutionStep

    extra = 0

    can_delete = False

    readonly_fields = (
        "id",
        "step_number",
        "tool_name",
        "agent_type",
        "model_version",
        "parameters",
        "input_refs",
        "output_ref",
        "evidence_refs",
        "status",
        "latency_ms",
        "retry_count",
        "started_at",
        "completed_at",
        "error",
    )

    fields = (
        "step_number",
        "tool_name",
        "agent_type",
        "model_version",
        "status",
        "latency_ms",
        "retry_count",
        "started_at",
        "completed_at",
        "error",
    )

    ordering = (
        "step_number",
    )


# ============================================================================
# Query admin
# ============================================================================

@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session",
        "detected_mode",
        "detected_task",
        "status",
        "clarification_required",
        "confidence",
        "created_at",
        "completed_at",
    )

    list_filter = (
        "detected_mode",
        "detected_task",
        "status",
        "clarification_required",
        "created_at",
    )

    search_fields = (
        "id",
        "text",
        "answer",
        "error",
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "id",
        "created_at",
        "completed_at",
        "answer_contract_preview",
    )

    autocomplete_fields = (
        "session",
        "user",
        "image",
        "image_pair",
    )

    filter_horizontal = (
        "input_assets",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "id",
                    "user",
                    "session",
                )
            },
        ),
        (
            "Request",
            {
                "fields": (
                    "text",
                    "image",
                    "image_pair",
                    "input_assets",
                )
            },
        ),
        (
            "Planner / Routing",
            {
                "fields": (
                    "detected_mode",
                    "detected_task",
                    "status",
                    "plan",
                    "structured_plan",
                )
            },
        ),
        (
            "Conversation Context",
            {
                "fields": (
                    "context_snapshot",
                    "follow_up_questions",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Evidence",
            {
                "fields": (
                    "evidence_graph",
                    "evidence_bundle",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Answer",
            {
                "fields": (
                    "answer",
                    "confidence",
                    "clarification_required",
                    "clarification",
                    "answer_contract_preview",
                )
            },
        ),
        (
            "Execution Trace",
            {
                "fields": (
                    "answer_trace",
                    "error",
                    "created_at",
                    "completed_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    inlines = [
        ExecutionStepInline,
    ]

    def answer_contract_preview(self, obj):
        """
        Lightweight admin preview.

        The API serializer remains the authoritative representation used by
        the frontend. This method intentionally avoids executing analysis.
        """

        if not obj:
            return {}

        return {
            "answer_available": bool(
                obj.answer
                and obj.answer.strip()
            ),
            "task": obj.detected_task,
            "mode": obj.detected_mode,
            "status": obj.status,
            "confidence": obj.confidence,
            "clarification_required": (
                obj.clarification_required
            ),
            "evidence_available": bool(
                obj.evidence_bundle
                or obj.evidence_graph
            ),
            "trace_steps": (
                obj.execution_steps.count()
            ),
        }

    answer_contract_preview.short_description = (
        "Answer Contract Preview"
    )


# ============================================================================
# Execution step admin
# ============================================================================

@admin.register(ExecutionStep)
class ExecutionStepAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "query",
        "step_number",
        "tool_name",
        "agent_type",
        "model_version",
        "status",
        "latency_ms",
        "retry_count",
        "started_at",
        "completed_at",
    )

    list_filter = (
        "status",
        "tool_name",
        "agent_type",
        "model_version",
        "started_at",
        "completed_at",
    )

    search_fields = (
        "id",
        "query__id",
        "query__text",
        "tool_name",
        "agent_type",
        "model_version",
        "error",
    )

    readonly_fields = (
        "id",
        "query",
        "step_number",
        "tool_name",
        "agent_type",
        "model_version",
        "parameters",
        "input_refs",
        "output_ref",
        "evidence_refs",
        "status",
        "latency_ms",
        "retry_count",
        "started_at",
        "completed_at",
        "error",
    )

    fieldsets = (
        (
            "Execution",
            {
                "fields": (
                    "id",
                    "query",
                    "step_number",
                    "tool_name",
                    "agent_type",
                    "model_version",
                    "status",
                )
            },
        ),
        (
            "Inputs / Outputs",
            {
                "fields": (
                    "parameters",
                    "input_refs",
                    "output_ref",
                    "evidence_refs",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Performance",
            {
                "fields": (
                    "latency_ms",
                    "retry_count",
                    "started_at",
                    "completed_at",
                )
            },
        ),
        (
            "Failure",
            {
                "fields": (
                    "error",
                )
            },
        ),
    )

    ordering = (
        "query",
        "step_number",
    )