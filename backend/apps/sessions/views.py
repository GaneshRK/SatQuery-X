from django.db.models import Q
from rest_framework import permissions, viewsets
from .models import Session
from .serializers import SessionSerializer


class SessionViewSet(viewsets.ModelViewSet):
    serializer_class = SessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        if role in ("ADMIN", "JUDGE", "OWNER", "DEMO") or user.is_staff or user.is_superuser:
            if user.organization:
                return Session.objects.filter(
                    Q(user__organization=user.organization)
                    | Q(project__organization=user.organization)
                    | Q(user=user)
                )
            return Session.objects.all()

        if user.organization:
            return Session.objects.filter(
                Q(user=user)
                | Q(user__organization=user.organization)
                | Q(project__organization=user.organization)
            )
        return Session.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
