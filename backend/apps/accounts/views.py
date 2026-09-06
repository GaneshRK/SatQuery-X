from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Organization, Project
from .serializers import (
    OrganizationSerializer,
    ProjectSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class CurrentUserView(APIView):
    """
    Return the authenticated user's current account information.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(
            request.user,
            context={"request": request},
        )
        return Response(serializer.data)


class RegisterView(generics.CreateAPIView):
    """
    Public registration endpoint.

    Every publicly registered account starts as an ANALYST.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        response_serializer = UserSerializer(
            user,
            context={"request": request},
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(APIView):
    """
    Return the authenticated user's organization.

    Users without an organization receive 404 instead of seeing
    another tenant's data.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organization = request.user.organization

        if organization is None:
            return Response(
                {
                    "detail": "Your account is not associated with an organization."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OrganizationSerializer(
            organization,
            context={"request": request},
        )

        return Response(serializer.data)


class OrganizationProjectListView(generics.ListAPIView):
    """
    List projects belonging only to the authenticated user's organization.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        organization = self.request.user.organization

        if organization is None:
            return Project.objects.none()

        return (
            Project.objects
            .filter(organization=organization)
            .select_related("organization")
            .order_by("-created_at")
        )


class OrganizationMemberListView(generics.ListAPIView):
    """
    List members of the authenticated user's organization.

    This endpoint is intentionally organization-scoped.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        organization = self.request.user.organization

        if organization is None:
            return User.objects.none()

        return (
            User.objects
            .filter(organization=organization)
            .select_related("organization")
            .order_by("username")
        )


class HealthView(APIView):
    """
    Lightweight authenticated accounts health endpoint.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "service": "accounts",
                "status": "ok",
                "authenticated": True,
            }
        )