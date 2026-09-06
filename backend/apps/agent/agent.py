"""
SatQuery-X Master Agent Orchestrator

Responsibilities
----------------
1. Resolve conversation/session context.
2. Understand the user's request.
3. Resolve image, image-pair, map/AOI and location context.
4. Validate that the requested analysis is actually possible.
5. Build an execution plan.
6. Delegate execution to AgentExecutor.
7. Persist the final evidence-backed result.
8. Maintain conversational memory.
9. Never fabricate imagery, coordinates, measurements, dates or confidence.

Architecture
------------

User Query
    |
    v
Master Agent
    |
    +--> Context / Memory
    |
    +--> Query Understanding
    |
    +--> Input Resolution
    |
    +--> Validation
    |
    +--> Planning
    |
    +--> AgentExecutor
             |
             +--> Preprocessing
             +--> Satellite Retrieval
             +--> Single Image Analysis
             +--> Multi Image Analysis
             +--> GIS / Location
             +--> Specialized Analysis
             +--> Evidence Validation
             +--> Answer Composition
    |
    v
Evidence-backed response
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.agent.executor import AgentExecutor
from apps.agent.planner import create_execution_plan
from apps.agent.understander import understand_query
from apps.agent.validator import validate_agent_inputs
from apps.queries.models import Query

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Query model only supports these modes.
QUERY_MODES = {
    "SINGLE_IMAGE",
    "BI_TEMPORAL",
    "CROSS_MODAL",
}

# The database model currently exposes these task values.
# The understander may internally use additional intent names, so those
# internal names are preserved in structured_plan rather than blindly
# writing them into detected_task.
QUERY_TASKS = {
    "VQA",
    "CAPTION",
    "GROUNDING",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "OPTICAL_SAR_FUSION",
    "MISSION",
}


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return a dictionary without throwing on malformed context."""

    if isinstance(value, dict):
        return dict(value)

    return {}


def _safe_list(value: Any) -> list[Any]:
    """Return a list without throwing on malformed context."""

    if isinstance(value, list):
        return list(value)

    if isinstance(value, tuple):
        return list(value)

    return []


def _json_safe(value: Any) -> Any:
    """Convert common non-JSON values into serializable structures."""

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass

    try:
        import uuid

        if isinstance(value, uuid.UUID):
            return str(value)
    except Exception:
        pass

    return str(value)


def _intent_name(intent: Any) -> str:
    value = getattr(intent, "intent", None)

    if value is None:
        return "UNKNOWN"

    return str(value).strip()


def _intent_target(intent: Any) -> str | None:
    value = getattr(intent, "target", None)

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _intent_location(intent: Any) -> dict[str, Any]:
    location = getattr(intent, "location", None)

    if isinstance(location, dict):
        return dict(location)

    return {}


def _intent_time_range(intent: Any) -> dict[str, Any]:
    value = getattr(intent, "time_range", None)

    if isinstance(value, dict):
        return dict(value)

    return {}


def _has_spatial_context(
    intent: Any,
    session_context: dict[str, Any],
) -> bool:
    """
    Determine whether a real spatial context is available.

    We deliberately do not invent a default geographic location.
    """

    location = _intent_location(intent)

    if location:
        if location.get("bbox"):
            return True

        if location.get("geometry"):
            return True

        if location.get("coords"):
            return True

        if location.get("name"):
            return True

    for key in (
        "active_aoi",
        "aoi_geometry",
        "current_viewport",
        "selected_area",
        "active_region",
    ):
        if session_context.get(key):
            return True

    visual_state = session_context.get(
        "current_visual_state"
    )

    if isinstance(visual_state, dict):
        for key in (
            "active_pin",
            "selected_location",
            "aoi_geometry",
            "viewport",
        ):
            if visual_state.get(key):
                return True

    return False


def _extract_bbox(value: Any) -> list[float] | None:
    """Normalize a real bbox into [west, south, east, north]."""

    if isinstance(value, dict):
        keys = (
            "west",
            "south",
            "east",
            "north",
        )

        if all(key in value for key in keys):
            try:
                return [
                    float(value["west"]),
                    float(value["south"]),
                    float(value["east"]),
                    float(value["north"]),
                ]
            except (TypeError, ValueError):
                return None

    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            return [
                float(value[0]),
                float(value[1]),
                float(value[2]),
                float(value[3]),
            ]
        except (TypeError, ValueError):
            return None

    return None


