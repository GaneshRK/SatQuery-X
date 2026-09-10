"""
SatQuery-X Master Execution Planner.

The planner converts a QueryIntent into a grounded execution plan.

Architecture
------------
USER
  ↓
QUERY UNDERSTANDING
  ↓
MASTER PLANNER
  ↓
SPECIALIZED AGENTS / TOOLS
  ├── Context / Location
  ├── Image Preprocessing
  ├── Single Image Analysis
  ├── Multi Image / Change Detection
  ├── GIS / Spatial Analysis
  ├── Satellite Catalogue Retrieval
  ├── Optical / SAR / Thermal Analysis
  ├── Evidence Fusion / Validation
  └── Answer / Report Composition
  ↓
REAL EVIDENCE
  ↓
VALIDATION
  ↓
FINAL RESPONSE

Important principles
--------------------
1. The planner routes work; it does not execute work.
2. The planner never fabricates coordinates, dates, sensors, measurements,
   confidence values, imagery, or scientific observations.
3. Map pins, viewport, AOI, uploaded imagery, and conversation context are
   first-class inputs.
4. A temporal comparison requires two actual observations or a real catalogue
   retrieval step capable of obtaining them.
5. A spectral index requires the actual required bands to be available.
6. Area measurement requires valid georeferencing.
7. SAR and thermal imagery must not be treated as ordinary optical imagery.
8. "Latest" means catalogue retrieval is required; the planner does not invent
   a date.
9. Ambiguous requests are returned as clarification requirements instead of
   being silently completed with defaults.
10. The planner exposes only a concise execution trace, never private model
    reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
import json
import re


# ============================================================================
# Planner-level capabilities
# ============================================================================


class AgentCapability:
    """Logical capabilities understood by the Master Orchestrator."""

    CONTEXT = "CONTEXT"
    QUERY_UNDERSTANDING = "QUERY_UNDERSTANDING"

    LOCATION_RESOLUTION = "LOCATION_RESOLUTION"
    GIS_ANALYSIS = "GIS_ANALYSIS"

    IMAGE_PREPROCESSING = "IMAGE_PREPROCESSING"

    IMAGE_ANALYSIS = "IMAGE_ANALYSIS"
    MULTI_IMAGE_ANALYSIS = "MULTI_IMAGE_ANALYSIS"
    CHANGE_DETECTION = "CHANGE_DETECTION"
    AREA_QUANTIFICATION = "AREA_QUANTIFICATION"
    GROUNDING = "GROUNDING"

    SATELLITE_SEARCH = "SATELLITE_SEARCH"
    SATELLITE_METADATA = "SATELLITE_METADATA"

    VEGETATION_ANALYSIS = "VEGETATION_ANALYSIS"
    WATER_ANALYSIS = "WATER_ANALYSIS"
    URBAN_ANALYSIS = "URBAN_ANALYSIS"
    THERMAL_ANALYSIS = "THERMAL_ANALYSIS"
    SAR_ANALYSIS = "SAR_ANALYSIS"

    CROSS_MODAL_ANALYSIS = "CROSS_MODAL_ANALYSIS"

    EVIDENCE_FUSION = "EVIDENCE_FUSION"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"

    WEB_KNOWLEDGE = "WEB_KNOWLEDGE"

    ANSWER_COMPOSITION = "ANSWER_COMPOSITION"
    REPORT_GENERATION = "REPORT_GENERATION"


# ============================================================================
# Plan structures
# ============================================================================


@dataclass
class PlanStep:
    """
    One planner step.

    This describes the operation required by the orchestrator. It does not
    contain model chain-of-thought.
    """

    step: int
    tool: str
    description: str

    parameters: dict[str, Any] = field(default_factory=dict)

    required_images: int = 0
    relationship: str = "NONE"

    optional: bool = False
    capability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "tool": self.tool,
            "description": self.description,
            "parameters": self.parameters,
            "required_images": self.required_images,
            "relationship": self.relationship,
            "optional": self.optional,
            "capability": self.capability,
        }


# ============================================================================
# Generic intent helpers
# ============================================================================


def _intent_name(intent: Any) -> str:
    value = getattr(intent, "intent", "") or ""
    return str(value).strip().upper()


def _target(intent: Any) -> str:
    value = getattr(intent, "target", None)

    if value is None:
        return ""

    return str(value).strip()


def _operation(intent: Any) -> str:
    value = getattr(intent, "operation", "") or ""
    return str(value).strip().lower()


def _raw_text(intent: Any) -> str:
    return str(
        getattr(intent, "raw_text", None)
        or getattr(intent, "text", None)
        or ""
    ).strip()


def _requested_outputs(intent: Any) -> list[str]:
    values = getattr(intent, "requested_output", None) or []

    if isinstance(values, str):
        return [values.strip().lower()]

    if not isinstance(values, (list, tuple, set)):
        return []

    return [
        str(value).strip().lower()
        for value in values
        if value is not None and str(value).strip()
    ]


def _missing_data(intent: Any) -> list[str]:
    values = getattr(intent, "missing_data", None) or []

    if isinstance(values, str):
        return [values.strip()]

    if not isinstance(values, (list, tuple, set)):
        return []

    return [
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    ]


def _has_clarification(intent: Any, mode: str) -> bool:
    return bool(
        str(mode or "").upper() == "CLARIFICATION"
        or _intent_name(intent) == "CLARIFICATION"
        or getattr(intent, "clarification_required", False)
    )


def _time_range(intent: Any) -> dict[str, Any]:
    value = getattr(intent, "time_range", None)

    if isinstance(value, dict):
        return dict(value)

    return {}


def _time_value(intent: Any, key: str) -> str | None:
    value = _time_range(intent).get(key)

    if value is None:
        return None

    text = str(value).strip()

    return text or None


def _location(intent: Any) -> dict[str, Any]:
    value = getattr(intent, "location", None)

    if isinstance(value, dict):
        return dict(value)

    return {}


def _location_name(intent: Any) -> str | None:
    location = _location(intent)

    for key in (
        "name",
        "display_name",
        "place",
        "location_name",
        "area_name",
    ):
        value = location.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def _contains_any(text: str, values: Iterable[str]) -> bool:
    normalized = str(text or "").lower()

    return any(
        str(value).lower() in normalized
        for value in values
    )


def _has_explicit_spatial_data(intent: Any) -> bool:
    location = _location(intent)

    spatial_filter = getattr(intent, "spatial_filter", None)

    geo_intent = getattr(intent, "geo_intent", None)

    return bool(
        location
        or (
            isinstance(spatial_filter, dict)
            and bool(spatial_filter)
        )
        or geo_intent is not None
    )


# ============================================================================
# Query classification
# ============================================================================


def _is_temporal(intent: Any, mode: str) -> bool:
    name = _intent_name(intent)

    return bool(
        getattr(intent, "temporal", False)
        or str(mode or "").upper() == "BI_TEMPORAL"
        or name
        in {
            "CHANGE_DETECTION",
            "CHANGE_VQA",
            "CHANGE_ANALYSIS",
            "TEMPORAL_COMPARISON",
            "LATEST_OBSERVATION",
        }
    )


def _is_cross_modal(intent: Any, mode: str) -> bool:
    name = _intent_name(intent)

    return bool(
        getattr(intent, "cross_modal", False)
        or str(mode or "").upper() == "CROSS_MODAL"
        or name
        in {
            "OPTICAL_SAR_COMPARISON",
            "OPTICAL_SAR_FUSION",
            "CROSS_MODAL_ANALYSIS",
        }
    )


def _is_change_query(intent: Any) -> bool:
    name = _intent_name(intent)
    operation = _operation(intent)
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "CHANGE_DETECTION",
            "CHANGE_VQA",
            "CHANGE_ANALYSIS",
            "TEMPORAL_COMPARISON",
            "BI_TEMPORAL",
        }
        or operation
        in {
            "change",
            "change_map",
            "compare",
            "comparison",
            "difference",
            "temporal_comparison",
        }
        or _contains_any(
            text,
            (
                "change",
                "changed",
                "difference",
                "before and after",
                "compare",
                "compared with",
                "over time",
                "between the two images",
                "between these images",
            ),
        )
    )


def _is_vegetation_query(intent: Any) -> bool:
    name = _intent_name(intent)
    target = _target(intent).lower()
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "VEGETATION_ANALYSIS",
            "AGRICULTURE_ANALYSIS",
            "VEGETATION",
            "CROP_ANALYSIS",
        }
        or target
        in {
            "vegetation",
            "crop",
            "crops",
            "forest",
            "forestry",
            "agriculture",
            "plantation",
        }
        or _contains_any(
            text,
            (
                "vegetation",
                "vegetative",
                "crop",
                "forest",
                "green cover",
                "plantation",
                "agriculture",
                "ndvi",
                "ndre",
            ),
        )
    )


def _is_water_query(intent: Any) -> bool:
    name = _intent_name(intent)
    target = _target(intent).lower()
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "WATER_DETECTION",
            "WATER_ANALYSIS",
            "WATER",
            "FLOOD_ANALYSIS",
        }
        or target
        in {
            "water",
            "river",
            "lake",
            "reservoir",
            "flood",
            "wetland",
        }
        or _contains_any(
            text,
            (
                "water",
                "river",
                "lake",
                "reservoir",
                "flood",
                "flooding",
                "ndwi",
                "water body",
            ),
        )
    )


def _is_urban_query(intent: Any) -> bool:
    name = _intent_name(intent)
    target = _target(intent).lower()
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "BUILDING_ANALYSIS",
            "URBAN_ANALYSIS",
            "ROAD_ANALYSIS",
            "OBJECT_COUNTING",
            "INFRASTRUCTURE_ANALYSIS",
        }
        or target
        in {
            "building",
            "buildings",
            "urban",
            "infrastructure",
            "road",
            "roads",
            "structure",
            "structures",
        }
        or _contains_any(
            text,
            (
                "building",
                "buildings",
                "urban",
                "infrastructure",
                "road",
                "roads",
                "structure",
                "structures",
                "built-up",
                "built up",
                "ndbi",
            ),
        )
    )


def _is_thermal_query(intent: Any) -> bool:
    name = _intent_name(intent)
    target = _target(intent).lower()
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "THERMAL_ANALYSIS",
            "THERMAL_HOTSPOT",
            "HOTSPOT_DETECTION",
        }
        or target
        in {
            "thermal",
            "temperature",
            "heat",
            "hotspot",
            "hotspots",
            "fire",
        }
        or _contains_any(
            text,
            (
                "thermal",
                "temperature",
                "hotspot",
                "heat",
                "surface temperature",
                "fire",
                "burn",
                "thermal anomaly",
            ),
        )
    )


def _is_sar_query(intent: Any) -> bool:
    name = _intent_name(intent)
    target = _target(intent).lower()
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "SAR_ANALYSIS",
            "RADAR_ANALYSIS",
            "OPTICAL_SAR_COMPARISON",
            "OPTICAL_SAR_FUSION",
        }
        or target
        in {
            "sar",
            "radar",
            "sentinel-1",
        }
        or _contains_any(
            text,
            (
                "sar",
                "radar",
                "sentinel-1",
                "sentinel 1",
                "vv",
                "vh",
                "backscatter",
                "radar imagery",
            ),
        )
    )


def _is_grounding_query(intent: Any) -> bool:
    name = _intent_name(intent)
    operation = _operation(intent)
    outputs = _requested_outputs(intent)
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "GROUNDING",
            "REGION_GROUNDING",
            "OBJECT_LOCALIZATION",
        }
        or operation
        in {
            "ground",
            "localize",
            "localization",
            "locate",
        }
        or any(
            output in {
                "boxes",
                "bounding_boxes",
                "bbox",
                "polygon",
                "geometry",
                "mask",
            }
            for output in outputs
        )
        or _contains_any(
            text,
            (
                "where is",
                "locate",
                "location of the",
                "show me the",
                "find the building",
                "find the road",
                "find the river",
                "highlight",
                "outline",
                "mark the",
                "identify where",
            ),
        )
    )


def _is_gis_query(intent: Any) -> bool:
    name = _intent_name(intent)
    operation = _operation(intent)
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "GIS_ANALYSIS",
            "SPATIAL_ANALYSIS",
            "SPATIAL_RELATION",
            "AREA_ANALYSIS",
            "BUFFER_ANALYSIS",
            "DISTANCE_ANALYSIS",
        }
        or operation
        in {
            "area",
            "distance",
            "buffer",
            "intersection",
            "containment",
            "spatial_relation",
            "within",
            "near",
        }
        or _contains_any(
            text,
            (
                "area",
                "square kilometers",
                "sq km",
                "hectares",
                "distance",
                "within",
                "near",
                "inside",
                "intersects",
                "buffer",
                "how far",
            ),
        )
    )


def _is_satellite_search_query(intent: Any) -> bool:
    name = _intent_name(intent)
    text = _raw_text(intent).lower()

    return bool(
        getattr(intent, "auto_search_required", False)
        or name
        in {
            "SATELLITE_SEARCH",
            "LATEST_OBSERVATION",
            "SCENE_SEARCH",
            "IMAGE_SEARCH",
            "CATALOG_SEARCH",
        }
        or _contains_any(
            text,
            (
                "latest satellite",
                "latest observation",
                "latest image",
                "recent satellite",
                "newest satellite",
                "find satellite image",
                "search satellite",
                "available imagery",
                "available observation",
                "what satellite data",
                "get satellite imagery",
                "find imagery",
                "new imagery",
            ),
        )
    )


def _is_latest_observation(intent: Any) -> bool:
    name = _intent_name(intent)
    text = _raw_text(intent).lower()

    return bool(
        name == "LATEST_OBSERVATION"
        or _contains_any(
            text,
            (
                "latest observation",
                "latest image",
                "latest satellite image",
                "most recent observation",
                "most recent image",
                "newest observation",
                "recent satellite image",
                "latest imagery",
            ),
        )
    )


def _is_web_query(intent: Any) -> bool:
    name = _intent_name(intent)
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "WEB_RESEARCH",
            "GENERAL_KNOWLEDGE",
            "EARTH_KNOWLEDGE",
            "EXTERNAL_KNOWLEDGE",
        }
        or _contains_any(
            text,
            (
                "according to",
                "what does nasa say",
                "what does esa say",
                "official report",
                "government report",
                "news about",
                "historical information",
                "general information about",
                "what is the policy",
                "what is the meaning",
            ),
        )
    )


def _is_report_request(intent: Any) -> bool:
    name = _intent_name(intent)
    outputs = _requested_outputs(intent)
    text = _raw_text(intent).lower()

    return bool(
        name
        in {
            "REPORT",
            "REPORT_GENERATION",
            "MISSION_REPORT",
        }
        or "report" in outputs
        or _contains_any(
            text,
            (
                "generate a report",
                "create a report",
                "make a report",
                "detailed report",
                "analysis report",
                "export report",
            ),
        )
    )


# ============================================================================
# Text-only detection
# ============================================================================


def _is_text_only_query(
    intent: Any,
    mode: str,
    input_context: dict[str, Any],
) -> bool:
    image_count = _safe_int(
        input_context.get("image_count"),
        default=0,
    )

    if image_count > 0:
        return False

    if str(mode or "").upper() in {
        "SINGLE_IMAGE",
        "BI_TEMPORAL",
        "CROSS_MODAL",
    }:
        return False

    if getattr(intent, "cross_modal", False):
        return False

    if getattr(intent, "temporal", False):
        return not _is_satellite_search_query(intent)

    return True


# ============================================================================
# Input relationship
# ============================================================================


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default

        result = int(value)

        return max(0, result)

    except (TypeError, ValueError):
        return default


def infer_input_relationship(
    intent: Any,
    mode: str,
    input_context: dict[str, Any] | None = None,
) -> str:
    """
    Determine the relationship among actual inputs.

    Explicit frontend/backend metadata has priority.

    No imagery is assumed merely because a mode was requested. The executor
    must still verify that the required files/assets actually exist.
    """

    context = input_context or {}

    explicit = str(
        context.get("relationship")
        or context.get("input_relationship")
        or ""
    ).strip().upper()

    valid_relationships = {
        "SINGLE_IMAGE",
        "BI_TEMPORAL",
        "CROSS_MODAL",
        "TEMPORAL_CROSS_MODAL",
        "TEXT_ONLY",
        "NONE",
    }

    if explicit in valid_relationships:
        return explicit

    image_count = _safe_int(
        context.get("image_count"),
        default=0,
    )

    normalized_mode = str(mode or "").strip().upper()

    if normalized_mode == "CROSS_MODAL":
        return "CROSS_MODAL"

    if normalized_mode == "TEMPORAL_CROSS_MODAL":
        return "TEMPORAL_CROSS_MODAL"

    if normalized_mode == "BI_TEMPORAL":
        return "BI_TEMPORAL"

    if _is_cross_modal(intent, mode):
        return "CROSS_MODAL"

    if _is_change_query(intent) and image_count >= 2:
        return "BI_TEMPORAL"

    if image_count >= 2 and getattr(intent, "temporal", False):
        return "BI_TEMPORAL"

    if image_count >= 1:
        return "SINGLE_IMAGE"

    return "TEXT_ONLY"


# ============================================================================
# Step construction
# ============================================================================


def _append_step(
    steps: list[PlanStep],
    tool: str,
    description: str,
    *,
    parameters: dict[str, Any] | None = None,
    required_images: int = 0,
    relationship: str = "NONE",
    optional: bool = False,
    capability: str | None = None,
) -> None:
    steps.append(
        PlanStep(
            step=len(steps) + 1,
            tool=tool,
            description=description,
            parameters=dict(parameters or {}),
            required_images=required_images,
            relationship=relationship,
            optional=optional,
            capability=capability,
        )
    )


def _append_context_step(
    steps: list[PlanStep],
    relationship: str,
) -> None:
    """
    Context resolution is always grounded in actual session/request state.

    It may use:
        - active map pin
        - viewport
        - active AOI
        - uploaded image metadata
        - conversation history
        - explicitly supplied location
        - explicitly supplied time constraints

    It must not create a location or time range when none exists.
    """

    _append_step(
        steps,
        AgentCapability.CONTEXT,
        (
            "Resolve the active conversation, map, upload, spatial, and "
            "temporal context from actual session state."
        ),
        parameters={
            "relationship": relationship,
            "use_active_pin": True,
            "use_current_viewport": True,
            "use_active_aoi": True,
            "use_uploaded_metadata": True,
            "use_conversation_history": True,
            "require_actual_values": True,
        },
        capability=AgentCapability.CONTEXT,
    )


def _append_location_step(
    steps: list[PlanStep],
    intent: Any,
) -> None:
    """
    Resolve a location only when the request contains a spatial target or
    context requires one.
    """

    parameters: dict[str, Any] = {}

    location = _location(intent)

    if location:
        parameters["location"] = location

    spatial_filter = getattr(intent, "spatial_filter", None)

    if isinstance(spatial_filter, dict) and spatial_filter:
        parameters["spatial_filter"] = dict(spatial_filter)

    parameters["allow_active_map_context"] = True
    parameters["allow_conversation_context"] = True
    parameters["require_actual_coordinates"] = True
    parameters["allow_unresolved_location"] = True

    _append_step(
        steps,
        "resolve_location",
        (
            "Resolve the requested place or spatial reference using actual "
            "request, map, session, or geocoder evidence."
        ),
        parameters=parameters,
        capability=AgentCapability.LOCATION_RESOLUTION,
    )


def _append_gis_step(
    steps: list[PlanStep],
    intent: Any,
) -> None:
    outputs = _requested_outputs(intent)

    _append_step(
        steps,
        "spatial_relation",
        (
            "Perform the requested GIS/spatial operation using actual "
            "geometries and spatial reference information."
        ),
        parameters={
            "target": _target(intent),
            "requested_outputs": outputs,
            "require_actual_geometry": True,
            "require_valid_crs_for_metric_measurement": True,
        },
        capability=AgentCapability.GIS_ANALYSIS,
    )


def _append_preprocessing_step(
    steps: list[PlanStep],
    relationship: str,
) -> None:
    """
    Preprocessing is modality-aware.

    Optical:
        cloud / cloud-shadow / haze / nodata checks

    SAR:
        modality-specific quality/artifact checks

    Thermal:
        thermal data quality checks

    The planner never instructs the preprocessing layer to discard valid SAR
    or thermal signal merely because it is visually noisy.
    """

    _append_step(
        steps,
        AgentCapability.IMAGE_PREPROCESSING,
        (
            "Validate and preprocess the supplied imagery using "
            "modality-appropriate quality controls before scientific analysis."
        ),
        parameters={
            "relationship": relationship,
            "optical": {
                "cloud_check": True,
                "shadow_check": True,
                "haze_check": True,
                "nodata_check": True,
            },
            "sar": {
                "quality_check": True,
                "preserve_backscatter_signal": True,
                "do_not_treat_speckle_as_generic_nodata": True,
            },
            "thermal": {
                "quality_check": True,
                "preserve_temperature_signal": True,
            },
            "require_actual_metadata": True,
            "preserve_useful_signal": True,
        },
        capability=AgentCapability.IMAGE_PREPROCESSING,
    )


def _append_satellite_search(
    steps: list[PlanStep],
    intent: Any,
    *,
    latest_only: bool = False,
) -> None:
    """
    Build a catalogue request from explicit constraints only.

    IMPORTANT:
    No default satellite, date, AOI, cloud threshold, or coordinates are
    inserted here.
    """

    parameters: dict[str, Any] = {}

    target = _target(intent)

    if target:
        parameters["target"] = target

    location = _location(intent)

    if location:
        parameters["location"] = location

    location_name = _location_name(intent)

    if location_name:
        parameters["location_name"] = location_name

    time_range = _time_range(intent)

    if time_range:
        parameters["time_range"] = time_range

    explicit_sensor = (
        getattr(intent, "sensor", None)
        or getattr(intent, "platform", None)
    )

    if explicit_sensor:
        parameters["sensor"] = str(explicit_sensor).strip()

    explicit_mission = getattr(intent, "mission", None)

    if explicit_mission:
        parameters["mission"] = str(explicit_mission).strip()

    explicit_cloud = getattr(intent, "cloud_cover", None)

    if explicit_cloud is not None:
        parameters["cloud_cover"] = explicit_cloud

    if latest_only:
        parameters["latest_only"] = True

    parameters["return_actual_catalogue_records"] = True
    parameters["do_not_fabricate_observation"] = True

    _append_step(
        steps,
        "search_satellite_imagery",
        (
            "Search the configured satellite catalogue using only the "
            "constraints actually supplied or resolved from session context."
        ),
        parameters=parameters,
        capability=AgentCapability.SATELLITE_SEARCH,
    )


def _append_metadata_step(
    steps: list[PlanStep],
    required_images: int = 1,
    relationship: str = "SINGLE_IMAGE",
) -> None:
    _append_step(
        steps,
        "geo_metadata",
        (
            "Read actual acquisition, CRS, geotransform, dimensions, "
            "resolution, nodata, and band metadata from the supplied imagery."
        ),
        required_images=required_images,
        relationship=relationship,
        capability=AgentCapability.SATELLITE_METADATA,
    )


def _append_evidence_validation(
    steps: list[PlanStep],
) -> None:
    _append_step(
        steps,
        "verify_evidence",
        (
            "Validate evidence consistency, provenance, spatial/temporal "
            "support, and uncertainty before final interpretation."
        ),
        parameters={
            "require_provenance": True,
            "preserve_uncertainty": True,
            "reject_unsupported_claims": True,
        },
        optional=True,
        capability=AgentCapability.EVIDENCE_VALIDATION,
    )


def _append_evidence_fusion(
    steps: list[PlanStep],
) -> None:
    _append_step(
        steps,
        "evidence_fusion",
        (
            "Fuse independent analysis outputs and preserve disagreements "
            "rather than collapsing conflicting evidence."
        ),
        parameters={
            "preserve_source_provenance": True,
            "preserve_conflicts": True,
            "no_unsupported_confidence": True,
        },
        capability=AgentCapability.EVIDENCE_FUSION,
    )


def _append_answer_stage(
    steps: list[PlanStep],
) -> None:
    _append_step(
        steps,
        AgentCapability.ANSWER_COMPOSITION,
        (
            "Compose the user-facing response from validated real outputs, "
            "measurements, evidence, provenance, and uncertainty."
        ),
        parameters={
            "use_measurements": True,
            "use_evidence": True,
            "use_provenance": True,
            "use_uncertainty": True,
            "no_fabrication": True,
            "no_private_reasoning": True,
        },
        capability=AgentCapability.ANSWER_COMPOSITION,
    )


def _append_report_stage(
    steps: list[PlanStep],
) -> None:
    _append_step(
        steps,
        AgentCapability.REPORT_GENERATION,
        (
            "Generate a structured report from validated evidence and "
            "analysis outputs."
        ),
        parameters={
            "source_only": True,
            "include_provenance": True,
            "include_uncertainty": True,
            "include_measurements_only_if_available": True,
        },
        capability=AgentCapability.REPORT_GENERATION,
    )


def _append_modality_router(steps: list[PlanStep], relationship: str) -> None:
    _append_step(
        steps,
        "resolve_analysis_route",
        (
            "Resolve the analysis route from actual imagery metadata, including "
            "single-image, bi-temporal, optical/SAR, and temporal optical/SAR cases."
        ),
        parameters={
            "requested_relationship": relationship,
            "require_explicit_modality_metadata": True,
            "allow_sensor_platform_metadata": True,
            "never_guess_from_input_order": True,
        },
        required_images=1,
        relationship=relationship,
        capability=AgentCapability.QUERY_UNDERSTANDING,
    )


# ============================================================================
# Specialized pipelines
# ============================================================================


def _build_change_pipeline(
    steps: list[PlanStep],
    intent: Any,
    relationship: str,
) -> None:
    """
    Build a genuine bi-temporal pipeline.

    Required order:

        preprocessing
             ↓
        metadata / alignment validation
             ↓
        change detection
             ↓
        quantitative measurement
             ↓
        semantic interpretation
             ↓
        evidence fusion
             ↓
        validation
             ↓
        answer
    """

    if relationship != "BI_TEMPORAL":
        return

    _append_metadata_step(
        steps,
        required_images=2,
        relationship="BI_TEMPORAL",
    )

    _append_modality_router(steps, relationship)

    _append_step(
        steps,
        "change_detection",
        (
            "Compare the two real observations after validating spatial "
            "alignment and temporal metadata."
        ),
        parameters={
            "target": _target(intent),
            "require_actual_pair": True,
            "require_spatial_alignment": True,
            "require_temporal_metadata": True,
            "no_synthetic_baseline": True,
        },
        required_images=2,
        relationship="BI_TEMPORAL",
        capability=AgentCapability.CHANGE_DETECTION,
    )

    _append_step(
        steps,
        "AREA_QUANTIFIER",
        (
            "Quantify detected change only when the change mask and valid "
            "georeferencing support a physical-area measurement."
        ),
        parameters={
            "require_georeferencing": True,
            "derive_pixel_area_from_actual_transform": True,
            "do_not_assume_pixel_size": True,
        },
        required_images=2,
        relationship="BI_TEMPORAL",
        capability=AgentCapability.AREA_QUANTIFICATION,
    )

    _append_step(
        steps,
        "change_vqa",
        (
            "Interpret the actual temporal differences in relation to the "
            "user's question."
        ),
        parameters={
            "target": _target(intent),
            "use_change_mask": True,
            "use_change_statistics": True,
            "use_source_metadata": True,
        },
        required_images=2,
        relationship="BI_TEMPORAL",
        capability=AgentCapability.MULTI_IMAGE_ANALYSIS,
    )


def _build_single_image_pipeline(
    steps: list[PlanStep],
    intent: Any,
    relationship: str,
) -> None:
    """Build a grounded single-image analysis pipeline."""

    if relationship != "SINGLE_IMAGE":
        return

    target = _target(intent)

    # ---------------------------------------------------------------
    # Grounding
    # ---------------------------------------------------------------

    if _is_grounding_query(intent):
        _append_step(
            steps,
            "grounding",
            "Locate the requested target in the supplied real imagery.",
            parameters={
                "text_prompt": target,
                "require_actual_image": True,
                "return_spatial_evidence": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.GROUNDING,
        )

        return

    # ---------------------------------------------------------------
    # Vegetation
    # ---------------------------------------------------------------

    if _is_vegetation_query(intent):
        _append_step(
            steps,
            "calculate_ndvi",
            (
                "Calculate NDVI only when the required red and near-infrared "
                "bands are available and correctly identified."
            ),
            parameters={
                "require_actual_band_mapping": True,
                "required_bands": ["red", "nir"],
                "reject_rgb_approximation": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.VEGETATION_ANALYSIS,
        )

        _append_step(
            steps,
            "detect_vegetation",
            (
                "Detect vegetation evidence from the processed imagery and "
                "available spectral evidence."
            ),
            parameters={
                "require_actual_raster": True,
                "preserve_nodata_mask": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.VEGETATION_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # Water
    # ---------------------------------------------------------------

    if _is_water_query(intent):
        _append_step(
            steps,
            "calculate_ndwi",
            (
                "Calculate NDWI only when the required green and near-infrared "
                "bands are available and correctly identified."
            ),
            parameters={
                "require_actual_band_mapping": True,
                "required_bands": ["green", "nir"],
                "reject_rgb_approximation": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.WATER_ANALYSIS,
        )

        _append_step(
            steps,
            "detect_water",
            (
                "Detect water evidence from the processed raster and return "
                "spatial evidence when georeferencing is available."
            ),
            parameters={
                "require_actual_raster": True,
                "preserve_nodata_mask": True,
                "return_geometry_when_georeferenced": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.WATER_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # Urban / infrastructure
    # ---------------------------------------------------------------

    if _is_urban_query(intent):
        _append_step(
            steps,
            "detect_and_count_structures",
            (
                "Detect candidate structures or infrastructure features in "
                "the supplied imagery."
            ),
            parameters={
                "target": target,
                "require_actual_image": True,
                "return_detection_evidence": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.URBAN_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # Thermal
    # ---------------------------------------------------------------

    if _is_thermal_query(intent):
        _append_step(
            steps,
            "vqa",
            (
                "Analyze the supplied thermal imagery using thermal-aware "
                "evidence and preserve thermal signal."
            ),
            parameters={
                "target": target,
                "modality": "THERMAL",
                "require_actual_thermal_data": True,
                "preserve_temperature_signal": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.THERMAL_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # SAR
    # ---------------------------------------------------------------

    if _is_sar_query(intent):
        _append_step(
            steps,
            "vqa",
            (
                "Analyze the supplied SAR/radar imagery using modality-aware "
                "evidence rather than optical assumptions."
            ),
            parameters={
                "target": target,
                "modality": "SAR",
                "require_actual_sar_data": True,
                "preserve_backscatter_signal": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.SAR_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # Semantic retrieval
    # ---------------------------------------------------------------

    name = _intent_name(intent)

    if name in {
        "SEMANTIC_RETRIEVAL",
        "REMOTECLIP_SEMANTIC_RETRIEVAL",
    }:
        if not target:
            return

        _append_step(
            steps,
            "remoteclip_semantic_retrieval",
            (
                "Compare the supplied satellite image representation against "
                "the user's semantic target."
            ),
            parameters={
                "text_queries": [target],
                "require_actual_image": True,
            },
            required_images=1,
            relationship="SINGLE_IMAGE",
            capability=AgentCapability.IMAGE_ANALYSIS,
        )

        return

    # ---------------------------------------------------------------
    # Generic visual question
    # ---------------------------------------------------------------

    _append_step(
        steps,
        "vqa",
        "Answer the visual question using evidence from the supplied imagery.",
        parameters={
            "target": target,
            "require_actual_image": True,
            "answer_from_evidence_only": True,
        },
        required_images=1,
        relationship="SINGLE_IMAGE",
        capability=AgentCapability.IMAGE_ANALYSIS,
    )


def _build_temporal_optical_sar_pipeline(steps: list[PlanStep], intent: Any, relationship: str) -> None:
    if relationship != "TEMPORAL_CROSS_MODAL":
        return
    _append_metadata_step(steps, required_images=4, relationship="TEMPORAL_CROSS_MODAL")
    _append_modality_router(steps, relationship)
    _append_step(
        steps,
        "coregister_temporal_optical_sar",
        "Pair the real observations by acquisition time and coregister each SAR scene to its paired optical grid before multimodal inference.",
        parameters={
            "max_pair_delta_hours": 72.0,
            "require_crs": True,
            "require_spatial_overlap": True,
            "preserve_temporal_order": True,
            "never_guess_modality": True,
        },
        required_images=4, relationship="TEMPORAL_CROSS_MODAL",
        capability=AgentCapability.MULTI_IMAGE_ANALYSIS,
    )
    _append_step(
        steps,
        "temporal_optical_sar",
        "Fuse Optical/SAR observations at two timestamps with separate modality and temporal streams.",
        parameters={
            "target": _target(intent),
            "require_two_optical_observations": True,
            "require_two_sar_observations": True,
            "require_explicit_modality_metadata": True,
            "require_spatial_alignment": True,
            "preserve_temporal_order": True,
        },
        required_images=4, relationship="TEMPORAL_CROSS_MODAL",
        capability=AgentCapability.MULTI_IMAGE_ANALYSIS,
    )
    _append_evidence_fusion(steps)


def _build_cross_modal_pipeline(
    steps: list[PlanStep],
    intent: Any,
    relationship: str,
) -> None:
    """Build an optical/SAR or other cross-modal analysis pipeline."""

    if relationship != "CROSS_MODAL":
        return

    _append_metadata_step(
        steps,
        required_images=2,
        relationship="CROSS_MODAL",
    )

    _append_modality_router(steps, relationship)

    _append_step(
        steps,
        "optical_sar_fusion",
        (
            "Fuse the supplied cross-modal observations after validating "
            "their metadata and spatial relationship."
        ),
        parameters={
            "target": _target(intent),
            "require_actual_modalities": True,
            "require_spatial_alignment": True,
            "preserve_modal_specific_evidence": True,
        },
        required_images=2,
        relationship="CROSS_MODAL",
        capability=AgentCapability.CROSS_MODAL_ANALYSIS,
    )

    _append_evidence_fusion(steps)


def _build_gis_pipeline(
    steps: list[PlanStep],
    intent: Any,
) -> None:
    if not _is_gis_query(intent):
        return

    _append_gis_step(
        steps,
        intent,
    )


def _build_text_pipeline(
    steps: list[PlanStep],
    intent: Any,
) -> None:
    """
    Text-only requests never trigger a fake visual analysis.

    Current/latest satellite information requires actual catalogue retrieval.
    External factual knowledge requires guarded web retrieval.
    """

    if _is_satellite_search_query(intent):
        _append_satellite_search(
            steps,
            intent,
            latest_only=_is_latest_observation(intent),
        )
        return

    if _is_web_query(intent):
        query_text = _raw_text(intent)

        parameters: dict[str, Any] = {
            "query": query_text,
            "require_source_evidence": True,
            "return_citations": True,
        }

        location_name = _location_name(intent)

        if location_name:
            parameters["location_name"] = location_name

        _append_step(
            steps,
            "search_web",
            (
                "Retrieve external evidence only when the request requires "
                "knowledge outside supplied imagery and session context."
            ),
            parameters=parameters,
            capability=AgentCapability.WEB_KNOWLEDGE,
        )

        return

    _append_step(
        steps,
        AgentCapability.QUERY_UNDERSTANDING,
        (
            "Use the resolved textual and conversational context to answer "
            "without manufacturing satellite observations."
        ),
        parameters={
            "text_only": True,
            "answer_from_available_context": True,
            "no_satellite_claims_without_data": True,
        },
        capability=AgentCapability.QUERY_UNDERSTANDING,
    )


# ============================================================================
# Plan validation
# ============================================================================


_ORCHESTRATION_TOOLS = {
    AgentCapability.CONTEXT,
    AgentCapability.QUERY_UNDERSTANDING,
    AgentCapability.ANSWER_COMPOSITION,
    AgentCapability.REPORT_GENERATION,
}


def _validate_plan(
    steps: list[PlanStep],
    relationship: str,
    image_count: int,
) -> tuple[list[PlanStep], list[str]]:
    """
    Validate planner-level input mismatches.

    A warning is preferable to silently pretending that missing imagery exists.
    """

    valid: list[PlanStep] = []
    warnings: list[str] = []

    for step in steps:
        if step.required_images > image_count:
            if step.optional:
                warnings.append(
                    f"Optional step '{step.tool}' was omitted because it "
                    f"requires {step.required_images} image(s), while "
                    f"{image_count} image(s) are available."
                )
                continue

            warnings.append(
                f"Step '{step.tool}' requires {step.required_images} image(s), "
                f"but only {image_count} image(s) are available."
            )

            # Keep the step in the plan so the orchestrator can return a
            # grounded missing-input result rather than silently changing the
            # user's requested task.
            valid.append(step)
            continue

        if (
            step.relationship not in {"NONE", relationship}
            and not step.optional
        ):
            warnings.append(
                f"Step '{step.tool}' expects relationship "
                f"'{step.relationship}', but current relationship is "
                f"'{relationship}'."
            )

        valid.append(step)

    for index, step in enumerate(valid, start=1):
        step.step = index

    return valid, warnings


def _deduplicate_steps(
    steps: list[PlanStep],
) -> list[PlanStep]:
    """Remove exact duplicate tool+parameter combinations."""

    result: list[PlanStep] = []
    seen: set[tuple[str, str]] = set()

    for step in steps:
        key = (
            step.tool,
            json_safe_key(step.parameters),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(step)

    for index, step in enumerate(result, start=1):
        step.step = index

    return result


def json_safe_key(value: Any) -> str:
    """Stable JSON representation used for planner deduplication."""

    return json.dumps(
        value,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


# ============================================================================
# Plan requirement analysis
# ============================================================================


def _derive_required_agents(
    steps: list[PlanStep],
) -> list[str]:
    result: list[str] = []

    excluded = {
        AgentCapability.CONTEXT,
        AgentCapability.QUERY_UNDERSTANDING,
        AgentCapability.IMAGE_PREPROCESSING,
        AgentCapability.ANSWER_COMPOSITION,
        AgentCapability.REPORT_GENERATION,
    }

    for step in steps:
        capability = step.capability

        if not capability:
            continue

        if capability in excluded:
            continue

        if capability not in result:
            result.append(capability)

    return result


def _has_tool(
    steps: list[PlanStep],
    *tool_names: str,
) -> bool:
    names = set(tool_names)

    return any(
        step.tool in names
        for step in steps
    )


def _map_context_available(
    context: dict[str, Any],
) -> bool:
    return bool(
        context.get("has_map_pin")
        or context.get("has_viewport")
        or context.get("has_aoi")
        or context.get("active_map_context")
        or context.get("map_context")
    )


# ============================================================================
# Clarification generation
# ============================================================================


def _build_clarification(
    intent: Any,
    relationship: str,
    missing_data: list[str],
) -> dict[str, Any]:
    prompt = getattr(
        intent,
        "clarification_prompt",
        None,
    )

    options = getattr(
        intent,
        "clarification_options",
        None,
    ) or []

    if not prompt:
        if missing_data:
            prompt = (
                "I need the following information before I can run this "
                "analysis: "
                + ", ".join(missing_data)
            )
        else:
            prompt = (
                "I need a little more information before I can run this "
                "analysis."
            )

    return {
        "required": True,
        "prompt": str(prompt),
        "options": options,
        "missing_data": missing_data,
        "relationship": relationship,
    }


# ============================================================================
# Public planner API
# ============================================================================


def create_execution_plan(
    intent: Any,
    mode: str,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create an auditable execution plan.

    Parameters
    ----------
    intent:
        QueryIntent produced by the query understander.

    mode:
        Existing query mode such as:
            SINGLE_IMAGE
            BI_TEMPORAL
            CROSS_MODAL
            CLARIFICATION

    input_context:
        Actual request/session state, for example:

        {
            "image_count": 2,
            "relationship": "BI_TEMPORAL",
            "has_map_pin": True,
            "has_viewport": True,
            "has_aoi": True,
        }

    Returns
    -------
    dict
        Structured execution plan consumed by the orchestrator/executor.
    """

    context = dict(input_context or {})

    normalized_mode = str(
        mode or "SINGLE_IMAGE"
    ).strip().upper()

    image_count = _safe_int(
        context.get("image_count"),
        default=0,
    )

    relationship = infer_input_relationship(
        intent,
        normalized_mode,
        context,
    )

    task = _intent_name(intent) or "IMAGE_ANALYSIS"
    target = _target(intent)

    missing_data = _missing_data(intent)

    # ====================================================================
    # Clarification
    # ====================================================================

    if _has_clarification(
        intent,
        normalized_mode,
    ):
        return {
            "mode": "CLARIFICATION",
            "task": "CLARIFICATION",
            "target": target,
            "relationship": relationship,
            "steps": [],
            "clarification": _build_clarification(
                intent,
                relationship,
                missing_data,
            ),
            "warnings": [],
            "required_inputs": {
                "image_count": image_count,
                "relationship": relationship,
                "map_context_available": _map_context_available(context),
            },
            "planner": {
                "version": "3.0",
                "strategy": "grounded_agentic_routing",
            },
        }

    # ====================================================================
    # Master plan
    # ====================================================================

    steps: list[PlanStep] = []

    _append_context_step(
        steps,
        relationship,
    )

    # ====================================================================
    # Location / GIS
    # ====================================================================

    if _has_explicit_spatial_data(intent):
        _append_location_step(
            steps,
            intent,
        )

    if _is_gis_query(intent):
        _build_gis_pipeline(
            steps,
            intent,
        )

    # ====================================================================
    # Satellite catalogue retrieval
    # ====================================================================

    if _is_satellite_search_query(intent):
        _append_satellite_search(
            steps,
            intent,
            latest_only=_is_latest_observation(intent),
        )

        # Agentic acquisition: when the request needs actual imagery for
        # downstream analysis, search results are not enough. Select real
        # provider assets, download them, validate them, and attach them to
        # the query before specialist models execute. Pure catalogue-search
        # requests remain metadata-only.
        if image_count == 0 and _intent_name(intent) not in {
            "SATELLITE_SEARCH", "SCENE_SEARCH", "IMAGE_SEARCH", "CATALOG_SEARCH",
        }: 
            acquisition_count = 4 if relationship == "TEMPORAL_CROSS_MODAL" else (2 if _is_change_query(intent) else 1)
            _append_step(
                steps,
                "acquire_satellite_imagery",
                (
                    "Select real catalogue observation(s), download provider assets, "
                    "validate geospatial integrity, and attach the resulting imagery "
                    "to the active query before analysis."
                ),
                parameters={
                    "required_images": acquisition_count,
                    "asset_preference": "",
                    "require_real_download": True,
                    "require_geospatial_validation": True,
                },
                capability=AgentCapability.SATELLITE_SEARCH,
            )

        # If real uploaded imagery is also available, it can be analyzed.
        if image_count > 0:
            _append_metadata_step(
                steps,
                required_images=1,
                relationship=(
                    "BI_TEMPORAL"
                    if image_count >= 2
                    else "SINGLE_IMAGE"
                ),
            )

            _append_preprocessing_step(
                steps,
                relationship,
            )

            if relationship == "TEMPORAL_CROSS_MODAL":
                _build_temporal_optical_sar_pipeline(steps, intent, relationship)

            elif relationship == "BI_TEMPORAL" and _is_change_query(intent):
                _build_change_pipeline(
                    steps,
                    intent,
                    relationship,
                )

            elif relationship == "CROSS_MODAL":
                _build_cross_modal_pipeline(
                    steps,
                    intent,
                    relationship,
                )

            elif relationship == "SINGLE_IMAGE":
                _build_single_image_pipeline(
                    steps,
                    intent,
                    relationship,
                )

    # ====================================================================
    # Cross-modal
    # ====================================================================

    elif relationship == "TEMPORAL_CROSS_MODAL":
        _append_preprocessing_step(steps, relationship)
        _build_temporal_optical_sar_pipeline(steps, intent, relationship)
        _append_evidence_validation(steps)

    elif _is_cross_modal(
        intent,
        normalized_mode,
    ):
        _append_preprocessing_step(
            steps,
            relationship,
        )

        _append_modality_router(steps, relationship)

        _build_cross_modal_pipeline(
            steps,
            intent,
            relationship,
        )

        _append_evidence_validation(
            steps,
        )

    # ====================================================================
    # Bi-temporal change
    # ====================================================================

    elif _is_change_query(intent):
        if relationship == "BI_TEMPORAL":
            _append_preprocessing_step(
                steps,
                relationship,
            )

            _build_change_pipeline(
                steps,
                intent,
                relationship,
            )

            _append_evidence_fusion(
                steps,
            )

            _append_evidence_validation(
                steps,
            )

        else:
            # A change request without two real observations cannot be
            # executed as a genuine change detector.
            #
            # If catalogue search was not already requested, the planner
            # exposes the missing dependency instead of choosing an arbitrary
            # baseline date.
            if getattr(
                intent,
                "auto_search_required",
                False,
            ):
                _append_satellite_search(
                    steps,
                    intent,
                )

            else:
                missing_data_for_change = list(
                    missing_data
                )

                if "second observation" not in {
                    item.lower()
                    for item in missing_data_for_change
                }:
                    missing_data_for_change.append(
                        "a second observation or a satellite catalogue search"
                    )

                return {
                    "mode": "CLARIFICATION",
                    "task": task,
                    "target": target,
                    "relationship": relationship,
                    "steps": [],
                    "clarification": {
                        "required": True,
                        "prompt": (
                            "A genuine change analysis needs two real "
                            "observations. Please provide a second image or "
                            "allow satellite catalogue retrieval."
                        ),
                        "options": [
                            "Upload a second image",
                            "Search the satellite catalogue",
                        ],
                        "missing_data": missing_data_for_change,
                    },
                    "warnings": [],
                    "required_inputs": {
                        "image_count": image_count,
                        "relationship": relationship,
                        "bi_temporal_pair_required": True,
                    },
                    "planner": {
                        "version": "3.0",
                        "strategy": "grounded_agentic_routing",
                    },
                }

    # ====================================================================
    # Single image
    # ====================================================================

    elif relationship == "SINGLE_IMAGE":
        _append_metadata_step(
            steps,
            required_images=1,
            relationship="SINGLE_IMAGE",
        )

        _append_preprocessing_step(
            steps,
            relationship,
        )

        _append_modality_router(steps, relationship)

        _build_single_image_pipeline(
            steps,
            intent,
            relationship,
        )

        _append_evidence_validation(
            steps,
        )

    # ====================================================================
    # Text-only
    # ====================================================================

    else:
        _build_text_pipeline(
            steps,
            intent,
        )

        if _is_web_query(intent):
            _append_evidence_validation(
                steps,
            )

    # ====================================================================
    # Evidence fusion
    # ====================================================================

    analysis_capabilities = {
        AgentCapability.IMAGE_ANALYSIS,
        AgentCapability.MULTI_IMAGE_ANALYSIS,
        AgentCapability.CHANGE_DETECTION,
        AgentCapability.AREA_QUANTIFICATION,
        AgentCapability.GROUNDING,
        AgentCapability.VEGETATION_ANALYSIS,
        AgentCapability.WATER_ANALYSIS,
        AgentCapability.URBAN_ANALYSIS,
        AgentCapability.THERMAL_ANALYSIS,
        AgentCapability.SAR_ANALYSIS,
        AgentCapability.CROSS_MODAL_ANALYSIS,
        AgentCapability.GIS_ANALYSIS,
        AgentCapability.SATELLITE_SEARCH,
        AgentCapability.WEB_KNOWLEDGE,
    }

    analysis_count = sum(
        1
        for step in steps
        if step.capability in analysis_capabilities
    )

    if analysis_count > 1 and not _has_tool(
        steps,
        "evidence_fusion",
    ):
        _append_evidence_fusion(
            steps,
        )

    # ====================================================================
    # Final answer / report
    # ====================================================================

    if _is_report_request(intent):
        _append_report_stage(
            steps,
        )

    _append_answer_stage(
        steps,
    )

    # ====================================================================
    # Validate
    # ====================================================================

    validated_steps, warnings = _validate_plan(
        steps,
        relationship,
        image_count,
    )

    validated_steps = _deduplicate_steps(
        validated_steps,
    )

    # ====================================================================
    # Requirements
    # ====================================================================

    requires_real_imagery = any(
        step.required_images > 0
        for step in validated_steps
    )

    requires_catalogue = _has_tool(
        validated_steps,
        "search_satellite_imagery",
    )

    requires_external_web = _has_tool(
        validated_steps,
        "search_web",
    )

    requires_change_pair = _has_tool(
        validated_steps,
        "change_detection",
        "change_vqa",
        "detect_change",
    )

    requires_cross_modal = _has_tool(
        validated_steps,
        "optical_sar_fusion",
    )

    requires_location = _has_tool(
        validated_steps,
        "resolve_location",
    )

    requires_gis = _has_tool(
        validated_steps,
        "spatial_relation",
    )

    requires_preprocessing = _has_tool(
        validated_steps,
        AgentCapability.IMAGE_PREPROCESSING,
    )

    # ====================================================================
    # Additional warnings for missing real inputs
    # ====================================================================

    if requires_real_imagery and image_count == 0:
        warnings.append(
            "This plan requires real imagery, but no uploaded image is "
            "currently available. Execution must not fabricate an image."
        )

    if requires_change_pair and image_count < 2:
        warnings.append(
            "This plan requires two real observations, but fewer than two "
            "images are currently available."
        )

    # ====================================================================
    # Plan result
    # ====================================================================

    return {
        "mode": normalized_mode,
        "task": task,
        "target": target,
        "relationship": relationship,

        "steps": [
            step.to_dict()
            for step in validated_steps
        ],

        "warnings": warnings,

        "required_inputs": {
            "image_count": image_count,
            "relationship": relationship,

            "real_imagery_required": requires_real_imagery,
            "bi_temporal_pair_required": requires_change_pair,
            "cross_modal_pair_required": requires_cross_modal,

            "location_resolution_required": requires_location,
            "gis_geometry_required": requires_gis,
            "preprocessing_required": requires_preprocessing,

            "map_context_available": _map_context_available(
                context
            ),
        },

        "required_agents": _derive_required_agents(
            validated_steps
        ),

        "data_sources": {
            "uploaded_imagery": image_count > 0,
            "satellite_catalogue": requires_catalogue,
            "external_web": requires_external_web,
            "conversation_context": True,
            "map_context": _map_context_available(
                context
            ),
        },

        "planner": {
            "version": "3.1",
            "strategy": "grounded_agentic_routing",

            "deterministic_measurements_before_semantic_interpretation": True,

            "context_first": True,
            "location_context_supported": True,
            "map_context_supported": True,
            "multi_image_supported": True,
            "cross_modal_supported": True,
            "runtime_modality_routing": True,
            "temporal_cross_modal_supported": True,

            "evidence_fusion_enabled": True,
            "evidence_validation_enabled": True,

            "fabrication_protection": True,
            "no_static_coordinates": True,
            "no_static_dates": True,
            "no_static_sensor_defaults": True,
            "no_synthetic_imagery": True,
        },
    }


# ============================================================================
# Compatibility aliases
# ============================================================================


def plan_query(
    intent: Any,
    mode: str,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible planner entry point."""

    return create_execution_plan(
        intent,
        mode,
        input_context=input_context,
    )


def build_plan(
    intent: Any,
    mode: str,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible planner entry point."""

    return create_execution_plan(
        intent,
        mode,
        input_context=input_context,
    )


__all__ = [
    "AgentCapability",
    "PlanStep",
    "infer_input_relationship",
    "create_execution_plan",
    "plan_query",
    "build_plan",
    "json_safe_key",
]