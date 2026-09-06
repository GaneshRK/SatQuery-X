"""
Permission and access-control helpers for SatQuery-X sessions.

Access model:

    Organization
        └── Project
              └── Session
                    ├── Imagery
                    ├── Queries
                    └── Reports

A session may be accessed by:
- its owner
- staff/superusers
- authorized users within the same organization/project according
  to their role

This module contains authorization logic only. It does not perform
scientific analysis or generate geospatial data.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404

from rest_framework.exceptions import PermissionDenied

from .models import Session


# ----------------------------------------------------------------------
# Role definitions
# ----------------------------------------------------------------------

PRIVILEGED_ROLES = frozenset(
    {
        "ADMIN",
        "OWNER",
        "JUDGE",
        "DEMO",
    }
)

ORGANIZATION_ROLES = frozenset(
    {
        "ADMIN",
        "OWNER",
        "JUDGE",
        "DEMO",
        "ANALYST",
        "VIEWER",
        "MEMBER",
    }
)


# ----------------------------------------------------------------------
# Basic helpers
# ----------------------------------------------------------------------

def _is_authenticated(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
    )


def _role(user) -> str:
    return (
        str(getattr(user, "role", "") or "")
        .strip()
        .upper()
    )


def _organization(user):
    return getattr(user, "organization", None)


def _organization_id(obj):
    """
    Safely extract an organization ID from a user, project, or
    organization-like object.
    """
    if obj is None:
        return None

    if hasattr(obj, "organization_id"):
        return getattr(obj, "organization_id", None)

    organization = getattr(obj, "organization", None)

    if organization is not None:
        return getattr(organization, "pk", None)

    return None


def _same_organization(user, session) -> bool:
    """
    Determine whether the requesting user and session belong to the
    same organization.

    Organization membership may be represented either through:
        user.organization
        session.user.organization
        session.project.organization
    """
    user_org = _organization(user)

    if user_org is None:
        return False

    user_org_id = getattr(user_org, "pk", None)

    if user_org_id is None:
        return False

    session_owner = getattr(session, "user", None)

    owner_org_id = _organization_id(session_owner)

    if (
        owner_org_id is not None
        and owner_org_id == user_org_id
    ):
        return True

    project = getattr(session, "project", None)

    project_org_id = _organization_id(project)

    if (
        project_org_id is not None
        and project_org_id == user_org_id
    ):
        return True

    return False


def _same_project(user, session) -> bool:
    """
    Project-level access helper.

    The current Session model does not directly store project membership
    for a user, so project access is inferred from the user's organization
    and the session's project organization.

    More restrictive project-membership models can build on this helper
    later without changing session ownership semantics.
    """
    project = getattr(session, "project", None)

    if project is None:
        return False

    user_org = _organization(user)
    project_org = getattr(project, "organization", None)

    if user_org is None or project_org is None:
        return False

    return user_org.pk == project_org.pk


# ----------------------------------------------------------------------
# Session access
# ----------------------------------------------------------------------

def user_can_access_session(
    user,
    session,
) -> bool:
    """
    Return True when the user is authorized to access the session.

    Rules, in order:

    1. Unauthenticated users -> denied.
    2. Superusers/staff -> allowed.
    3. Session owner -> allowed.
    4. Privileged organization roles -> allowed within their organization.
    5. Regular organization members -> allowed for sessions in their
       organization/project.
    6. Everyone else -> denied.
    """
    if not _is_authenticated(user):
        return False

    if session is None:
        return False

    # Global administrative access.
    if (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    ):
        return True

    # Direct ownership.
    if (
        getattr(session, "user_id", None)
        == getattr(user, "id", None)
    ):
        return True

    role = _role(user)

    # Users without a known organization cannot inherit organization-level
    # access merely from having a privileged role.
    if _organization(user) is None:
        return False

    # Privileged roles may access sessions in their organization.
    if role in PRIVILEGED_ROLES:
        return _same_organization(user, session)

    # Regular organization users can access sessions belonging to their
    # organization or an organization-owned project.
    if role in ORGANIZATION_ROLES:
        return _same_organization(user, session)

    # If the project is explicitly shared through the user's organization,
    # allow access even when role metadata is not recognized.
    if _same_project(user, session):
        return True

    return False


def can_modify_session(
    user,
    session,
) -> bool:
    """
    Determine whether the user can modify session-level state.

    Reading a shared session and modifying it are intentionally separate.

    Modification is allowed to:
    - staff/superusers
    - the session owner
    - organization administrators/owners
    """
    if not _is_authenticated(user):
        return False

    if session is None:
        return False

    if (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    ):
        return True

    if (
        getattr(session, "user_id", None)
        == getattr(user, "id", None)
    ):
        return True

    role = _role(user)

    if role not in {
        "ADMIN",
        "OWNER",
    }:
        return False

    return _same_organization(user, session)


def can_delete_session(
    user,
    session,
) -> bool:
    """
    Determine whether a session can be permanently deleted.

    Deletion is more restrictive than ordinary modification.
    """
    if not _is_authenticated(user):
        return False

    if session is None:
        return False

    if (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    ):
        return True

    if (
        getattr(session, "user_id", None)
        == getattr(user, "id", None)
    ):
        return True

    role = _role(user)

    return (
        role in {"ADMIN", "OWNER"}
        and _same_organization(user, session)
    )


# ----------------------------------------------------------------------
# Query helper
# ----------------------------------------------------------------------

def get_session_for_user_or_403(
    session_id: str,
    user,
):
    """
    Retrieve a session and enforce access control.

    Missing sessions produce the normal 404 response.
    Existing but unauthorized sessions produce 403.

    This distinction prevents accidentally treating an authorization
    failure as a successful lookup.
    """
    if not _is_authenticated(user):
        raise PermissionDenied(
            "Authentication is required to access a session."
        )

    session = get_object_or_404(
        Session.objects.select_related(
            "user",
            "project",
        ),
        id=session_id,
    )

    if not user_can_access_session(
        user,
        session,
    ):
        raise PermissionDenied(
            "You do not have permission to access this session."
        )

    return session


def get_modifiable_session_or_403(
    session_id: str,
    user,
):
    """
    Retrieve a session and require modification permission.
    """
    session = get_session_for_user_or_403(
        session_id,
        user,
    )

    if not can_modify_session(
        user,
        session,
    ):
        raise PermissionDenied(
            "You do not have permission to modify this session."
        )

    return session


def get_deletable_session_or_403(
    session_id: str,
    user,
):
    """
    Retrieve a session and require deletion permission.
    """
    session = get_session_for_user_or_403(
        session_id,
        user,
    )

    if not can_delete_session(
        user,
        session,
    ):
        raise PermissionDenied(
            "You do not have permission to delete this session."
        )

    return session