"""
Operational health and readiness endpoints for SatQuery-X.

This module reports the real runtime state of the backend and its
external dependencies.

Design principles:
- Never report a dependency as healthy without checking it.
- Never expose passwords, tokens, credentials, or internal filesystem
  paths through the public health endpoint.
- Do not claim a fallback provider exists unless it is actually configured.
- Distinguish healthy, degraded, unavailable, and not_configured states.
- Keep health endpoints lightweight and safe for production deployment.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError
from rest_framework import permissions, status, views
from rest_framework.response import Response


def _safe_exception_message(exc: Exception) -> str:
    """
    Return a short operational error without exposing credentials or
    connection strings.
    """
    message = str(exc)

    sensitive_keys = (
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "api_key",
        "apikey",
    )

    lowered = message.lower()

    if any(key in lowered for key in sensitive_keys):
        return "Dependency check failed."

    if len(message) > 300:
        return message[:297] + "..."

    return message


def _status_from_checks(checks: dict[str, Any]) -> str:
    """
    Derive an overall service status from actual subsystem results.

    HEALTHY:
        All required checks are healthy.

    DEGRADED:
        Backend is operational but one or more optional/external
        dependencies are unavailable or not configured.

    DOWN:
        A core dependency required to serve the API is unavailable.
    """
    core_names = {
        "django",
        "database",
    }

    core_states = [
        checks[name].get("status")
        for name in core_names
        if name in checks
    ]

    if any(state in {"unavailable", "down"} for state in core_states):
        return "DOWN"

    if any(
        item.get("status") in {"degraded", "unavailable", "not_configured"}
        for item in checks.values()
        if isinstance(item, dict)
    ):
        return "DEGRADED"

    return "UP"


class SystemHealthView(views.APIView):
    """
    GET /system/health/

    Returns a safe operational health summary.

    Authentication is intentionally not required so load balancers,
    Kubernetes probes, and monitoring systems can use the endpoint.

    Detailed infrastructure information is deliberately omitted.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        checks: dict[str, Any] = {}

        # ------------------------------------------------------------------
        # 1. Django
        # ------------------------------------------------------------------
        try:
            import django

            checks["django"] = {
                "status": "healthy",
                "version": django.get_version(),
            }
        except Exception as exc:
            checks["django"] = {
                "status": "degraded",
                "error": _safe_exception_message(exc),
            }

        # ------------------------------------------------------------------
        # 2. Database / PostGIS
        # ------------------------------------------------------------------
        checks["database"] = self._check_database()

        # ------------------------------------------------------------------
        # 3. Redis
        # ------------------------------------------------------------------
        checks["redis"] = self._check_redis()

        # ------------------------------------------------------------------
        # 4. Celery
        # ------------------------------------------------------------------
        checks["celery"] = self._check_celery()

        # ------------------------------------------------------------------
        # 5. Copernicus CDSE
        # ------------------------------------------------------------------
        checks["copernicus"] = self._check_copernicus()

        # ------------------------------------------------------------------
        # 6. AI provider/model subsystem
        # ------------------------------------------------------------------
        checks["ai_providers"] = self._check_ai_providers()

        # ------------------------------------------------------------------
        # 7. Storage
        # ------------------------------------------------------------------
        checks["storage"] = self._check_storage()

        # ------------------------------------------------------------------
        # 8. Map provider configuration
        # ------------------------------------------------------------------
        checks["map_provider"] = self._check_map_provider()

        overall_status = _status_from_checks(checks)

        response_status = (
            status.HTTP_200_OK
            if overall_status in {"UP", "DEGRADED"}
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            {
                "status": overall_status,
                "service": "SatQuery-X",
                "subsystems": checks,
            },
            status=response_status,
        )

    # ======================================================================
    # Database
    # ======================================================================

    @staticmethod
    def _check_database() -> dict[str, Any]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

                if not result or result[0] != 1:
                    return {
                        "status": "unavailable",
                        "message": "Database query failed.",
                    }

                postgis_available = False
                postgis_version = None

                try:
                    cursor.execute("SELECT PostGIS_Version()")
                    row = cursor.fetchone()

                    if row and row[0]:
                        postgis_available = True
                        postgis_version = str(row[0])
                except Exception:
                    # PostGIS is optional for some development configurations.
                    pass

            response: dict[str, Any] = {
                "status": "healthy",
                "postgis_available": postgis_available,
            }

            if postgis_version:
                response["postgis_version"] = postgis_version

            return response

        except OperationalError:
            return {
                "status": "unavailable",
                "message": "Database connection unavailable.",
            }

        except Exception as exc:
            return {
                "status": "unavailable",
                "error": _safe_exception_message(exc),
            }

    # ======================================================================
    # Redis
    # ======================================================================

    @staticmethod
    def _check_redis() -> dict[str, Any]:
        broker_url = getattr(settings, "CELERY_BROKER_URL", None)

        if not broker_url:
            return {
                "status": "not_configured",
                "message": "Celery broker is not configured.",
            }

        try:
            import redis

            client = redis.from_url(
                broker_url,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )

            client.ping()

            return {
                "status": "healthy",
            }

        except ImportError:
            return {
                "status": "unavailable",
                "message": "Redis client package is not installed.",
            }

        except Exception:
            return {
                "status": "unavailable",
                "message": "Redis broker is unreachable.",
            }

    # ======================================================================
    # Celery
    # ======================================================================

    @staticmethod
    def _check_celery() -> dict[str, Any]:
        try:
            from celery import current_app

            broker_url = current_app.conf.broker_url

            if not broker_url:
                return {
                    "status": "not_configured",
                    "message": "Celery broker is not configured.",
                }

            return {
                "status": "configured",
                "broker_configured": True,
            }

        except Exception as exc:
            return {
                "status": "degraded",
                "error": _safe_exception_message(exc),
            }

    # ======================================================================
    # Copernicus CDSE
    # ======================================================================

    @staticmethod
    def _check_copernicus() -> dict[str, Any]:
        try:
            from apps.satellite.providers.copernicus import CopernicusProvider

            provider = CopernicusProvider()

            health = provider.health_check()

            if not isinstance(health, dict):
                return {
                    "status": "degraded",
                    "message": "Provider returned an invalid health response.",
                }

            safe_health = {
                key: value
                for key, value in health.items()
                if key.lower()
                not in {
                    "token",
                    "access_token",
                    "refresh_token",
                    "password",
                    "secret",
                    "client_secret",
                    "authorization",
                }
            }

            provider_status = str(
                safe_health.get("status", "degraded")
            ).lower()

            if provider_status in {"healthy", "ok", "up"}:
                safe_health["status"] = "healthy"
            elif provider_status in {"not_configured", "unconfigured"}:
                safe_health["status"] = "not_configured"
            else:
                safe_health["status"] = "degraded"

            return safe_health

        except Exception as exc:
            return {
                "status": "degraded",
                "message": "Copernicus provider health check failed.",
                "error": _safe_exception_message(exc),
            }

    # ======================================================================
    # AI providers
    # ======================================================================

    @staticmethod
    def _check_ai_providers() -> dict[str, Any]:
        try:
            from apps.ai_providers.router import ModelRouter

            router = ModelRouter()

            health = router.health_check()

            if not isinstance(health, dict):
                return {
                    "status": "degraded",
                    "message": "AI router returned an invalid health response.",
                }

            provider_states = []

            for key, value in health.items():
                if isinstance(value, dict):
                    provider_states.append(
                        str(value.get("status", "")).lower()
                    )

            if provider_states and all(
                state in {"healthy", "ok", "up", "configured"}
                for state in provider_states
            ):
                overall = "healthy"
            elif any(
                state in {"healthy", "ok", "up", "configured"}
                for state in provider_states
            ):
                overall = "degraded"
            else:
                overall = "degraded"

            return {
                "status": overall,
                "providers": health,
            }

        except ImportError:
            return {
                "status": "not_configured",
                "message": "AI provider router is not available.",
            }

        except Exception as exc:
            return {
                "status": "degraded",
                "message": "AI provider health check failed.",
                "error": _safe_exception_message(exc),
            }

    # ======================================================================
    # Storage
    # ======================================================================

    @staticmethod
    def _check_storage() -> dict[str, Any]:
        try:
            media_root = getattr(settings, "MEDIA_ROOT", None)

            if not media_root:
                return {
                    "status": "not_configured",
                    "message": "MEDIA_ROOT is not configured.",
                }

            media_path = os.path.abspath(str(media_root))

            if not os.path.exists(media_path):
                return {
                    "status": "unavailable",
                    "message": "Configured media storage path does not exist.",
                }

            if not os.path.isdir(media_path):
                return {
                    "status": "unavailable",
                    "message": "Configured media storage path is not a directory.",
                }

            usage = shutil.disk_usage(media_path)

            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)

            return {
                "status": "healthy",
                "backend": "local_filesystem",
                "free_disk_gb": round(free_gb, 2),
                "total_disk_gb": round(total_gb, 2),
            }

        except Exception as exc:
            return {
                "status": "degraded",
                "error": _safe_exception_message(exc),
            }

    # ======================================================================
    # Map provider
    # ======================================================================

    @staticmethod
    def _check_map_provider() -> dict[str, Any]:
        maptiler_key = (
            getattr(settings, "MAPTILER_API_KEY", None)
            or os.getenv("MAPTILER_API_KEY")
        )

        if maptiler_key:
            return {
                "status": "configured",
                "provider": "maptiler",
            }

        configured_provider = getattr(
            settings,
            "MAP_PROVIDER",
            None,
        )

        if configured_provider:
            return {
                "status": "configured",
                "provider": str(configured_provider),
            }

        return {
            "status": "not_configured",
            "message": (
                "No explicit external map provider is configured. "
                "Map functionality requiring a provider may be unavailable."
            ),
        }


class SystemReadinessView(views.APIView):
    """
    Lightweight readiness endpoint.

    Unlike the detailed health endpoint, this is intended for deployment
    probes. It only verifies whether the Django application can reach its
    primary database.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        database = SystemHealthView._check_database()

        if database.get("status") != "healthy":
            return Response(
                {
                    "ready": False,
                    "status": "NOT_READY",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "ready": True,
                "status": "READY",
            },
            status=status.HTTP_200_OK,
        )


class SystemLivenessView(views.APIView):
    """
    Minimal liveness endpoint.

    A successful response means the Django application process is alive.
    It intentionally performs no network or database checks.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                "alive": True,
                "status": "ALIVE",
            },
            status=status.HTTP_200_OK,
        )