"""
Multi-tenancy and session access control module.
Enforces Organization -> Project -> Session scoping per Phase 10 / §10.
"""

from rest_framework.exceptions import PermissionDenied


def user_can_access_session(user, session) -> bool:
    """
    Evaluates whether a user can access a given session based on:
    1. Superuser / Staff status.
    2. Direct ownership (session.user == user).
    3. Organization-level role (OWNER, ADMIN, JUDGE).
    4. Project-level membership within the same organization.
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Direct owner
    if session.user_id == user.id:
        return True

    role = (getattr(user, "role", "") or "").upper()
    user_org = getattr(user, "organization", None)

    # Privileged roles (Judge, Admin, Owner, Demo) within same organization or global
    if role in ("ADMIN", "OWNER", "JUDGE", "DEMO"):
        if not user_org:
            # If user has no organization set, allow access if judge/superuser/admin/demo
            return role in ("JUDGE", "ADMIN", "OWNER", "DEMO")
        # Check session user's org or session project's org
        session_user_org = getattr(session.user, "organization", None)
        if session_user_org and session_user_org.id == user_org.id:
            return True
        if session.project and session.project.organization_id == user_org.id:
            return True

    # Regular analyst / viewer in same organization with shared project or user org
    if user_org:
        if session.project and session.project.organization_id == user_org.id:
            return True
        session_user_org = getattr(session.user, "organization", None)
        if session_user_org and session_user_org.id == user_org.id:
            return True

    return False


def get_session_for_user_or_403(session_id: str, user):
    """
    Retrieves a Session by ID and verifies the user has access.
    Raises Http404 if not found, PermissionDenied if unauthorized.
    """
    from django.shortcuts import get_object_or_404
    from apps.sessions.models import Session

    session = get_object_or_404(Session, id=session_id)
    if not user_can_access_session(user, session):
        raise PermissionDenied("You do not have permission to access this session.")
    return session
