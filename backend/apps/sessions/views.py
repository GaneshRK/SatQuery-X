"""
API views for the SatQuery-X session subsystem.

Sessions are the main conversational context boundary for SatQuery-X.

Responsibilities:
- authenticated session CRUD
- organization/project-aware access control
- durable conversation context
- active map pin/context
- active imagery context
- conversation history updates
- session archive/restore

Scientific measurements and analysis results are NOT generated here.
Those belong to the imagery, satellite, queries, and analysis subsystems.
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Session
from .permissions import user_can_access_session
from .serializers import (
    SessionContextSerializer,
    SessionCreateSerializer,
    SessionHistoryAppendSerializer,
    SessionSerializer,
)


class SessionViewSet(viewsets.ModelViewSet):
    """
    Main REST API for SatQuery-X analysis sessions.

    Routes are normally exposed through:
        /api/sessions/

    The authenticated user is always the owner of newly created sessions.
    Clients cannot assign another user as the session owner.
    """

    permission_classes = [permissions.IsAuthenticated]

    # ------------------------------------------------------------------
    # Serializer selection
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == "create":
            return SessionCreateSerializer

        return SessionSerializer

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def get_queryset(self):
        """
        Return sessions visible to the authenticated user.

        Access is intentionally restricted to:
        - direct ownership
        - authorized organization/project scope

        This mirrors the centralized session-access helper while keeping
        queryset filtering efficient.
        """
        user = self.request.user

        if not user or not user.is_authenticated:
            return Session.objects.none()

        if user.is_superuser or user.is_staff:
            return Session.objects.all().select_related(
                "user",
                "project",
            )

        role = (getattr(user, "role", "") or "").upper()
        organization = getattr(user, "organization", None)

        if organization is not None:
            queryset = Session.objects.filter(
                Q(user=user)
                | Q(user__organization=organization)
                | Q(project__organization=organization)
            )
        else:
            queryset = Session.objects.filter(user=user)

        return queryset.select_related(
            "user",
            "project",
        ).distinct()

    def get_object(self):
        """
        Retrieve the object through the filtered queryset and then apply
        the centralized access-control rule as a second safety check.
        """
        obj = get_object_or_404(
            self.get_queryset(),
            pk=self.kwargs.get(self.lookup_field, self.kwargs.get("pk")),
        )

        if not user_can_access_session(
            self.request.user,
            obj,
        ):
            raise PermissionDenied(
                "You do not have permission to access this session."
            )

        return obj

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        """
        Always assign the authenticated user as the owner.

        The client cannot submit an arbitrary user ID.
        """
        user = self.request.user

        project = serializer.validated_data.get("project")

        if project is not None:
            user_org = getattr(user, "organization", None)
            project_org = getattr(project, "organization", None)

            if (
                user_org is not None
                and project_org is not None
                and user_org.pk != project_org.pk
            ):
                raise PermissionDenied(
                    "You cannot create a session for a project "
                    "outside your organization."
                )

        serializer.save(
            user=user,
            status=Session.STATUS_ACTIVE,
            conversation_history=[],
            conversation_context={},
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def perform_update(self, serializer):
        """
        Prevent ownership changes through normal session updates.
        """
        serializer.save(
            user=self.get_object().user,
        )

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="archive",
    )
    def archive(self, request, pk=None):
        """
        Archive a session without deleting its history or evidence links.
        """
        session = self.get_object()

        if session.is_archived:
            return Response(
                SessionSerializer(
                    session,
                    context={"request": request},
                ).data,
                status=status.HTTP_200_OK,
            )

        session.archive()

        return Response(
            SessionSerializer(
                session,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # Activate
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="activate",
    )
    def activate(self, request, pk=None):
        """
        Restore an archived session to active state.
        """
        session = self.get_object()

        if session.is_active:
            return Response(
                SessionSerializer(
                    session,
                    context={"request": request},
                ).data,
                status=status.HTTP_200_OK,
            )

        session.activate()

        return Response(
            SessionSerializer(
                session,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get", "patch", "put", "delete"],
        url_path="context",
    )
    def context(self, request, pk=None):
        """
        Read or update durable conversational analysis context.

        This is where the frontend can persist things such as:
        - active map pin
        - active imagery
        - active image pair
        - active AOI
        - map view
        - last intent
        - last query

        It does not create scientific measurements.
        """
        session = self.get_object()

        if request.method == "GET":
            serializer = SessionSerializer(
                session,
                context={"request": request},
            )

            return Response(
                {
                    "session_id": str(session.id),
                    "context": serializer.data.get(
                        "conversation_context",
                        {},
                    ),
                }
            )

        if request.method == "DELETE":
            session.clear_context()

            return Response(
                {
                    "session_id": str(session.id),
                    "context": {},
                },
                status=status.HTTP_200_OK,
            )

        serializer = SessionContextSerializer(
            data=request.data,
            partial=request.method == "PATCH",
        )

        serializer.is_valid(raise_exception=True)

        current_context = dict(
            session.conversation_context or {}
        )

        if request.method == "PUT":
            current_context = {}

        current_context.update(
            serializer.validated_data
        )

        session.update_context(
            current_context,
            replace=True,
        )

        return Response(
            {
                "session_id": str(session.id),
                "context": session.conversation_context,
            },
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # Map pin
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path="map-pin",
    )
    def map_pin(self, request, pk=None):
        """
        Manage the active map pin associated with the conversation.

        The map pin is context, not imagery georeferencing.
        """
        session = self.get_object()

        if request.method == "GET":
            return Response(
                {
                    "session_id": str(session.id),
                    "active_pin": session.get_active_pin(),
                }
            )

        if request.method == "DELETE":
            session.set_active_pin(None)

            return Response(
                {
                    "session_id": str(session.id),
                    "active_pin": None,
                }
            )

        serializer = SessionContextSerializer(
            data={
                "active_pin": request.data,
            }
        )

        serializer.is_valid(raise_exception=True)

        pin = serializer.validated_data.get("active_pin")

        session.set_active_pin(pin)

        return Response(
            {
                "session_id": str(session.id),
                "active_pin": session.get_active_pin(),
            },
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # Active imagery
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path="active-assets",
    )
    def active_assets(self, request, pk=None):
        """
        Manage the imagery currently active in the conversation.
        """
        session = self.get_object()

        if request.method == "GET":
            return Response(
                {
                    "session_id": str(session.id),
                    "active_asset_ids": session.get_active_asset_ids(),
                }
            )

        if request.method == "DELETE":
            session.set_active_assets([])

            return Response(
                {
                    "session_id": str(session.id),
                    "active_asset_ids": [],
                }
            )

        asset_ids = request.data.get("active_asset_ids")

        if asset_ids is None:
            raise ValidationError(
                {
                    "active_asset_ids": (
                        "active_asset_ids is required."
                    )
                }
            )

        serializer = SessionContextSerializer(
            data={
                "active_asset_ids": asset_ids,
            }
        )

        serializer.is_valid(raise_exception=True)

        normalized_ids = serializer.validated_data[
            "active_asset_ids"
        ]

        session.set_active_assets(
            normalized_ids
        )

        return Response(
            {
                "session_id": str(session.id),
                "active_asset_ids": session.get_active_asset_ids(),
            }
        )

    # ------------------------------------------------------------------
    # Active image pair
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path="active-pair",
    )
    def active_pair(self, request, pk=None):
        """
        Manage the image pair currently selected for comparison/change
        analysis.
        """
        session = self.get_object()

        if request.method == "GET":
            return Response(
                {
                    "session_id": str(session.id),
                    "active_image_pair_id": (
                        session.get_active_image_pair_id()
                    ),
                }
            )

        if request.method == "DELETE":
            session.set_active_image_pair(None)

            return Response(
                {
                    "session_id": str(session.id),
                    "active_image_pair_id": None,
                }
            )

        pair_id = request.data.get(
            "active_image_pair_id"
        )

        if pair_id in (None, ""):
            raise ValidationError(
                {
                    "active_image_pair_id": (
                        "active_image_pair_id is required."
                    )
                }
            )

        session.set_active_image_pair(pair_id)

        return Response(
            {
                "session_id": str(session.id),
                "active_image_pair_id": (
                    session.get_active_image_pair_id()
                ),
            }
        )

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="history",
    )
    def history(self, request, pk=None):
        """
        Return the durable conversation history.
        """
        session = self.get_object()

        history = session.conversation_history or []

        return Response(
            {
                "session_id": str(session.id),
                "messages": history,
                "count": len(history),
            }
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="history/append",
    )
    def append_history(self, request, pk=None):
        """
        Append one conversation message.

        This is useful for durable user/assistant context when the main
        query pipeline is not itself responsible for persistence.
        """
        session = self.get_object()

        serializer = SessionHistoryAppendSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]

        session.append_message(
            role=message["role"],
            content=message["content"],
            metadata=message.get("metadata"),
        )

        return Response(
            {
                "session_id": str(session.id),
                "message": message,
                "messages": session.conversation_history,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path="history",
    )
    def clear_history(self, request, pk=None):
        """
        Clear conversational history while retaining the session itself,
        imagery, reports, and other analysis records.
        """
        session = self.get_object()

        session.clear_conversation_history()

        return Response(
            {
                "session_id": str(session.id),
                "messages": [],
                "count": 0,
            },
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # Last-query context
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="last-query",
    )
    def last_query(self, request, pk=None):
        """
        Return the ID of the last query associated with this conversation.
        """
        session = self.get_object()

        return Response(
            {
                "session_id": str(session.id),
                "last_query_id": session.get_last_query_id(),
            }
        )

    # ------------------------------------------------------------------
    # Current session state
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="state",
    )
    def state(self, request, pk=None):
        """
        Return the compact state needed by the frontend/orchestrator.

        This avoids requiring the client to parse the entire conversation
        history simply to restore a workspace.
        """
        session = self.get_object()

        return Response(
            {
                "session_id": str(session.id),
                "name": session.name,
                "status": session.status,
                "is_active": session.is_active,
                "active_asset_ids": session.get_active_asset_ids(),
                "active_image_pair_id": (
                    session.get_active_image_pair_id()
                ),
                "active_pin": session.get_active_pin(),
                "last_query_id": session.get_last_query_id(),
                "context": session.conversation_context or {},
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
        )