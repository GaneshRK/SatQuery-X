"""
Session models for SatQuery-X.

A Session represents one continuous Earth-observation analysis workspace.

The session is intentionally lightweight:
- It owns the conversation state.
- It stores durable map/context state.
- It links to a project when applicable.
- Uploaded imagery, queries, evidence, and reports remain in their
  respective applications and reference the session.

Scientific measurements must never be stored here as fabricated defaults.
They belong to actual imagery/evidence/analysis records.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Session(models.Model):
    """
    Persistent conversational analysis session.

    A session is the main context boundary for SatQuery-X. The orchestrator,
    imagery subsystem, query subsystem, satellite subsystem, and reports
    can all reference the same session.

    conversation_context is intended for durable conversational/map state,
    for example:
        {
            "active_asset_ids": [...],
            "active_image_pair_id": "...",
            "active_pin": {...},
            "active_aoi": {...},
            "map_view": {...},
            "last_intent": "...",
            "last_query_id": "..."
        }

    It must contain context/state only, not fabricated scientific results.
    """

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analysis_sessions",
    )

    project = models.ForeignKey(
        "accounts.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )

    name = models.CharField(
        max_length=255,
        default="Untitled Session",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    conversation_history = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Durable conversation messages/events for this analysis session."
        ),
    )

    conversation_context = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Durable Earth-analysis context including active imagery, "
            "map pin, AOI, selected pair, and recent query state."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(
                fields=("user", "status"),
                name="session_user_status_idx",
            ),
            models.Index(
                fields=("project", "status"),
                name="session_project_status_idx",
            ),
            models.Index(
                fields=("updated_at",),
                name="session_updated_idx",
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self) -> None:
        """
        Validate session relationships without making assumptions about
        organizations or scientific data.
        """
        errors = {}

        if self.project_id and self.user_id:
            project_user = getattr(self.project, "organization", None)
            user_organization = getattr(self.user, "organization", None)

            # If both objects expose organizations, prevent cross-organization
            # session assignment.
            if (
                project_user is not None
                and user_organization is not None
                and project_user.pk != user_organization.pk
            ):
                errors["project"] = (
                    "The selected project does not belong to the user's "
                    "organization."
                )

        if not isinstance(self.conversation_history, list):
            errors["conversation_history"] = (
                "Conversation history must be a JSON list."
            )

        if not isinstance(self.conversation_context, dict):
            errors["conversation_context"] = (
                "Conversation context must be a JSON object."
            )

        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE

    @property
    def is_archived(self) -> bool:
        return self.status == self.STATUS_ARCHIVED

    def archive(self, *, save: bool = True) -> "Session":
        self.status = self.STATUS_ARCHIVED

        if save:
            self.save(update_fields=("status", "updated_at"))

        return self

    def activate(self, *, save: bool = True) -> "Session":
        self.status = self.STATUS_ACTIVE

        if save:
            self.save(update_fields=("status", "updated_at"))

        return self

    # ------------------------------------------------------------------
    # Conversation state
    # ------------------------------------------------------------------

    def append_message(
        self,
        *,
        role: str,
        content: str,
        metadata: dict | None = None,
        save: bool = True,
    ) -> "Session":
        """
        Append one durable conversation event.

        This stores conversational history only. It does not manufacture
        analysis measurements or model outputs.
        """
        if not role:
            raise ValueError("role is required.")

        if content is None:
            raise ValueError("content is required.")

        message = {
            "role": str(role),
            "content": str(content),
        }

        if metadata:
            message["metadata"] = metadata

        history = list(self.conversation_history or [])
        history.append(message)
        self.conversation_history = history

        if save:
            self.save(update_fields=("conversation_history", "updated_at"))

        return self

    def clear_conversation_history(
        self,
        *,
        save: bool = True,
    ) -> "Session":
        self.conversation_history = []

        if save:
            self.save(update_fields=("conversation_history", "updated_at"))

        return self

    # ------------------------------------------------------------------
    # Durable analysis context
    # ------------------------------------------------------------------

    def update_context(
        self,
        values: dict,
        *,
        replace: bool = False,
        save: bool = True,
    ) -> "Session":
        """
        Update durable conversational analysis context.

        Example context:
            {
                "active_asset_ids": ["..."],
                "active_pin": {
                    "latitude": ...,
                    "longitude": ...,
                    "label": "..."
                },
                "active_aoi": {...}
            }

        The method intentionally does not validate scientific measurements.
        Those belong to evidence/analysis records.
        """
        if not isinstance(values, dict):
            raise ValueError("Session context must be a dictionary.")

        if replace:
            context = dict(values)
        else:
            context = dict(self.conversation_context or {})
            context.update(values)

        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def get_context(self, key: str, default=None):
        if not key:
            return default

        context = self.conversation_context or {}
        return context.get(key, default)

    def remove_context(
        self,
        key: str,
        *,
        save: bool = True,
    ) -> "Session":
        context = dict(self.conversation_context or {})
        context.pop(key, None)
        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def clear_context(
        self,
        *,
        save: bool = True,
    ) -> "Session":
        self.conversation_context = {}

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    # ------------------------------------------------------------------
    # Map context
    # ------------------------------------------------------------------

    def set_active_pin(
        self,
        pin: dict | None,
        *,
        save: bool = True,
    ) -> "Session":
        """
        Persist the user's active map pin.

        The pin is contextual information. It must not be interpreted as
        fabricated imagery georeferencing.
        """
        if pin is not None and not isinstance(pin, dict):
            raise ValueError("Active pin must be a dictionary or None.")

        context = dict(self.conversation_context or {})

        if pin is None:
            context.pop("active_pin", None)
        else:
            context["active_pin"] = pin

        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def get_active_pin(self) -> dict | None:
        pin = (self.conversation_context or {}).get("active_pin")
        return pin if isinstance(pin, dict) else None

    # ------------------------------------------------------------------
    # Active imagery context
    # ------------------------------------------------------------------

    def set_active_assets(
        self,
        asset_ids,
        *,
        save: bool = True,
    ) -> "Session":
        """
        Store the IDs of imagery currently relevant to the conversation.
        """
        if asset_ids is None:
            normalized = []
        else:
            normalized = [str(asset_id) for asset_id in asset_ids]

        context = dict(self.conversation_context or {})
        context["active_asset_ids"] = normalized
        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def get_active_asset_ids(self) -> list[str]:
        value = (self.conversation_context or {}).get(
            "active_asset_ids",
            [],
        )

        if not isinstance(value, list):
            return []

        return [str(item) for item in value]

    def set_active_image_pair(
        self,
        pair_id,
        *,
        save: bool = True,
    ) -> "Session":
        context = dict(self.conversation_context or {})

        if pair_id is None:
            context.pop("active_image_pair_id", None)
        else:
            context["active_image_pair_id"] = str(pair_id)

        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def get_active_image_pair_id(self) -> str | None:
        value = (self.conversation_context or {}).get(
            "active_image_pair_id"
        )

        return str(value) if value else None

    # ------------------------------------------------------------------
    # Query context
    # ------------------------------------------------------------------

    def set_last_query(
        self,
        query_id,
        *,
        save: bool = True,
    ) -> "Session":
        context = dict(self.conversation_context or {})

        if query_id is None:
            context.pop("last_query_id", None)
        else:
            context["last_query_id"] = str(query_id)

        self.conversation_context = context

        if save:
            self.save(update_fields=("conversation_context", "updated_at"))

        return self

    def get_last_query_id(self) -> str | None:
        value = (self.conversation_context or {}).get("last_query_id")
        return str(value) if value else None