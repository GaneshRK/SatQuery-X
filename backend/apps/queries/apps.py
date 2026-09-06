"""
Django application configuration for the SatQuery-X query subsystem.
"""

from django.apps import AppConfig


class QueriesConfig(AppConfig):
    """
    Configuration for conversational query execution.

    This app owns:
    - User queries
    - Planner/execution state
    - Specialist-agent execution steps
    - Evidence references
    - Final grounded answers
    """

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.queries"

    label = "queries"

    verbose_name = "SatQuery-X Queries"