"""Production settings for SatQuery AI.

All security-sensitive values must be supplied through environment variables.
"""

from .base import *  # noqa: F403,F401

DEBUG = False

_secret = os.getenv("DJANGO_SECRET_KEY", "").strip()
if len(_secret) < 50 or _secret.startswith("django-insecure-"):
    raise RuntimeError("DJANGO_SECRET_KEY must be a strong production secret (50+ characters).")
SECRET_KEY = _secret

_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "").strip()
if not _hosts:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be configured in production.")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
if "*" in ALLOWED_HOSTS:
    raise RuntimeError("Wildcard DJANGO_ALLOWED_HOSTS is forbidden in production.")

_database_url = os.getenv("DATABASE_URL", "").strip()
if not _database_url:
    raise RuntimeError("DATABASE_URL must be configured in production.")
try:
    import dj_database_url
except ImportError as exc:
    raise RuntimeError("dj-database-url is required for production database configuration.") from exc
DATABASES["default"] = dj_database_url.parse(
    _database_url,
    conn_max_age=60,
    conn_health_checks=True,
)
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

if not CSRF_TRUSTED_ORIGINS:
    raise RuntimeError("CSRF_TRUSTED_ORIGINS must be configured in production.")
if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must be configured in production.")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "False").lower() in ("true", "1", "yes")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() in ("true", "1", "yes")

# Production uploads should not be served by Django's development static helper.
# Put media behind authenticated storage or a separate media service/reverse proxy.
