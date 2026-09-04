import uuid
from django.conf import settings
from django.db import models


class Query(models.Model):
    MODE_CHOICES = [
        ("SINGLE_IMAGE", "Single Image"),
        ("BI_TEMPORAL", "Bi-Temporal"),
        ("CROSS_MODAL", "Cross-Modal"),
    ]
    TASK_CHOICES = [
        ("VQA", "Visual Question Answering"),
        ("CAPTION", "Scene Captioning"),
        ("GROUNDING", "Text-Guided Grounding"),
        ("CHANGE_DETECTION", "Bi-Temporal Change Map"),
        ("CHANGE_VQA", "Change-Based VQA"),
        ("OPTICAL_SAR_FUSION", "Optical-SAR Fusion Analysis"),
        ("MISSION", "Mission Mode (Multi-Step Intelligence Analysis)"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="queries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_queries"
    )
    text = models.TextField()
    image = models.ForeignKey(
        "imagery.ImageAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="queries"
    )
    image_pair = models.ForeignKey(
        "imagery.ImagePair", on_delete=models.SET_NULL, null=True, blank=True, related_name="queries"
    )
    detected_mode = models.CharField(max_length=32, choices=MODE_CHOICES, default="SINGLE_IMAGE")
    detected_task = models.CharField(max_length=32, choices=TASK_CHOICES, default="VQA")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="PENDING")
    plan = models.JSONField(default=dict, blank=True)
    answer = models.TextField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Query {self.id}: {self.text[:50]}"


class ExecutionStep(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(
        Query, on_delete=models.CASCADE, related_name="execution_steps"
    )
    step_number = models.IntegerField(default=1)
    tool_name = models.CharField(max_length=128)
    model_version = models.CharField(max_length=64, default="0.1-baseline")
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="PENDING")
    output_ref = models.JSONField(default=dict, blank=True)
    latency_ms = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["step_number"]

    def __str__(self):
        return f"Step {self.step_number} [{self.tool_name}]: {self.status}"
