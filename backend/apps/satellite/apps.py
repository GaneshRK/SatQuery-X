"""
Django application configuration for the SatQuery-X satellite intelligence subsystem.
"""

from django.apps import AppConfig


class SatelliteConfig(AppConfig):
    """
    Configuration for satellite catalogue, acquisition, temporal analysis,
    synchronization, and monitoring services.
    """

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.satellite"

    label = "satellite"

    verbose_name = "SatQuery-X Satellite Intelligence"