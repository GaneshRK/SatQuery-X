from django.apps import AppConfig


class AgentConfig(AppConfig):
    """
    Django application configuration for the SatQuery-X agent subsystem.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agent"
    label = "agent"