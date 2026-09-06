from django.apps import AppConfig


class GeospatialConfig(AppConfig):
    """
    Django application configuration for the SatQuery-X geospatial engine.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.geospatial"
    label = "geospatial"
    verbose_name = "Geospatial Processing"