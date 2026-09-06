"""
URL configuration for the SatQuery-X session subsystem.
"""

from rest_framework.routers import DefaultRouter

from .views import SessionViewSet


app_name = "sessions"


router = DefaultRouter()

router.register(
    r"",
    SessionViewSet,
    basename="session",
)


urlpatterns = router.urls