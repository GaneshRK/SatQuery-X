"""
Serializers for SatQuery-X report generation and retrieval.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.queries.models import Query

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    """
    Read serializer for generated reports.

    Scientific values are exposed only when they already exist in the
    underlying query/evidence data.
    """

    file_url = serializers.SerializerMethodField()
    is_ready = serializers.ReadOnlyField()
    is_failed = serializers.ReadOnlyField()
    is_generating = serializers.ReadOnlyField()

    class Meta:
        model = Report
        fields = [
            "id",
            "session",
            "query",
            "format",
            "status",
            "error",
            "file",
            "file_url",
            "source_snapshot",
            "provenance",
            "renderer_version",
            "generated_at",
            "completed_at",
            "updated_at",
            "is_ready",
            "is_failed",
            "is_generating",
        ]
        read_only_fields = [
            "id",
            "status",
            "error",
            "file",
            "file_url",
            "source_snapshot",
            "provenance",
            "renderer_version",
            "generated_at",
            "completed_at",
            "updated_at",
            "is_ready",
            "is_failed",
            "is_generating",
        ]

    def get_file_url(self, obj):
        if not obj.file:
            return None

        request = self.context.get("request")

        try:
            url = obj.file.url
        except Exception:
            return None

        if request is not None:
            return request.build_absolute_uri(url)

        return url


class ReportCreateSerializer(serializers.Serializer):
    """
    Input serializer for creating a report.

    The session is supplied by the URL and therefore is deliberately not
    accepted from the request body.
    """

    query_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )

    format = serializers.ChoiceField(
        choices=["PDF", "HTML"],
        default="PDF",
    )

    def validate_query_id(self, value):
        if value is None:
            return value

        request = self.context.get("request")
        session = self.context.get("session")

        if session is None:
            raise serializers.ValidationError(
                "A valid session is required."
            )

        query = Query.objects.filter(
            id=value,
            session_id=session.id,
        ).first()

        if query is None:
            raise serializers.ValidationError(
                "The selected query does not belong to this session."
            )

        if request is not None and query.user_id != request.user.id:
            raise serializers.ValidationError(
                "You do not have access to the selected query."
            )

        return value


class ReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer used when listing reports for a session.
    """

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "query",
            "format",
            "status",
            "error",
            "file_url",
            "renderer_version",
            "generated_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file:
            return None

        request = self.context.get("request")

        try:
            url = obj.file.url
        except Exception:
            return None

        if request is not None:
            return request.build_absolute_uri(url)

        return url