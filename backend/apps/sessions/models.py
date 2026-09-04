import uuid
from django.conf import settings
from django.db import models


class Session(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analysis_sessions"
    )
    project = models.ForeignKey(
        "accounts.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sessions",
    )
    name = models.CharField(max_length=255, default="Untitled Session")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    conversation_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.id})"
