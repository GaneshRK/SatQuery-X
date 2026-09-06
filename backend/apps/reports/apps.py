"""
Django application configuration for the SatQuery-X report subsystem.
"""

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """
    Configuration for report generation and export.
    """

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.reports"

    label = "reports"

    verbose_name = "SatQuery-X Reports"