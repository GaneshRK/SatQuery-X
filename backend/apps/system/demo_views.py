"""
Demo and showcase endpoints for SatQuery-X.

This module intentionally does NOT create synthetic satellite imagery,
fabricated geospatial metadata, fake measurements, or artificial analysis
results.

A demo scenario is therefore a workflow template. It can only be executed
when the required real imagery already exists in the authenticated user's
workspace.

The endpoint helps the frontend:
    1. Discover supported showcase workflows.
    2. Select a scenario.
    3. Validate the required inputs.
    4. Create a real query using those inputs.
    5. Execute the normal SatQuery-X orchestration pipeline.

It never bypasses the production analysis pipeline.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.imagery.models import ImageAsset, ImagePair
from apps.queries.models import Query
from apps.queries.tasks import run_query_task
from apps.sessions.models import Session


DEMO_SCENARIOS: dict[str, dict[str, Any]] = {
    "scenario_1_caption": {
        "key": "scenario_1_caption",
        "title": "Scenario 1: Single-Image Scene Captioning",
        "description": (
            "Natural-language scene understanding and visual land-cover "
            "description from a real remote-sensing image."
        ),
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "required_inputs": 1,
        "default_query": (
            "Describe the overall scene and visible land-cover structure "
            "in this satellite image."
        ),
    },
    "scenario_2_vqa": {
        "key": "scenario_2_vqa",
        "title": "Scenario 2: Single-Image Remote-Sensing VQA",
        "description": (
            "Question answering grounded in an uploaded remote-sensing "
            "image and its available evidence."
        ),
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "required_inputs": 1,
        "default_query": (
            "Is there visible water in this remote-sensing scene?"
        ),
    },
    "scenario_3_grounding": {
        "key": "scenario_3_grounding",
        "title": "Scenario 3: Single-Image Visual Grounding",
        "description": (
            "Visual localization of a requested feature using the "
            "grounding pipeline."
        ),
        "sensor": "OPTICAL",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "required_inputs": 1,
        "default_query": (
            "Locate and bound the visible transportation infrastructure "
            "in this image."
        ),
    },
    "scenario_4_change_detection": {
        "key": "scenario_4_change_detection",
        "title": "Scenario 4: Bi-Temporal Change Detection",
        "description": (
            "Change analysis between two compatible real observations, "
            "with measurements reported only when supported by evidence."
        ),
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "required_inputs": 2,
        "default_query": (
            "Detect meaningful surface changes between the two images "
            "and report the measured change evidence."
        ),
    },
    "scenario_5_change_vqa": {
        "key": "scenario_5_change_vqa",
        "title": "Scenario 5: Bi-Temporal Change VQA",
        "description": (
            "Natural-language questioning over an existing bi-temporal "
            "change-analysis result."
        ),
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "required_inputs": 2,
        "default_query": (
            "What meaningful changes are supported by the evidence "
            "between the two observations?"
        ),
    },
    "scenario_6_optical_sar_fusion": {
        "key": "scenario_6_optical_sar_fusion",
        "title": "Scenario 6: Optical + SAR Cross-Modal Fusion",
        "description": (
            "Cross-modal reasoning using real optical and SAR observations "
            "when both are available and spatially compatible."
        ),
        "sensor": "OPTICAL + SAR",
        "modality": "CROSS_MODAL",
        "mode": "CROSS_MODAL_PAIR",
        "required_inputs": 2,
        "default_query": (
            "Fuse the available optical and SAR evidence and identify "
            "features supported by both modalities."
        ),
    },
    "scenario_7_multiturn": {
        "key": "scenario_7_multiturn",
        "title": "Scenario 7: Multi-Turn Conversational Follow-Up",
        "description": (
            "Context-preserving follow-up questions using the active "
            "session, imagery, map context, and previous evidence."
        ),
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "required_inputs": 2,
        "default_query": (
            "Where are the primary supported changes located?"
        ),
        "follow_up_query": (
            "How much measured area does the detected change represent?"
        ),
    },
}


def _scenario_response_payload() -> dict[str, Any]:
    """
    Return scenario metadata without exposing implementation internals.
    """

    return {
        "platform": "SatQuery-X",
        "scenarios": list(DEMO_SCENARIOS.values()),
        "count": len(DEMO_SCENARIOS),
        "data_policy": {
            "synthetic_imagery": False,
            "fabricated_geospatial_metadata": False,
            "fabricated_measurements": False,
            "analysis_pipeline": "canonical_satquery_orchestration",
        },
    }


def _owned_assets(request, asset_ids: list[str]) -> list[ImageAsset]:
    """
    Resolve only imagery belonging to the authenticated user.

    A demo endpoint must never allow an arbitrary UUID to expose another
    user's imagery.
    """

    if not asset_ids:
        return []

    queryset = (
        ImageAsset.objects
        .filter(id__in=asset_ids)
        .select_related("session")
        .distinct()
    )

    assets = list(queryset)

    if len(assets) != len(set(asset_ids)):
        return []

    for asset in assets:
        if asset.session.user_id != request.user.id:
            return []

    return assets


def _asset_is_usable(asset: ImageAsset) -> bool:
    """
    A demo can only run against imagery that has passed ingestion/validation.
    """

    processing_status = str(
        getattr(asset, "processing_status", "") or ""
    ).upper()

    return processing_status in {
        "VALIDATED",
        "READY",
        "PROCESSED",
        "COMPLETED",
    }


def _validate_asset_requirements(
    scenario: dict[str, Any],
    assets: list[ImageAsset],
) -> tuple[bool, str | None]:
    """
    Validate the minimum inputs required by a scenario.

    Scientific compatibility is intentionally not fabricated here.
    The normal imagery/pair validation pipeline remains authoritative.
    """

    required_inputs = int(scenario["required_inputs"])

    if len(assets) < required_inputs:
        return (
            False,
            (
                f"This scenario requires at least {required_inputs} "
                f"real imagery input(s). "
                f"Received {len(assets)}."
            ),
        )

    unusable = [
        str(asset.id)
        for asset in assets
        if not _asset_is_usable(asset)
    ]

    if unusable:
        return (
            False,
            (
                "One or more selected imagery assets are not validated "
                f"or ready for analysis: {', '.join(unusable)}."
            ),
        )

    mode = str(scenario["mode"]).upper()

    if mode == "CROSS_MODAL_PAIR":
        modalities = {
            str(getattr(asset, "modality", "") or "").upper()
            for asset in assets[:2]
        }

        if "OPTICAL" not in modalities or "SAR" not in modalities:
            return (
                False,
                (
                    "The optical + SAR scenario requires one real optical "
                    "asset and one real SAR asset."
                ),
            )

    return True, None


def _find_existing_pair(
    session: Session,
    asset_a: ImageAsset,
    asset_b: ImageAsset,
    pair_type: str,
) -> ImagePair | None:
    """
    Find an existing pair instead of creating a fabricated compatibility
    relationship.
    """

    pair = (
        ImagePair.objects
        .filter(
            session=session,
            pair_type=pair_type,
        )
        .filter(
            image_a=asset_a,
            image_b=asset_b,
        )
        .first()
    )

    if pair is not None:
        return pair

    return (
        ImagePair.objects
        .filter(
            session=session,
            pair_type=pair_type,
            image_a=asset_b,
            image_b=asset_a,
        )
        .first()
    )


def _pair_is_usable(pair: ImagePair | None) -> bool:
    """
    Only an explicitly validated/compatible pair can be used for pair
    scenarios.
    """

    if pair is None:
        return False

    compatibility = str(
        getattr(pair, "compatibility_status", "") or ""
    ).upper()

    return compatibility in {
        "COMPATIBLE",
        "VALIDATED",
        "READY",
    }


def _query_payload(
    query: Query,
    scenario: dict[str, Any],
    session: Session,
    assets: list[ImageAsset],
    pair: ImagePair | None,
) -> dict[str, Any]:
    """
    Build a frontend-safe bootstrap response.

    The answer and confidence are returned only from the actual Query
    record; this endpoint never invents them.
    """

    return {
        "status": "bootstrapped",
        "scenario": scenario,
        "session_id": str(session.id),
        "image_ids": [str(asset.id) for asset in assets],
        "image_id": str(assets[0].id) if assets else None,
        "image_a_id": str(assets[0].id) if assets else None,
        "image_b_id": (
            str(assets[1].id)
            if len(assets) > 1
            else None
        ),
        "pair_id": str(pair.id) if pair else None,
        "query_id": str(query.id),
        "query_status": query.status,
        "answer": query.answer,
        "confidence": query.confidence,
        "clarification_required": getattr(
            query,
            "clarification_required",
            False,
        ),
        "clarification": getattr(
            query,
            "clarification",
            None,
        ),
    }


class DemoScenariosListView(views.APIView):
    """
    List the supported SatQuery-X showcase workflows.

    Authentication is not required because this endpoint exposes only
    scenario definitions and no user data.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        return Response(
            _scenario_response_payload(),
            status=status.HTTP_200_OK,
        )