def _bbox_intersects(
    bbox_a: Any,
    bbox_b: Any,
) -> bool:
    """
    Test bounding-box intersection.

    If either bbox cannot be interpreted, return True rather than falsely
    claiming that two datasets do not overlap.
    """

    a = _extract_bbox(bbox_a)
    b = _extract_bbox(bbox_b)

    if not a or not b:
        return True

    west_a, south_a, east_a, north_a = a
    west_b, south_b, east_b, north_b = b

    if west_a > east_b:
        return False

    if east_a < west_b:
        return False

    if south_a > north_b:
        return False

    if north_a < south_b:
        return False

    return True


# ---------------------------------------------------------------------------
# Master Agent
# ---------------------------------------------------------------------------


class Agent:
    """
    Top-level SatQuery-X Master Orchestrator.

    This class is intentionally thin.

    It should decide:
        What does the user want?
        What evidence/context is available?
        Is the request executable?
        What plan should be executed?

    It should NOT:
        - invent satellite observations
        - generate fake raster data
        - invent confidence scores
        - calculate fake areas
        - create fake coordinates
        - contain hardcoded location-specific scientific answers
        - duplicate specialist-agent logic
    """

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    @classmethod
    def _build_session_context(
        cls,
        query: Query,
        supplied_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Merge persisted session context with context supplied by the request.

        Request context wins over stale persisted context.
        """

        context: dict[str, Any] = {}

        session = getattr(query, "session", None)

        if session is not None:
            persisted = getattr(
                session,
                "conversation_context",
                None,
            )

            if isinstance(persisted, dict):
                context.update(
                    persisted
                )

        if isinstance(supplied_context, dict):
            context.update(
                supplied_context
            )

        # Conversation history is useful to the understander.
        if session is not None:
            history = getattr(
                session,
                "conversation_history",
                None,
            )

            if isinstance(history, list):
                context["conversation_history"] = history

        # Keep the current query available to downstream agents.
        context["current_query_id"] = str(
            query.id
        )

        context["current_query"] = query.text

        # Current image information.
        image_count = 0

        try:
            image_count = query.session.imagery_assets.count()
        except Exception:
            pass

        context["image_count"] = image_count

        context["has_images"] = (
            image_count > 0
            or query.image_id is not None
            or query.image_pair_id is not None
        )

        # Current explicit image/pair references.
        if query.image_id:
            context["current_image_id"] = str(
                query.image_id
            )

        if query.image_pair_id:
            context["current_image_pair_id"] = str(
                query.image_pair_id
            )

        return context

    # ------------------------------------------------------------------
    # Input resolution
    # ------------------------------------------------------------------

    @classmethod
    def _get_validated_assets(
        cls,
        query: Query,
    ) -> list[Any]:
        """
        Resolve actual uploaded imagery.

        Only existing database assets are returned.
        """

        assets: list[Any] = []

        if query.image is not None:
            assets.append(
                query.image
            )

        pair = query.image_pair

        if pair is not None:
            for field_name in (
                "image_a",
                "image_b",
            ):
                asset = getattr(
                    pair,
                    field_name,
                    None,
                )

                if asset is not None and asset not in assets:
                    assets.append(
                        asset
                    )

        # If explicit query references are absent, use validated session
        # assets as candidates.
        if not assets and query.session is not None:
            try:
                queryset = (
                    query.session.imagery_assets
                    .filter(
                        processing_status="VALIDATED"
                    )
                )

                for asset in queryset:
                    if asset not in assets:
                        assets.append(
                            asset
                        )

            except Exception as exc:
                logger.debug(
                    "Unable to resolve session imagery: %s",
                    exc,
                )

        return assets

    @classmethod
    def _select_pair(
        cls,
        query: Query,
        intent: Any,
        assets: list[Any],
    ) -> Any | None:
        """
        Resolve a real ImagePair when one exists.

        We never construct a pair merely to make validation pass.
        """

        if query.image_pair is not None:
            return query.image_pair

        session = query.session

        if session is None:
            return None

        requires_pair = bool(
            getattr(intent, "temporal", False)
            or getattr(intent, "cross_modal", False)
        )

        if not requires_pair:
            return None

        # Prefer an already-created compatible pair.
        try:
            pairs = session.image_pairs.all()

            for pair in pairs:
                image_a = getattr(
                    pair,
                    "image_a",
                    None,
                )

                image_b = getattr(
                    pair,
                    "image_b",
                    None,
                )

                if image_a is None or image_b is None:
                    continue

                if image_a in assets and image_b in assets:
                    return pair

        except Exception as exc:
            logger.debug(
                "Unable to inspect existing image pairs: %s",
                exc,
            )

        return None

    @classmethod
    def _filter_assets_by_spatial_context(
        cls,
        assets: list[Any],
        intent: Any,
        session_context: dict[str, Any],
    ) -> list[Any]:
        """
        Remove assets that are provably outside the requested AOI.

        Unknown footprints are retained because absence of metadata is not
        evidence of non-intersection.
        """

        location = _intent_location(intent)

        target_bbox = (
            location.get("bbox")
            if isinstance(location, dict)
            else None
        )

        if not target_bbox:
            target_bbox = _extract_bbox(
                session_context.get(
                    "aoi_geometry"
                )
            )

        if not target_bbox:
            target_bbox = _extract_bbox(
                session_context.get(
                    "active_region"
                )
            )

        if not target_bbox:
            return assets

        filtered: list[Any] = []

        for asset in assets:
            image_bbox = getattr(
                asset,
                "bounds_wgs84",
                None,
            )

            if image_bbox is None:
                provenance = getattr(
                    asset,
                    "provenance",
                    None,
                )

                if isinstance(provenance, dict):
                    image_bbox = provenance.get(
                        "bbox"
                    )

            if _bbox_intersects(
                image_bbox,
                target_bbox,
            ):
                filtered.append(
                    asset
                )

        return filtered

    # ------------------------------------------------------------------
    # Mode / task mapping
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_mode(
        cls,
        intent: Any,
        assets: list[Any],
        image_pair: Any | None,
    ) -> str:
        if getattr(
            intent,
            "cross_modal",
            False,
        ):
            return "CROSS_MODAL"

        if (
            getattr(
                intent,
                "temporal",
                False,
            )
            or image_pair is not None
        ):
            return "BI_TEMPORAL"

        return "SINGLE_IMAGE"

    @classmethod
    def _resolve_database_task(
        cls,
        intent: Any,
    ) -> str:
        """
        Map internal understander intents to the Query model's task choices.

        Internal intent remains available in structured_plan.
        """

        name = _intent_name(intent).upper()

        mapping = {
            "VQA": "VQA",
            "IMAGE_DESCRIPTION": "CAPTION",
            "CAPTION": "CAPTION",
            "GROUNDING": "GROUNDING",
            "REGION_GROUNDING": "GROUNDING",

            "CHANGE_DETECTION": "CHANGE_DETECTION",
            "CHANGE_VQA": "CHANGE_VQA",

            "OPTICAL_SAR_FUSION": "OPTICAL_SAR_FUSION",

            "MISSION": "MISSION",

            "SATELLITE_SEARCH": "CAPTION",
            "LATEST_OBSERVATION": "CAPTION",

            "VEGETATION_ANALYSIS": "VQA",
            "AGRICULTURE_ANALYSIS": "VQA",

            "WATER_DETECTION": "VQA",

            "BUILDING_ANALYSIS": "VQA",
            "URBAN_ANALYSIS": "VQA",
            "OBJECT_COUNTING": "VQA",

            "SEMANTIC_RETRIEVAL": "GROUNDING",

            "THERMAL_HOTSPOT": "VQA",
            "MAP_VISUALIZATION": "VQA",

            "FOLLOW_UP_REFINEMENT": "VQA",
            "REGION_COMPARISON": "VQA",
        }

        return mapping.get(
            name,
            "VQA",
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate_request(
        cls,
        intent: Any,
        assets: list[Any],
        image_pair: Any | None,
    ) -> dict[str, Any]:
        try:
            result = validate_agent_inputs(
                intent,
                assets,
                image_pair,
            )

        except Exception as exc:
            logger.exception(
                "Agent input validation failed."
            )

            return {
                "valid": False,
                "mode": "SINGLE_IMAGE",
                "reasons": [
                    f"Input validation failed: {exc}"
                ],
            }

        if not isinstance(result, dict):
            return {
                "valid": False,
                "mode": "SINGLE_IMAGE",
                "reasons": [
                    "Input validator returned an invalid response."
                ],
            }

        result.setdefault(
            "valid",
            False,
        )

        result.setdefault(
            "mode",
            "SINGLE_IMAGE",
        )

        result.setdefault(
            "reasons",
            [],
        )

        return result

    # ------------------------------------------------------------------
    # Clarification
    # ------------------------------------------------------------------

    @classmethod
    def _clarification_response(
        cls,
        query: Query,
        intent: Any,
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = (
            getattr(
                intent,
                "clarification_prompt",
                None,
            )
            or "I need a little more information before I can perform this analysis."
        )

        options = _safe_list(
            getattr(
                intent,
                "clarification_options",
                [],
            )
        )

        query.answer = str(
            prompt
        )

        # Clarification confidence is NOT scientific confidence.
        # Keep it null because no Earth-observation evidence was evaluated.
        query.confidence = None

        query.status = "COMPLETED"
        query.completed_at = timezone.now()

        query.structured_plan = {
            "type": "CLARIFICATION",
            "intent": _intent_name(intent),
            "target": _intent_target(intent),
            "prompt": prompt,
            "options": options,
            "validation": _json_safe(
                validation
            ),
        }

        query.plan = {
            "type": "CLARIFICATION",
            "steps": [],
        }

        query.follow_up_questions = options

        query.save(
            update_fields=[
                "answer",
                "confidence",
                "status",
                "completed_at",
                "structured_plan",
                "plan",
                "follow_up_questions",
            ]
        )

        return {
            "status": "COMPLETED",
            "answer": query.answer,
            "confidence": None,
            "clarification_required": True,
            "clarification_options": options,
            "workflow": "CLARIFICATION",
        }

    # ------------------------------------------------------------------
    # Session memory
    # ------------------------------------------------------------------

    @classmethod
    def _update_memory(
        cls,
        query: Query,
        intent: Any,
        result: dict[str, Any],
        session_context: dict[str, Any],
    ) -> None:
        session = query.session

        if session is None:
            return

        context = _safe_dict(
            getattr(
                session,
                "conversation_context",
                None,
            )
        )

        history = _safe_list(
            getattr(
                session,
                "conversation_history",
                None,
            )
        )

        answer = result.get(
            "answer"
        )

        history.append(
            {
                "query_id": str(query.id),
                "query": query.text,
                "intent": _intent_name(intent),
                "target": _intent_target(intent),
                "answer": answer,
                "timestamp": timezone.now().isoformat(),
            }
        )

        context["conversation_history"] = history[-100:]
        context["last_query_id"] = str(
            query.id
        )
        context["last_question"] = query.text
        context["last_intent"] = _intent_name(
            intent
        )

        target = _intent_target(
            intent
        )

        if target:
            context["last_target"] = target

        location = _intent_location(
            intent
        )

        if location:
            context["active_aoi"] = _json_safe(
                location
            )

        # Preserve map context supplied by the frontend.
        for key in (
            "active_pin",
            "selected_location",
            "current_viewport",
            "aoi_geometry",
            "current_visual_state",
        ):
            if key in session_context:
                context[key] = _json_safe(
                    session_context[key]
                )

        # Preserve actual evidence from executor output.
        if result.get("evidence_graph"):
            context["last_evidence_graph"] = (
                _json_safe(
                    result["evidence_graph"]
                )
            )

        # Do not store synthetic summaries. Only persist an actual answer.
        if isinstance(answer, str) and answer.strip():
            context["last_answer_summary"] = (
                answer[:500]
            )

        previous_questions = _safe_list(
            context.get(
                "previous_questions"
            )
        )

        previous_questions.append(
            query.text
        )

        context["previous_questions"] = (
            previous_questions[-20:]
        )

        session.conversation_context = context
        session.conversation_history = history[-100:]

        session.save(
            update_fields=[
                "conversation_context",
                "conversation_history",
                "updated_at",
            ]
        )

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    @classmethod
    def _build_input_context(
        cls,
        query: Query,
        intent: Any,
        assets: list[Any],
        image_pair: Any | None,
        session_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "query_id": str(
                query.id
            ),
            "image_count": len(
                assets
            ),
            "has_images": bool(
                assets
            ),
            "image_ids": [
                str(asset.pk)
                for asset in assets
            ],
            "image_metadata": [
                {
                    "id": str(asset.pk),
                    "sensor": getattr(
                        asset,
                        "sensor",
                        None,
                    ),
                    "modality": getattr(
                        asset,
                        "modality",
                        None,
                    ),
                    "processing_status": getattr(
                        asset,
                        "processing_status",
                        None,
                    ),
                    "acquisition_date": _json_safe(
                        getattr(
                            asset,
                            "acquisition_date",
                            None,
                        )
                    ),
                    "bounds_wgs84": _json_safe(
                        getattr(
                            asset,
                            "bounds_wgs84",
                            None,
                        )
                    ),
                    "resolution_m": getattr(
                        asset,
                        "resolution_m",
                        None,
                    ),
                    "crs": getattr(
                        asset,
                        "crs",
                        None,
                    ),
                }
                for asset in assets
            ],
            "image_pair_id": (
                str(image_pair.pk)
                if image_pair is not None
                else None
            ),
            "aoi_geometry": (
                session_context.get(
                    "aoi_geometry"
                )
                or _intent_location(
                    intent
                ).get(
                    "geometry"
                )
            ),
            "active_pin": (
                session_context.get(
                    "active_pin"
                )
                or session_context.get(
                    "selected_location"
                )
            ),
            "current_viewport": session_context.get(
                "current_viewport"
            ),
            "session_context": session_context,
            "intent": {
                "name": _intent_name(
                    intent
                ),
                "target": _intent_target(
                    intent
                ),
                "temporal": bool(
                    getattr(
                        intent,
                        "temporal",
                        False,
                    )
                ),
                "cross_modal": bool(
                    getattr(
                        intent,
                        "cross_modal",
                        False,
                    )
                ),
                "spatial_filter": _json_safe(
                    getattr(
                        intent,
                        "spatial_filter",
                        None,
                    )
                ),
                "requested_output": _json_safe(
                    getattr(
                        intent,
                        "requested_output",
                        None,
                    )
                ),
                "time_range": _json_safe(
                    _intent_time_range(
                        intent
                    )
                ),
            },
        }

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def run(
        cls,
        query: Query,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the complete SatQuery-X orchestration flow.
        """

        # --------------------------------------------------------------
        # Initial state
        # --------------------------------------------------------------

        query.status = "RUNNING"
        query.error = None

        query.save(
            update_fields=[
                "status",
                "error",
            ]
        )

        session_ctx = cls._build_session_context(
            query,
            session_context,
        )

        # --------------------------------------------------------------
        # 1. UNDERSTAND
        # --------------------------------------------------------------

        try:
            intent = understand_query(
                query.text,
                session_ctx,
            )

        except Exception as exc:
            logger.exception(
                "Query understanding failed."
            )

            query.status = "FAILED"
            query.error = (
                f"QUERY_UNDERSTANDING_FAILED: {exc}"
            )
            query.completed_at = timezone.now()

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                ]
            )

            return {
                "status": "FAILED",
                "error": query.error,
            }

        intent_name = _intent_name(
            intent
        )

        target = _intent_target(
            intent
        )

        # --------------------------------------------------------------
        # Persist detected task/mode
        # --------------------------------------------------------------

        query.detected_task = (
            cls._resolve_database_task(
                intent
            )
        )

        preliminary_mode = cls._resolve_mode(
            intent,
            [],
            query.image_pair,
        )

        if preliminary_mode in QUERY_MODES:
            query.detected_mode = (
                preliminary_mode
            )

        # Keep rich understanding information.
        query.structured_plan = {
            "understanding": {
                "intent": intent_name,
                "target": target,
                "temporal": bool(
                    getattr(
                        intent,
                        "temporal",
                        False,
                    )
                ),
                "cross_modal": bool(
                    getattr(
                        intent,
                        "cross_modal",
                        False,
                    )
                ),
                "location": _json_safe(
                    _intent_location(
                        intent
                    )
                ),
                "time_range": _json_safe(
                    _intent_time_range(
                        intent
                    )
                ),
                "geo_intent": _json_safe(
                    getattr(
                        intent,
                        "geo_intent",
                        None,
                    )
                ),
                "requested_output": _json_safe(
                    getattr(
                        intent,
                        "requested_output",
                        None,
                    )
                ),
            }
        }

        query.save(
            update_fields=[
                "detected_task",
                "detected_mode",
                "structured_plan",
            ]
        )

        # --------------------------------------------------------------
        # 2. RESOLVE REAL INPUTS
        # --------------------------------------------------------------

        assets = cls._get_validated_assets(
            query
        )

        assets = cls._filter_assets_by_spatial_context(
            assets,
            intent,
            session_ctx,
        )

        image_pair = cls._select_pair(
            query,
            intent,
            assets,
        )

        # --------------------------------------------------------------
        # 3. VALIDATE
        # --------------------------------------------------------------

        validation = cls._validate_request(
            intent,
            assets,
            image_pair,
        )

        validation_mode = str(
            validation.get(
                "mode",
                "",
            )
        )

        # Clarification requested by understanding/validation.
        if (
            validation_mode == "CLARIFICATION"
            or getattr(
                intent,
                "clarification_required",
                False,
            )
        ):
            return cls._clarification_response(
                query,
                intent,
                validation,
            )

        # --------------------------------------------------------------
        # Validation failure
        # --------------------------------------------------------------

        if not validation.get(
            "valid",
            False,
        ):
            reasons = [
                str(reason)
                for reason in _safe_list(
                    validation.get(
                        "reasons"
                    )
                )
            ]

            error_message = (
                "; ".join(reasons)
                if reasons
                else "The requested analysis cannot be executed with the available inputs."
            )

            query.status = "FAILED"
            query.error = (
                f"INPUT_VALIDATION_FAILED: {error_message}"
            )
            query.completed_at = timezone.now()

            query.structured_plan = {
                **_safe_dict(
                    query.structured_plan
                ),
                "validation": _json_safe(
                    validation
                ),
            }

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                    "structured_plan",
                ]
            )

            return {
                "status": "FAILED",
                "error": query.error,
                "validation": _json_safe(
                    validation
                ),
            }

        # --------------------------------------------------------------
        # Resolve final execution mode
        # --------------------------------------------------------------

        final_mode = cls._resolve_mode(
            intent,
            assets,
            image_pair,
        )

        # The validator may intentionally return a specialized autonomous
        # mode. Those are planning modes rather than Query DB enum values.
        if validation_mode in QUERY_MODES:
            final_mode = validation_mode

        if final_mode in QUERY_MODES:
            query.detected_mode = final_mode

        # If a real pair was resolved, attach it to the query.
        if image_pair is not None:
            query.image_pair = image_pair

        # If one real image is being analyzed and no explicit image was
        # attached, attach the first actual asset.
        if (
            query.image is None
            and image_pair is None
            and len(assets) == 1
        ):
            query.image = assets[0]

        query.save(
            update_fields=[
                "detected_mode",
                "image",
                "image_pair",
            ]
        )

        # --------------------------------------------------------------
        # 4. BUILD PLAN
        # --------------------------------------------------------------

        input_context = cls._build_input_context(
            query,
            intent,
            assets,
            image_pair,
            session_ctx,
        )

        try:
            plan = create_execution_plan(
                intent,
                final_mode,
                input_context=input_context,
            )

        except TypeError:
            # Compatibility with the currently deployed planner signature.
            try:
                plan = create_execution_plan(
                    intent,
                    final_mode,
                )
            except Exception as exc:
                logger.exception(
                    "Planning failed."
                )

                query.status = "FAILED"
                query.error = (
                    f"PLANNING_FAILED: {exc}"
                )
                query.completed_at = timezone.now()

                query.save(
                    update_fields=[
                        "status",
                        "error",
                        "completed_at",
                    ]
                )

                return {
                    "status": "FAILED",
                    "error": query.error,
                }

        except Exception as exc:
            logger.exception(
                "Planning failed."
            )

            query.status = "FAILED"
            query.error = (
                f"PLANNING_FAILED: {exc}"
            )
            query.completed_at = timezone.now()

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                ]
            )

            return {
                "status": "FAILED",
                "error": query.error,
            }

        # --------------------------------------------------------------
        # Persist plan
        # --------------------------------------------------------------

        if isinstance(plan, dict):
            plan_data = _json_safe(
                plan
            )
        else:
            try:
                from dataclasses import asdict

                plan_data = _json_safe(
                    asdict(plan)
                )
            except Exception:
                plan_data = {
                    "steps": []
                }

        query.plan = plan_data

        query.structured_plan = {
            **_safe_dict(
                query.structured_plan
            ),
            "intent": intent_name,
            "target": target,
            "mode": final_mode,
            "validation": _json_safe(
                validation
            ),
            "input_context": _json_safe(
                input_context
            ),
            "execution_plan": plan_data,
        }

        query.save(
            update_fields=[
                "plan",
                "structured_plan",
            ]
        )

        # --------------------------------------------------------------
        # 5. EXECUTE
        # --------------------------------------------------------------

        try:
            executor = AgentExecutor()

            # The executor is responsible for actual evidence-producing
            # tools/models. The master agent does not generate observations.
            result = executor.execute_safe(
                str(query.id)
            )

        except Exception as exc:
            logger.exception(
                "Agent executor failed."
            )

            query.status = "FAILED"
            query.error = (
                f"EXECUTION_FAILED: {exc}"
            )
            query.completed_at = timezone.now()

            query.save(
                update_fields=[
                    "status",
                    "error",
                    "completed_at",
                ]
            )

            return {
                "status": "FAILED",
                "error": query.error,
            }

        # The executor returns a Query object in the current architecture.
        if isinstance(
            result,
            Query,
        ):
            query = result

            result_payload = {
                "status": query.status,
                "answer": query.answer,
                "confidence": query.confidence,
                "follow_up_questions": (
                    query.follow_up_questions
                ),
                "evidence_graph": (
                    query.evidence_graph
                ),
                "plan": query.plan,
            }

        elif isinstance(
            result,
            dict,
        ):
            result_payload = dict(
                result
            )

            # Re-read persisted query state because the executor may have
            # updated it in the database.
            query.refresh_from_db()

            result_payload.setdefault(
                "status",
                query.status,
            )

            result_payload.setdefault(
                "answer",
                query.answer,
            )

            result_payload.setdefault(
                "confidence",
                query.confidence,
            )

            result_payload.setdefault(
                "follow_up_questions",
                query.follow_up_questions,
            )

            result_payload.setdefault(
                "evidence_graph",
                query.evidence_graph,
            )

        else:
            query.refresh_from_db()

            result_payload = {
                "status": query.status,
                "answer": query.answer,
                "confidence": query.confidence,
                "follow_up_questions": (
                    query.follow_up_questions
                ),
                "evidence_graph": (
                    query.evidence_graph
                ),
            }

        # --------------------------------------------------------------
        # 6. Update memory
        # --------------------------------------------------------------

        try:
            cls._update_memory(
                query,
                intent,
                result_payload,
                session_ctx,
            )

        except Exception as exc:
            # Memory failure must not turn a successful scientific analysis
            # into a fabricated/failed result.
            logger.warning(
                "Conversation memory update failed: %s",
                exc,
            )

        # --------------------------------------------------------------
        # 7. Final response
        # --------------------------------------------------------------

        query.refresh_from_db()

        return {
            "status": query.status,
            "answer": query.answer,
            "confidence": query.confidence,
            "follow_up_questions": (
                query.follow_up_questions
            ),
            "evidence_graph": (
                query.evidence_graph
            ),
            "plan": query.plan,
            "structured_plan": (
                query.structured_plan
            ),
            "detected_task": (
                query.detected_task
            ),
            "detected_mode": (
                query.detected_mode
            ),
        }


# ---------------------------------------------------------------------------
# Functional entry point
# ---------------------------------------------------------------------------


def run_agent(
    query: Query,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Functional wrapper for code that prefers a function API.
    """

    return Agent.run(
        query,
        session_context=session_context,
    )


def run(
    query: Query,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible functional alias.
    """

    return Agent.run(
        query,
        session_context=session_context,
    )