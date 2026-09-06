from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    CurrentUserView,
    HealthView,
    OrganizationDetailView,
    OrganizationMemberListView,
    OrganizationProjectListView,
    RegisterView,
)

app_name = "accounts"

urlpatterns = [
    # Authentication
    path(
        "login/",
        TokenObtainPairView.as_view(),
        name="login",
    ),
    path(
        "refresh/",
        TokenRefreshView.as_view(),
        name="refresh",
    ),

    # Registration
    path(
        "register/",
        RegisterView.as_view(),
        name="register",
    ),

    # Current account
    path(
        "me/",
        CurrentUserView.as_view(),
        name="current_user",
    ),

    # Organization context
    path(
        "organization/",
        OrganizationDetailView.as_view(),
        name="organization",
    ),
    path(
        "organization/projects/",
        OrganizationProjectListView.as_view(),
        name="organization_projects",
    ),
    path(
        "organization/members/",
        OrganizationMemberListView.as_view(),
        name="organization_members",
    ),

    # Service health
    path(
        "health/",
        HealthView.as_view(),
        name="health",
    ),
]