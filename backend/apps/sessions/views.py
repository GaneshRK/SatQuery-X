from rest_framework import permissions, viewsets
from .models import Session
from .serializers import SessionSerializer


class SessionViewSet(viewsets.ModelViewSet):
    serializer_class = SessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Admins or judges can view all sessions; regular analysts view their own
        if getattr(user, "role", "demo") in ("admin", "judge") or user.is_staff:
            return Session.objects.all()
        return Session.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
