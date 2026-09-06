"""
Serializers for the SatQuery-X session subsystem.

Sessions are the durable conversational workspace connecting:
- user/project context
- uploaded imagery
- map context
- conversational history
- active analysis state

Scientific measurements are not generated here. They must come from
actual imagery/evidence/analysis services.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Session


class SessionSerializer(serializers.ModelSerializer):
    """
    Full session representation used by the frontend.

    The serializer exposes useful session-level state while keeping
    ownership and server-managed timestamps read-only.
    """

    image_count = serializers.SerializerMethodField()
    query_count = serializers.SerializerMethodField()

    active_asset_ids = serializers.SerializerMethodField()
    active_image_pair_id = serializers.SerializerMethodField()
    active_pin = serializers.SerializerMethodField()
    last_query_id = serializers.SerializerMethodField()

    class Meta:
        model = Session

        fields = (
            "id",
            "name",
            "status",
            "project",
            "conversation_history",
            "conversation_context",

            # Derived session context.
            "active_asset_ids",
            "active_image_pair_id",
            "active_pin",
            "last_query_id",

            # Related-object counts.
            "image_count",
            "query_count",

            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "image_count",
            "query_count",
            "active_asset_ids",
            "active_image_pair_id",
            "active_pin",
            "last_query_id",
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError(
                "Session name cannot be empty."
            )

        return value

    def validate_status(self, value: str) -> str:
        allowed = {
            Session.STATUS_ACTIVE,
            Session.STATUS_ARCHIVED,
        }

        if value not in allowed:
            raise serializers.ValidationError(
                "Invalid session status."
            )

        return value

    def validate_conversation_history(self, value):
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Conversation history must be a list."
            )

        return value

    def validate_conversation_context(self, value):
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Conversation context must be an object."
            )

        return value

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def get_image_count(self, obj) -> int:
        """
        Count imagery assets attached to this session.

        Supports the canonical `imagery_assets` reverse relation and
        gracefully handles projects where that relation is unavailable.
        """
        manager = getattr(obj, "imagery_assets", None)

        if manager is None:
            return 0

        try:
            return manager.count()
        except (AttributeError, TypeError):
            return 0

    def get_query_count(self, obj) -> int:
        """
        Count queries attached to this session.

        Supports the canonical `queries` reverse relation.
        """
        manager = getattr(obj, "queries", None)

        if manager is None:
            return 0

        try:
            return manager.count()
        except (AttributeError, TypeError):
            return 0

    # ------------------------------------------------------------------
    # Durable context
    # ------------------------------------------------------------------

    def _context(self, obj) -> dict:
        context = getattr(obj, "conversation_context", None)

        return context if isinstance(context, dict) else {}

    def get_active_asset_ids(self, obj) -> list[str]:
        value = self._context(obj).get(
            "active_asset_ids",
            [],
        )

        if not isinstance(value, list):
            return []

        return [str(item) for item in value]

    def get_active_image_pair_id(self, obj):
        value = self._context(obj).get(
            "active_image_pair_id"
        )

        return str(value) if value else None

    def get_active_pin(self, obj):
        value = self._context(obj).get("active_pin")

        if not isinstance(value, dict):
            return None

        return value

    def get_last_query_id(self, obj):
        value = self._context(obj).get("last_query_id")

        return str(value) if value else None


class SessionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used when creating a new analysis session.

    The authenticated user is assigned by the view and can never be
    supplied by the client.
    """

    class Meta:
        model = Session

        fields = (
            "name",
            "project",
        )

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError(
                "Session name cannot be empty."
            )

        return value

    def validate_project(self, project):
        """
        Ensure a project can only be selected when it belongs to the
        authenticated user's organization.

        If the user/project models do not expose organization metadata,
        ownership cannot be safely inferred here, so the project is
        left for the view/access-control layer to validate.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not project or not user or not user.is_authenticated:
            return project

        user_org = getattr(user, "organization", None)
        project_org = getattr(project, "organization", None)

        if user_org is not None and project_org is not None:
            if user_org.pk != project_org.pk:
                raise serializers.ValidationError(
                    "You cannot create a session for a project "
                    "outside your organization."
                )

        return project


class SessionContextSerializer(serializers.Serializer):
    """
    Serializer for updating durable conversational/map context.

    This endpoint intentionally accepts contextual state rather than
    scientific measurements.

    Examples:
        {
            "active_asset_ids": ["..."],
            "active_image_pair_id": "...",
            "active_pin": {
                "latitude": 11.0168,
                "longitude": 76.9558,
                "label": "Selected location"
            }
        }
    """

    active_asset_ids = serializers.ListField(
        child=serializers.CharField(
            max_length=128,
        ),
        required=False,
        allow_empty=True,
    )

    active_image_pair_id = serializers.CharField(
        max_length=128,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    active_pin = serializers.DictField(
        required=False,
        allow_null=True,
    )

    active_aoi = serializers.DictField(
        required=False,
        allow_null=True,
    )

    map_view = serializers.DictField(
        required=False,
        allow_null=True,
    )

    last_intent = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    last_query_id = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate_active_pin(self, value):
        if value is None:
            return None

        latitude = value.get("latitude")
        longitude = value.get("longitude")

        if latitude is None or longitude is None:
            raise serializers.ValidationError(
                "An active pin must contain latitude and longitude."
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                "Pin latitude and longitude must be numeric."
            )

        if not -90.0 <= latitude <= 90.0:
            raise serializers.ValidationError(
                "Pin latitude must be between -90 and 90."
            )

        if not -180.0 <= longitude <= 180.0:
            raise serializers.ValidationError(
                "Pin longitude must be between -180 and 180."
            )

        normalized = dict(value)
        normalized["latitude"] = latitude
        normalized["longitude"] = longitude

        return normalized

    def validate_map_view(self, value):
        if value is None:
            return None

        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Map view must be an object."
            )

        return value

    def validate_active_aoi(self, value):
        if value is None:
            return None

        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "AOI context must be an object."
            )

        return value


class SessionHistoryMessageSerializer(serializers.Serializer):
    """
    Validation for a single conversation-history message.

    Used when the frontend needs to append a message without replacing
    the entire conversation history.
    """

    role = serializers.CharField(
        max_length=64,
    )

    content = serializers.CharField(
        allow_blank=True,
    )

    metadata = serializers.DictField(
        required=False,
        default=dict,
    )

    def validate_role(self, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise serializers.ValidationError(
                "Message role cannot be empty."
            )

        return value


class SessionHistoryAppendSerializer(
    serializers.Serializer
):
    """
    Serializer for appending one message to session history.
    """

    message = SessionHistoryMessageSerializer()