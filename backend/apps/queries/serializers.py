from rest_framework import serializers
from apps.evidence.models import EvidenceRegion
from apps.queries.models import ExecutionStep, Query


class ExecutionStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionStep
        fields = "__all__"


class EvidenceRegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceRegion
        fields = "__all__"


class QueryDetailSerializer(serializers.ModelSerializer):
    execution_steps = ExecutionStepSerializer(many=True, read_only=True)
    evidence_regions = EvidenceRegionSerializer(many=True, read_only=True)

    class Meta:
        model = Query
        fields = (
            "id",
            "session",
            "text",
            "image",
            "image_pair",
            "detected_mode",
            "detected_task",
            "status",
            "plan",
            "answer",
            "confidence",
            "error",
            "created_at",
            "completed_at",
            "execution_steps",
            "evidence_regions",
        )
