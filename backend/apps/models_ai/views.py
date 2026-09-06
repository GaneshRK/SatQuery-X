"""
SatQuery-X AI Model Registry API views.

Provides read-only endpoints for:
- Listing registered specialist models
- Inspecting one specialist model
- Inspecting runtime model-manager status

These endpoints expose model capabilities and runtime state only.
They do not execute inference.
"""

from __future__ import annotations

import logging

from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.agent.registry import (
    list_models_info,
    load_registry_config,
)
from .manager import model_manager

logger = logging.getLogger(__name__)


class ModelRegistryListView(views.APIView):
    """
    GET /api/models/

    Return the models known by the SatQuery-X agent registry.
    """

    permission_classes = [
        permissions.AllowAny
    ]

    def get(self, request):
        try:
            models = list_models_info()

            return Response(
                {
                    "status": "ok",
                    "count": len(models)
                    if hasattr(models, "__len__")
                    else None,
                    "models": models,
                    "runtime": {
                        "device": model_manager.device,
                        "dtype": model_manager.dtype,
                        "mode": model_manager.mode,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            logger.exception(
                "Unable to retrieve model registry."
            )

            return Response(
                {
                    "status": "error",
                    "error": "Unable to retrieve model registry.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ModelRegistryDetailView(views.APIView):
    """
    GET /api/models/<model_id>/

    Return configuration and runtime information for one model.
    """

    permission_classes = [
        permissions.AllowAny
    ]

    def get(
        self,
        request,
        model_id,
    ):
        try:
            cfg = load_registry_config()

            if not isinstance(
                cfg,
                dict,
            ):
                return Response(
                    {
                        "status": "error",
                        "error": "Invalid model registry configuration.",
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Registry IDs are normally uppercase, but accepting either
            # case makes the API less fragile.
            requested_id = str(
                model_id
            ).strip()

            info = cfg.get(
                requested_id
            )

            if info is None:
                uppercase_id = (
                    requested_id.upper()
                )

                info = cfg.get(
                    uppercase_id
                )

                if info is not None:
                    requested_id = uppercase_id

            if info is None:
                return Response(
                    {
                        "status": "error",
                        "error": (
                            f"Model '{requested_id}' not found."
                        ),
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            runtime = (
                model_manager.model_status(
                    requested_id
                )
            )

            response_data = {
                "status": "ok",
                "id": requested_id,
                "configuration": info,
                "runtime": runtime,
            }

            return Response(
                response_data,
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                "Unable to retrieve model '%s'.",
                model_id,
            )

            return Response(
                {
                    "status": "error",
                    "error": (
                        "Unable to retrieve model information."
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ModelRuntimeHealthView(views.APIView):
    """
    GET /api/models/health/

    Runtime health information for the specialist model manager.
    """

    permission_classes = [
        permissions.AllowAny
    ]

    def get(
        self,
        request,
    ):
        try:
            return Response(
                model_manager.health_check(),
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                "Unable to retrieve model runtime health."
            )

            return Response(
                {
                    "status": "error",
                    "error": (
                        "Unable to retrieve model runtime health."
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


__all__ = [
    "ModelRegistryListView",
    "ModelRegistryDetailView",
    "ModelRuntimeHealthView",
]