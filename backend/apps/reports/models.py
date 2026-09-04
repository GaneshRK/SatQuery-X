import uuid
from django.db import models


class Report(models.Model):
    FORMAT_CHOICES = [
        ("HTML", "HTML Document"),
        ("PDF", "PDF Document"),
    ]
    STATUS_CHOICES = [
        ("GENERATING", "Generating"),
        ("READY", "Ready"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "analysis_sessions.Session", on_delete=models.CASCADE, related_name="reports"
    )
    query = models.ForeignKey(
        "queries.Query", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    file = models.FileField(upload_to="reports/", null=True, blank=True)
    format = models.CharField(max_length=16, choices=FORMAT_CHOICES, default="PDF")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="GENERATING")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"Report {self.id} ({self.format}): {self.status}"
