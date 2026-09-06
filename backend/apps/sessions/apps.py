"""
Django application configuration for the SatQuery-X session subsystem.
"""

from django.apps import AppConfig


class SessionsConfig(AppConfig):
    """
    Application configuration for conversational analysis sessions.
    """

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.sessions"

    # Keep the existing database app label for migration compatibility.
    label = "analysis_sessions"

    verbose_name = "SatQuery-X Analysis Sessions"