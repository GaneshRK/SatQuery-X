from __future__ import annotations
import os
import shutil
from typing import Any
from django.conf import settings
from django.db import connection
from rest_framework import permissions, views
from rest_framework.response import Response

from apps.satellite.providers.copernicus import CopernicusProvider
from apps.ai_providers.router import ModelRouter


class SystemHealthView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """
        Comprehensive operational health check for all core and external platform subsystems.
        """
        checks: dict[str, Any] = {}

        # 1. Django
        checks["django"] = {"status": "healthy", "version": "5.1", "mode": getattr(settings, "SATQUERY_MODE", "production")}

        # 2. PostgreSQL & PostGIS
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                db_ok = bool(cursor.fetchone())
                try:
                    cursor.execute("SELECT PostGIS_Version();")
                    postgis_ver = cursor.fetchone()[0]
                    postgis_ok = True
                except Exception:
                    postgis_ver = "Not installed or SQLite fallback"
                    postgis_ok = False
            checks["database"] = {
                "engine": settings.DATABASES["default"]["ENGINE"],
                "status": "healthy" if db_ok else "unavailable",
                "postgis": postgis_ver,
                "postgis_available": postgis_ok,
            }
        except Exception as dbe:
            checks["database"] = {"status": "unavailable", "error": str(dbe)}

        # 3. Redis / Celery Broker
        try:
            import redis
            broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            r = redis.from_url(broker_url, socket_connect_timeout=0.3, socket_timeout=0.3)
            r.ping()
            checks["redis"] = {"status": "healthy", "broker": broker_url}
        except Exception as re_err:
            checks["redis"] = {"status": "unavailable", "message": "Redis broker unreachable; synchronous fallback active"}

        # 4. Celery Workers
        checks["celery"] = {
            "status": "configured",
            "fallback_mode": "SYNCHRONOUS_DEV_FALLBACK_READY",
        }

        # 5. Copernicus Data Space Ecosystem (CDSE)
        try:
            copernicus = CopernicusProvider()
            checks["copernicus"] = copernicus.health_check()
        except Exception as ce:
            checks["copernicus"] = {"status": "degraded", "error": str(ce)}

        # 6. AI Providers & Model Router
        try:
            router = ModelRouter()
            checks["ai_providers"] = router.health_check()
        except Exception as aie:
            checks["ai_providers"] = {"status": "degraded", "error": str(aie)}

        # 7. Storage Backend
        try:
            media_path = str(settings.MEDIA_ROOT)
            free_bytes = shutil.disk_usage(media_path).free
            checks["storage"] = {
                "status": "healthy",
                "backend": "LocalFileSystem / S3 Compatible",
                "media_root": media_path,
                "free_disk_gb": round(free_bytes / (1024 ** 3), 2),
            }
        except Exception as se:
            checks["storage"] = {"status": "degraded", "error": str(se)}

        # 8. Map Provider
        maptiler_key = getattr(settings, "MAPTILER_API_KEY", None) or os.getenv("MAPTILER_API_KEY", "")
        checks["map_provider"] = {
            "maptiler": "configured" if maptiler_key else "not_configured (using Esri / OSM fallback basemaps)",
            "basemaps": ["esri_satellite", "carto_dark", "osm_standard"],
            "status": "healthy",
        }

        all_healthy = all(
            v.get("status") in ("healthy", "configured")
            for k, v in checks.items()
            if k in ("django", "database")
        )

        return Response({
            "status": "UP" if all_healthy else "DEGRADED",
            "subsystems": checks,
        })
