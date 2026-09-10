"""Stage 20 runtime/maintenance helpers.

These helpers are deliberately dependency-light so operators can use them in
CI and deployment checks without importing the full application stack.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProductionConfigResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_production_environment(environ: dict[str, str] | None = None) -> ProductionConfigResult:
    env = os.environ if environ is None else environ
    errors: list[str] = []
    warnings: list[str] = []

    secret = env.get("DJANGO_SECRET_KEY", "").strip()
    if len(secret) < 50 or secret.startswith("django-insecure-"):
        errors.append("DJANGO_SECRET_KEY must be at least 50 characters and must not be a Django insecure default.")

    hosts = [x.strip() for x in env.get("DJANGO_ALLOWED_HOSTS", "").split(",") if x.strip()]
    if not hosts:
        errors.append("DJANGO_ALLOWED_HOSTS must contain at least one host.")
    if "*" in hosts:
        errors.append("DJANGO_ALLOWED_HOSTS must not contain '*'.")

    if env.get("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}:
        errors.append("DJANGO_DEBUG must be False in production.")

    if env.get("SECURE_SSL_REDIRECT", "True").lower() not in {"1", "true", "yes"}:
        errors.append("SECURE_SSL_REDIRECT must be enabled in production.")

    if env.get("SESSION_COOKIE_SECURE", "True").lower() not in {"1", "true", "yes"}:
        errors.append("SESSION_COOKIE_SECURE must be enabled in production.")

    if env.get("CSRF_COOKIE_SECURE", "True").lower() not in {"1", "true", "yes"}:
        errors.append("CSRF_COOKIE_SECURE must be enabled in production.")

    if not env.get("DATABASE_URL", "").strip():
        warnings.append("DATABASE_URL is not set; production settings will use the configured default only if explicitly supported by deployment.")

    if not env.get("REDIS_URL", "").strip():
        warnings.append("REDIS_URL is not set; Celery/Redis-dependent features may be unavailable.")

    return ProductionConfigResult(not errors, tuple(errors), tuple(warnings))


def generate_secret(length: int = 64) -> str:
    """Generate a URL-safe Django secret suitable for production configuration."""
    if length < 50:
        raise ValueError("Production secrets must be at least 50 characters long.")
    value = secrets.token_urlsafe(length)
    return value[:length]


def ensure_directory(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target
