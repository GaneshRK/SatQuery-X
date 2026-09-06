import uuid
from typing import Any

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable application audit record.

    Audit logs record observable application actions and metadata.
    They must never contain private model reasoning / chain-of-thought.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    action = models.CharField(
        max_length=128,
        db_index=True,
    )

    target_type = models.CharField(
        max_length=128,
        db_index=True,
    )

    target_id = models.CharField(
        max_length=128,
        db_index=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["action", "-created_at"],
                name="audit_action_created_idx",
            ),
            models.Index(
                fields=["target_type", "target_id"],
                name="audit_target_idx",
            ),
            models.Index(
                fields=["user", "-created_at"],
                name="audit_user_created_idx",
            ),
        ]

    def __str__(self) -> str:
        timestamp = (
            self.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if self.created_at
            else "unknown-time"
        )

        return (
            f"[{timestamp}] "
            f"{self.action} on "
            f"{self.target_type}:{self.target_id}"
        )


def _sanitize_metadata(value: Any) -> Any:
    """
    Convert metadata into JSON-safe values.

    Audit metadata should contain factual execution information only.
    Private reasoning, prompts, secrets, tokens, and credentials must
    not be written to the audit log.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _sanitize_metadata(item)
            for key, item in value.items()
            if str(key).lower()
            not in {
                "password",
                "token",
                "access_token",
                "refresh_token",
                "api_key",
                "secret",
                "authorization",
                "cookie",
                "private_key",
                "chain_of_thought",
                "cot",
                "reasoning_trace",
                "hidden_reasoning",
                "internal_reasoning",
            }
        }

    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata(item) for item in value]

    return str(value)


def log_audit_event(
    user,
    action: str,
    target_type: str,
    target_id: str,
    metadata: dict | None = None,
):
    """
    Create an audit event.

    Parameters
    ----------
    user:
        Django user instance or None.

    action:
        Observable action name, for example:
        QUERY_CREATED
        QUERY_EXECUTION_STARTED
        QUERY_EXECUTION_COMPLETED
        QUERY_EXECUTION_FAILED
        EVIDENCE_VALIDATED
        RESPONSE_GENERATED

    target_type:
        Type of object involved, such as:
        query
        session
        execution_step
        image
        evidence

    target_id:
        Identifier of the target object.

    metadata:
        JSON-safe operational metadata.

    Returns
    -------
    AuditLog
        Created audit record.
    """

    authenticated_user = (
        user
        if user is not None
        and getattr(user, "is_authenticated", False)
        else None
    )

    safe_metadata = _sanitize_metadata(metadata or {})

    return AuditLog.objects.create(
        user=authenticated_user,
        action=str(action)[:128],
        target_type=str(target_type)[:128],
        target_id=str(target_id)[:128],
        metadata=safe_metadata,
    )