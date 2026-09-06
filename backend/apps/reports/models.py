"""
SatQuery-X report models.

Reports are generated from actual Query / Evidence data.  This module does
not store or manufacture scientific measurements; measurements belong to the
evidence produced by the analysis pipeline.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Report(models.Model):
    """
    A persistent export of a SatQuery-X analysis.

    A report belongs to a session and may optionally be associated with a
    specific query.  The report itself stores export/provenance metadata,
    while scientific results remain sourced from the query's evidence bundle.
    """

    FORMAT_CHOICES = [
        ("HTML", "HTML Document"),
        ("PDF", "PDF Document"),
    ]

    STATUS_CHOICES = [
        ("GENERATING", "Generating"),
        ("READY", "Ready"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    session = models.ForeignKey(
        "analysis_sessions.Session",
        on_delete=models.CASCADE,
        related_name="reports",
    )

    query = models.ForeignKey(
        "queries.Query",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )

    file = models.FileField(
        upload_to="reports/",
        null=True,
        blank=True,
    )

    format = models.CharField(
        max_length=16,
        choices=FORMAT_CHOICES,
        default="PDF",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="GENERATING",
    )

    # Human-readable failure information. Never expose stack traces here.
    error = models.TextField(
        blank=True,
        default="",
    )

    # Snapshot of the report-generation inputs.
    #
    # Example:
    # {
    #   "query_id": "...",
    #   "input_asset_ids": ["..."],
    #   "evidence_count": 4,
    #   "execution_step_count": 3
    # }
    source_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    # Compact provenance information describing what actually contributed
    # to the generated report.
    #
    # This is intentionally metadata/provenance, not hidden chain-of-thought.
    provenance = models.JSONField(
        default=dict,
        blank=True,
    )

    # Report-generation version so exported documents can be reproduced or
    # compared after the renderer changes.
    renderer_version = models.CharField(
        max_length=64,
        default="1.0",
    )

    generated_at = models.DateTimeField(
        auto_now_add=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(
                fields=["session", "-generated_at"],
                name="reports_session_created_idx",
            ),
            models.Index(
                fields=["status", "-generated_at"],
                name="reports_status_created_idx",
            ),
            models.Index(
                fields=["format", "-generated_at"],
                name="reports_format_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Report {self.id} ({self.format}): {self.status}"

    def clean(self):
        """
        Validate report consistency.

        A query attached to a report must belong to the same session.
        """
        super().clean()

        if self.query_id and self.session_id:
            if self.query.session_id != self.session_id:
                raise ValidationError(
                    {
                        "query": (
                            "The selected query does not belong to the "
                            "selected session."
                        )
                    }
                )

        if self.format not in dict(self.FORMAT_CHOICES):
            raise ValidationError(
                {"format": "Unsupported report format."}
            )

        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError(
                {"status": "Unsupported report status."}
            )

    @property
    def is_ready(self) -> bool:
        """Return True only when the report is ready and has a file."""
        return self.status == "READY" and bool(self.file)

    @property
    def is_failed(self) -> bool:
        """Return True when report generation failed."""
        return self.status == "FAILED"

    @property
    def is_generating(self) -> bool:
        """Return True while report generation is in progress."""
        return self.status == "GENERATING"

    def mark_generating(self) -> None:
        """Reset the report to the generating state."""
        self.status = "GENERATING"
        self.error = ""
        self.completed_at = None
        self.save(
            update_fields=[
                "status",
                "error",
                "completed_at",
                "updated_at",
            ]
        )

    def mark_ready(
        self,
        *,
        source_snapshot: dict | None = None,
        provenance: dict | None = None,
    ) -> None:
        """
        Mark the report ready after a successful file write.
        """
        from django.utils import timezone

        self.status = "READY"
        self.error = ""
        self.completed_at = timezone.now()

        if source_snapshot is not None:
            self.source_snapshot = source_snapshot

        if provenance is not None:
            self.provenance = provenance

        self.save(
            update_fields=[
                "status",
                "error",
                "completed_at",
                "source_snapshot",
                "provenance",
                "updated_at",
            ]
        )

    def mark_failed(self, error_message: str) -> None:
        """
        Mark generation as failed.

        Only a safe, human-readable error should be supplied. Internal
        exception traces must stay in server logs.
        """
        from django.utils import timezone

        self.status = "FAILED"
        self.error = str(error_message)[:4000]
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "error",
                "completed_at",
                "updated_at",
            ]
        )