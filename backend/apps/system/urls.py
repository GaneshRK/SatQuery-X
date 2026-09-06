"""
URL configuration for the SatQuery-X system subsystem.
"""

from django.urls import path

from .views import (
    SystemHealthView,
    SystemLivenessView,
    SystemReadinessView,
)

app_name = "system"

urlpatterns = [
    path(
        "health/",
        SystemHealthView.as_view(),
        name="health",
    ),
    path(
        "readiness/",
        SystemReadinessView.as_view(),
        name="readiness",
    ),
    path(
        "liveness/",
        SystemLivenessView.as_view(),
        name="liveness",
    ),
]