class BootstrapDemoScenarioView(views.APIView):
    """
    Bootstrap a showcase workflow using real user-owned imagery.

    Expected request body:

        {
            "asset_ids": ["uuid-1", "uuid-2"],
            "session_id": "optional-existing-session-uuid",
            "query": "optional custom question",
            "execute": true
        }

    If no assets are supplied, the endpoint refuses to fabricate imagery.
    """

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, scenario_key: str, *args, **kwargs):
        if scenario_key not in DEMO_SCENARIOS:
            return Response(
                {
                    "error": "Invalid scenario.",
                    "scenario_key": scenario_key,
                    "available_scenarios": list(
                        DEMO_SCENARIOS.keys()
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        scenario = DEMO_SCENARIOS[scenario_key]

        raw_asset_ids = request.data.get("asset_ids", [])

        if isinstance(raw_asset_ids, str):
            raw_asset_ids = [raw_asset_ids]

        if not isinstance(raw_asset_ids, list):
            return Response(
                {
                    "error": "asset_ids must be a list of imagery UUIDs."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset_ids = [
            str(value).strip()
            for value in raw_asset_ids
            if str(value).strip()
        ]

        assets = _owned_assets(request, asset_ids)

        if asset_ids and not assets:
            return Response(
                {
                    "error": (
                        "No valid user-owned imagery assets were found "
                        "for the supplied asset_ids."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        valid, validation_error = _validate_asset_requirements(
            scenario,
            assets,
        )

        if not valid:
            return Response(
                {
                    "error": validation_error,
                    "scenario": scenario,
                    "required_inputs": scenario["required_inputs"],
                    "received_inputs": len(assets),
                    "hint": (
                        "Upload and validate real imagery first, then "
                        "select those assets for the demo."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_session_id = request.data.get("session_id")

        session = None

        if requested_session_id:
            try:
                session = (
                    Session.objects
                    .filter(
                        id=requested_session_id,
                        user=request.user,
                    )
                    .first()
                )
            except Exception:
                session = None

            if session is None:
                return Response(
                    {
                        "error": (
                            "The requested session does not exist "
                            "or does not belong to the authenticated user."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        if session is None:
            session = Session.objects.create(
                user=request.user,
                name=f"SatQuery-X Demo — {scenario['title']}",
            )

        # Assets may already belong to another session. They are not moved.
        # The Query uses them as explicit inputs instead.
        for asset in assets:
            if asset.session_id != session.id:
                # Session membership is intentionally not rewritten here.
                # Cross-session input handling belongs to the normal query
                # subsystem.
                pass

        pair = None

        if scenario["mode"] in {
            "BI_TEMPORAL",
            "CROSS_MODAL_PAIR",
        }:
            if len(assets) < 2:
                return Response(
                    {
                        "error": (
                            "A pair-based scenario requires two real "
                            "imagery assets."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pair_type = (
                "CROSS_MODAL"
                if scenario["mode"] == "CROSS_MODAL_PAIR"
                else "BI_TEMPORAL"
            )

            pair = _find_existing_pair(
                session,
                assets[0],
                assets[1],
                pair_type,
            )

            if not _pair_is_usable(pair):
                return Response(
                    {
                        "error": (
                            "No validated compatible imagery pair exists "
                            "for the selected assets in this session."
                        ),
                        "pair_type": pair_type,
                        "image_ids": [
                            str(assets[0].id),
                            str(assets[1].id),
                        ],
                        "hint": (
                            "Create and validate the pair through the "
                            "normal imagery pipeline before running "
                            "this showcase scenario."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        query_text = str(
            request.data.get("query")
            or scenario["default_query"]
        ).strip()

        if not query_text:
            return Response(
                {"error": "A non-empty query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        detected_mode = (
            "CROSS_MODAL"
            if scenario["mode"] == "CROSS_MODAL_PAIR"
            else scenario["mode"]
        )

        query_kwargs: dict[str, Any] = {
            "session": session,
            "user": request.user,
            "text": query_text,
            "detected_mode": detected_mode,
        }

        if assets:
            query_kwargs["image"] = assets[0]

        if pair is not None:
            query_kwargs["image_pair"] = pair

        query = Query.objects.create(**query_kwargs)

        # Use the normal query task. No demo-specific model execution,
        # fabricated answer, confidence, geometry, or measurement is used.
        execute = request.data.get("execute", True)

        if isinstance(execute, str):
            execute = execute.lower() not in {
                "false",
                "0",
                "no",
            }

        if execute:
            try:
                result = run_query_task.delay(str(query.id))

                return Response(
                    {
                        **_query_payload(
                            query,
                            scenario,
                            session,
                            assets,
                            pair,
                        ),
                        "execution": {
                            "queued": True,
                            "task_id": str(result.id),
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )

            except Exception as exc:
                query.refresh_from_db()

                return Response(
                    {
                        **_query_payload(
                            query,
                            scenario,
                            session,
                            assets,
                            pair,
                        ),
                        "execution": {
                            "queued": False,
                            "error": str(exc),
                        },
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                **_query_payload(
                    query,
                    scenario,
                    session,
                    assets,
                    pair,
                ),
                "execution": {
                    "queued": False,
                    "message": (
                        "Query created but execution was disabled "
                        "by the request."
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )