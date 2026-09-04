"""Development settings for SatQuery AI."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Default to eager execution for fast local development and testing without Redis
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "True").lower() in ("true", "1")
CELERY_TASK_EAGER_PROPAGATES = True
