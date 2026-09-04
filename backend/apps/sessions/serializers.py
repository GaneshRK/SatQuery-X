from rest_framework import serializers
from .models import Session


class SessionSerializer(serializers.ModelSerializer):
    image_count = serializers.SerializerMethodField()
    query_count = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = (
            "id",
            "name",
            "status",
            "project",
            "conversation_history",
            "created_at",
            "updated_at",
            "image_count",
            "query_count",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_image_count(self, obj):
        return getattr(obj, "imagery_assets", []).count() if hasattr(obj, "imagery_assets") else 0

    def get_query_count(self, obj):
        return getattr(obj, "queries", []).count() if hasattr(obj, "queries") else 0
