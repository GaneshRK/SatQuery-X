"""
Query and execution-trace models for SatQuery-X.

The query layer stores:
- The user's natural-language request
- Active imagery / image-pair context
- Planner output
- Evidence produced by specialist agents
- Final grounded answer
- Auditable execution trace

Design principles:
- No fabricated scientific measurements
- No hardcoded model/method claims
- Multiple imagery inputs are supported
- Map/location context is preserved with the query
- Legacy `image` and `image_pair` fields remain for compatibility
- Scientific evidence is stored separately from the final answer
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Query(models.Model):
    """
    A single conversational analysis request.

    A Query represents one user request and its complete execution lifecycle.
    Specialist agents should write evidence into `evidence_graph` and the
    orchestrator should use that evidence to produce `answer`.
    """

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

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # ------------------------------------------------------------------
    # Conversation ownership
    # ------------------------------------------------------------------

    session = models.ForeignKey(
        "analysis_sessions.Session",
        on_delete=models.CASCADE,
        related_name="queries",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_queries",
    )

    # ------------------------------------------------------------------
    # Original user request
    # ------------------------------------------------------------------

    text = models.TextField()

    # ------------------------------------------------------------------
    # Imagery inputs
    # ------------------------------------------------------------------

    # Legacy / primary image reference.
    # Kept for compatibility with existing API code.
    image = models.ForeignKey(
        "imagery.ImageAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queries",
    )

    # Legacy / primary image-pair reference.
    image_pair = models.ForeignKey(
        "imagery.ImagePair",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queries",
    )

    # Multiple uploaded images can participate in one query.
    #
    # This is intentionally separate from `image` so existing clients that
    # expect Query.image continue to work.
    input_assets = models.ManyToManyField(
        "imagery.ImageAsset",
        blank=True,
        related_name="queries_many",
        help_text=(
            "All imagery assets explicitly used as inputs for this query."
        ),
    )

    # ------------------------------------------------------------------
    # Planner / routing state
    # ------------------------------------------------------------------

    detected_mode = models.CharField(
        max_length=32,
        choices=MODE_CHOICES,
        default="SINGLE_IMAGE",
    )

    detected_task = models.CharField(
        max_length=32,
        choices=TASK_CHOICES,
        default="VQA",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    # Legacy planner field.
    plan = models.JSONField(
        default=dict,
        blank=True,
    )

    # Validated structured execution plan produced by the planner.
    structured_plan = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Validated execution plan produced by the query planner."
        ),
    )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    context_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Immutable-at-execution snapshot of map, location, imagery, "
            "viewport, AOI, conversation and other relevant context."
        ),
    )

    follow_up_questions = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Contextual follow-up questions generated when useful."
        ),
    )

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    evidence_graph = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Structured evidence graph produced by specialist agents. "
            "Contains observations, measurements, provenance and "
            "validation state."
        ),
    )

    evidence_bundle = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Final validated evidence bundle used by the answer composer."
        ),
    )

    # ------------------------------------------------------------------
    # Final response
    # ------------------------------------------------------------------

    answer = models.TextField(
        null=True,
        blank=True,
    )

    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Evidence-grounded confidence. This must not be interpreted "
            "as an unsupported probability of truth."
        ),
    )

    clarification_required = models.BooleanField(
        default=False,
        help_text=(
            "True when the system cannot safely answer without "
            "additional user input or data."
        ),
    )

    clarification = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Structured clarification request when more context/data "
            "is required."
        ),
    )

    # ------------------------------------------------------------------
    # Auditable response trace
    # ------------------------------------------------------------------

    answer_trace = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Concise user-visible execution/evidence trace. "
            "This must never contain hidden chain-of-thought."
        ),
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    error = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["session", "-created_at"],
                name="query_session_created_idx",
            ),
            models.Index(
                fields=["user", "-created_at"],
                name="query_user_created_idx",
            ),
            models.Index(
                fields=["status", "-created_at"],
                name="query_status_created_idx",
            ),
            models.Index(
                fields=["detected_task", "-created_at"],
                name="query_task_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Query {self.id}: {self.text[:80]}"

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json_object(value: Any) -> dict:
        return value if isinstance(value, dict) else {}

    def clean(self) -> None:
        """
        Validate relationships that can be checked without resolving the
        ManyToMany input_assets relation.
        """

        errors: dict[str, str] = {}

        if not self.text or not self.text.strip():
            errors["text"] = "Query text cannot be empty."

        if self.confidence is not None:
            if not 0.0 <= float(self.confidence) <= 1.0:
                errors["confidence"] = (
                    "Confidence must be between 0 and 1."
                )

        # A pair belongs to a session. A query must not accidentally combine
        # a pair from another conversation.
        if self.image_pair_id and self.session_id:
            try:
                pair_session_id = self.image_pair.session_id
                if pair_session_id != self.session_id:
                    errors["image_pair"] = (
                        "Image pair must belong to the same session "
                        "as the query."
                    )
            except Exception:
                pass

        # A primary image must belong to the same session.
        if self.image_id and self.session_id:
            try:
                image_session_id = self.image.session_id
                if image_session_id != self.session_id:
                    errors["image"] = (
                        "Image must belong to the same session "
                        "as the query."
                    )
            except Exception:
                pass

        # Validate mode requirements where the information is explicit.
        if self.detected_mode == "BI_TEMPORAL" and not self.image_pair_id:
            errors["image_pair"] = (
                "Bi-temporal queries require an image pair."
            )

        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def has_image(self) -> bool:
        return bool(self.image_id or self.input_assets.exists())

    @property
    def has_pair(self) -> bool:
        return bool(self.image_pair_id)

    @property
    def input_asset_count(self) -> int:
        """
        Return the number of explicitly attached input assets.

        The legacy `image` is counted when it has not also been attached
        through input_assets.
        """
        try:
            asset_ids = set(
                self.input_assets.values_list("id", flat=True)
            )
        except Exception:
            asset_ids = set()

        if self.image_id:
            asset_ids.add(self.image_id)

        return len(asset_ids)

    @property
    def is_finished(self) -> bool:
        return self.status in {"COMPLETED", "FAILED"}

    @property
    def has_answer(self) -> bool:
        return bool(self.answer and self.answer.strip())

    @property
    def has_evidence(self) -> bool:
        return bool(
            isinstance(self.evidence_bundle, dict)
            and self.evidence_bundle
        )

    @property
    def active_context(self) -> dict:
        """
        Return the execution context snapshot without mutating the model.
        """
        return self._safe_json_object(self.context_snapshot)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def mark_running(self) -> None:
        self.status = "RUNNING"
        self.error = None
        self.save(
            update_fields=["status", "error"],
        )

    def mark_completed(
        self,
        *,
        answer: str | None = None,
        confidence: float | None = None,
        evidence_bundle: dict | None = None,
        answer_trace: list | None = None,
    ) -> None:
        from django.utils import timezone

        self.status = "COMPLETED"
        self.completed_at = timezone.now()
        self.error = None

        if answer is not None:
            self.answer = answer

        if confidence is not None:
            self.confidence = float(confidence)

        if evidence_bundle is not None:
            self.evidence_bundle = evidence_bundle

        if answer_trace is not None:
            self.answer_trace = answer_trace

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error",
                "answer",
                "confidence",
                "evidence_bundle",
                "answer_trace",
            ]
        )

    def mark_failed(self, error: str) -> None:
        from django.utils import timezone

        self.status = "FAILED"
        self.completed_at = timezone.now()
        self.error = str(error)[:10000]

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error",
            ]
        )


class ExecutionStep(models.Model):
    """
    One auditable orchestration step.

    This records WHAT specialist/tool executed and what evidence it produced.
    It deliberately does not store hidden chain-of-thought.
    """

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    query = models.ForeignKey(
        Query,
        on_delete=models.CASCADE,
        related_name="execution_steps",
    )

    step_number = models.IntegerField(
        default=1,
    )

    # High-level agent/tool identity.
    tool_name = models.CharField(
        max_length=128,
    )

    # Optional specialist category.
    agent_type = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=(
            "Specialist agent category, e.g. single_image, "
            "change_detection, gis, preprocessing."
        ),
    )

    # Actual model implementation/version used, when applicable.
    model_version = models.CharField(
        max_length=128,
        default="unknown",
    )

    # Parameters passed to the specialist.
    #
    # Do not store secrets, tokens or hidden chain-of-thought here.
    parameters = models.JSONField(
        default=dict,
        blank=True,
    )

    # References to input assets/evidence.
    input_refs = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "References to input assets or upstream evidence consumed "
            "by this step."
        ),
    )

    # Structured output/evidence reference.
    output_ref = models.JSONField(
        default=dict,
        blank=True,
    )

    evidence_refs = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "References to evidence generated or validated by this step."
        ),
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    latency_ms = models.IntegerField(
        null=True,
        blank=True,
    )

    retry_count = models.PositiveIntegerField(
        default=0,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["step_number"]

        constraints = [
            models.UniqueConstraint(
                fields=["query", "step_number"],
                name="unique_query_execution_step",
            ),
        ]

        indexes = [
            models.Index(
                fields=["query", "step_number"],
                name="exec_query_step_idx",
            ),
            models.Index(
                fields=["query", "status"],
                name="exec_query_status_idx",
            ),
            models.Index(
                fields=["tool_name", "status"],
                name="exec_tool_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Step {self.step_number} "
            f"[{self.tool_name}]: {self.status}"
        )

    def clean(self) -> None:
        errors: dict[str, str] = {}

        if self.step_number < 1:
            errors["step_number"] = (
                "Execution step number must be at least 1."
            )

        if self.latency_ms is not None and self.latency_ms < 0:
            errors["latency_ms"] = (
                "Latency cannot be negative."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def is_finished(self) -> bool:
        return self.status in {"DONE", "FAILED", "SKIPPED"}

    @property
    def succeeded(self) -> bool:
        return self.status == "DONE"

    def mark_running(self) -> None:
        from django.utils import timezone

        self.status = "RUNNING"
        self.started_at = timezone.now()
        self.error = None

        self.save(
            update_fields=[
                "status",
                "started_at",
                "error",
            ]
        )

    def mark_done(
        self,
        *,
        output_ref: dict | None = None,
        evidence_refs: list | None = None,
        latency_ms: int | None = None,
    ) -> None:
        from django.utils import timezone

        self.status = "DONE"
        self.completed_at = timezone.now()
        self.error = None

        if output_ref is not None:
            self.output_ref = output_ref

        if evidence_refs is not None:
            self.evidence_refs = evidence_refs

        if latency_ms is not None:
            self.latency_ms = max(0, int(latency_ms))

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error",
                "output_ref",
                "evidence_refs",
                "latency_ms",
            ]
        )

    def mark_failed(
        self,
        error: str,
        *,
        latency_ms: int | None = None,
    ) -> None:
        from django.utils import timezone

        self.status = "FAILED"
        self.completed_at = timezone.now()
        self.error = str(error)[:10000]

        if latency_ms is not None:
            self.latency_ms = max(0, int(latency_ms))

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error",
                "latency_ms",
            ]
        )

    def mark_skipped(self, reason: str | None = None) -> None:
        from django.utils import timezone

        self.status = "SKIPPED"
        self.completed_at = timezone.now()

        if reason:
            self.error = str(reason)[:10000]

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error",
            ]
        )

class ProvenanceRecord(models.Model):
    """Hash-chained audit event for reproducible SatQuery-X execution provenance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(Query, on_delete=models.CASCADE, related_name="provenance_records")
    execution_step = models.ForeignKey(
        "queries.ExecutionStep", on_delete=models.SET_NULL, null=True, blank=True, related_name="provenance_records"
    )
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    previous_hash = models.CharField(max_length=64, blank=True, default="")
    record_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["query", "sequence"], name="unique_query_provenance_sequence"),
        ]
        indexes = [
            models.Index(fields=["query", "sequence"], name="prov_query_sequence_idx"),
            models.Index(fields=["query", "event_type"], name="prov_query_event_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.query_id}:{self.sequence}:{self.event_type}"

