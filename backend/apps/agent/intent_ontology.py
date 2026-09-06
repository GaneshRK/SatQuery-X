"""
SatQuery-X Intent Ontology
==========================

Evidence-grounded semantic intent classification for SatQuery-X.

Design goals
------------
1. Separate USER INTENT from MODEL/SENSOR selection.
2. Never assume Sentinel-1, Sentinel-2, Landsat, bands, or dates.
3. Never depend on a static geocoding gazetteer.
4. Preserve map-pin / active-AOI / conversation context.
5. Support single-image, bi-temporal, cross-modal, comparative,
   measurement, visualization, search, and mission requests.
6. Route only to capabilities that can actually be represented by
   the current backend.
7. Fail conservatively when the request cannot be safely classified.
8. Support follow-up questions using conversation context.
9. Keep the ontology extensible for future specialist agents.

The ontology does NOT execute models.
It only determines:
    - what the user is asking for
    - what target they are referring to
    - what input type is likely required
    - what evidence is required
    - what execution constraints should be considered

Actual model selection belongs to the planner/router.
Actual truth comes from executed evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Intent enum
# ---------------------------------------------------------------------------


class GeoIntent(str, Enum):
    """Fine-grained user intents supported by SatQuery-X."""

    # ------------------------------------------------------------------
    # Image understanding
    # ------------------------------------------------------------------

    SINGLE_IMAGE_VQA = "SINGLE_IMAGE_VQA"
    MULTI_IMAGE_VQA = "MULTI_IMAGE_VQA"
    IMAGE_CAPTIONING = "IMAGE_CAPTIONING"
    OBJECT_GROUNDING = "OBJECT_GROUNDING"
    OBJECT_COUNTING = "OBJECT_COUNTING"

    # ------------------------------------------------------------------
    # Change / temporal analysis
    # ------------------------------------------------------------------

    BI_TEMPORAL_CHANGE = "BI_TEMPORAL_CHANGE"
    WATER_LOSS = "WATER_LOSS"
    FLOOD_INUNDATION = "FLOOD_INUNDATION"
    URBAN_EXPANSION = "URBAN_EXPANSION"
    DEFORESTATION = "DEFORESTATION"
    VEGETATION_GROWTH = "VEGETATION_GROWTH"
    DROUGHT_ANALYSIS = "DROUGHT_ANALYSIS"
    WILDFIRE_BURN = "WILDFIRE_BURN"
    AGRICULTURE_MONITORING = "AGRICULTURE_MONITORING"
    DAMAGE_ASSESSMENT = "DAMAGE_ASSESSMENT"
    REGION_CHANGE_COMPARISON = "REGION_CHANGE_COMPARISON"

    # ------------------------------------------------------------------
    # Cross-modal / analytical
    # ------------------------------------------------------------------

    SAR_FLOOD_MAPPING = "SAR_FLOOD_MAPPING"
    OPTICAL_SAR_FUSION = "OPTICAL_SAR_FUSION"
    SPECTRAL_INDEX = "SPECTRAL_INDEX"
    THERMAL_HOTSPOT = "THERMAL_HOTSPOT"

    # ------------------------------------------------------------------
    # GIS / spatial analysis
    # ------------------------------------------------------------------

    AREA_MEASUREMENT = "AREA_MEASUREMENT"
    MAP_VISUALIZATION = "MAP_VISUALIZATION"
    REGION_COMPARISON = "REGION_COMPARISON"

    # ------------------------------------------------------------------
    # Data discovery / workflow
    # ------------------------------------------------------------------

    SATELLITE_SEARCH = "SATELLITE_SEARCH"
    MISSION_WORKFLOW = "MISSION_WORKFLOW"

    # ------------------------------------------------------------------
    # Conversational intents
    # ------------------------------------------------------------------

    FOLLOW_UP_REFINEMENT = "FOLLOW_UP_REFINEMENT"
    CLARIFICATION = "CLARIFICATION"
    GENERAL_EARTH_KNOWLEDGE = "GENERAL_EARTH_KNOWLEDGE"
    UNSUPPORTED = "UNSUPPORTED"


# ---------------------------------------------------------------------------
# Input requirements
# ---------------------------------------------------------------------------


class InputMode(str, Enum):
    """Expected evidence/input configuration."""

    NONE = "none"
    SINGLE_IMAGE = "single_image"
    MULTI_IMAGE = "multi_image"
    BI_TEMPORAL = "bi_temporal"
    CROSS_MODAL_PAIR = "cross_modal_pair"
    SPATIAL_CONTEXT = "spatial_context"
    IMAGE_OR_SPATIAL_CONTEXT = "image_or_spatial_context"
    CATALOG_DATA = "catalog_data"
    CONVERSATION_CONTEXT = "conversation_context"


# ---------------------------------------------------------------------------
# Execution capability
# ---------------------------------------------------------------------------


class ExecutionCapability(str, Enum):
    """
    Backend capability required by an intent.

    These values deliberately correspond to actual/current SatQuery-X
    capabilities where possible.
    """

    RS_VQA = "RS_VQA"
    RS_CAPTION = "RS_CAPTION"
    RS_GROUNDING = "RS_GROUNDING"
    CHANGE_DETECTION = "CHANGE_DETECTION"
    CHANGE_VQA = "CHANGE_VQA"
    OPTICAL_SAR_FUSION = "OPTICAL_SAR_FUSION"

    CONTEXT_ONLY = "CONTEXT_ONLY"
    CATALOG_SEARCH = "CATALOG_SEARCH"
    GIS_ANALYSIS = "GIS_ANALYSIS"
    SPECIALIZED_AGENT = "SPECIALIZED_AGENT"
    KNOWLEDGE = "KNOWLEDGE"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Ontology metadata
# ---------------------------------------------------------------------------


@dataclass
class IntentMetadata:
    """
    Metadata describing an intent.

    This metadata is descriptive/planning information.
    It must not fabricate model outputs or scientific measurements.
    """

    intent: GeoIntent

    min_images_required: int = 0

    max_images_required: Optional[int] = None

    input_modes: List[InputMode] = field(
        default_factory=lambda: [InputMode.NONE]
    )

    capabilities: List[ExecutionCapability] = field(
        default_factory=lambda: [ExecutionCapability.NONE]
    )

    required_evidence: List[str] = field(default_factory=list)

    optional_evidence: List[str] = field(default_factory=list)

    target_types: List[str] = field(default_factory=list)

    description: str = ""

    clarification_required_when: List[str] = field(default_factory=list)

    # Compatibility fields for older planner code.
    allow_auto_catalog_fetch: bool = False
    default_bands: List[str] = field(default_factory=list)
    recommended_sensors: List[str] = field(default_factory=list)
    metrics_types: List[str] = field(default_factory=list)
    sensor_reality_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


INTENT_METADATA_REGISTRY: Dict[GeoIntent, IntentMetadata] = {

    # ================================================================
    # IMAGE UNDERSTANDING
    # ================================================================

    GeoIntent.SINGLE_IMAGE_VQA: IntentMetadata(
        intent=GeoIntent.SINGLE_IMAGE_VQA,
        min_images_required=1,
        max_images_required=1,
        input_modes=[InputMode.SINGLE_IMAGE],
        capabilities=[ExecutionCapability.RS_VQA],
        required_evidence=["image"],
        target_types=["scene", "object", "land_cover", "feature"],
        metrics_types=["model_confidence"],
        description=(
            "Answer a natural-language question about one supplied "
            "remote-sensing image."
        ),
        clarification_required_when=[
            "no image and no usable spatial acquisition context"
        ],
    ),

    GeoIntent.MULTI_IMAGE_VQA: IntentMetadata(
        intent=GeoIntent.MULTI_IMAGE_VQA,
        min_images_required=2,
        input_modes=[InputMode.MULTI_IMAGE, InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_VQA,
            ExecutionCapability.RS_VQA,
        ],
        required_evidence=["multiple_images"],
        optional_evidence=["acquisition_dates", "spatial_alignment"],
        target_types=["scene", "object", "land_cover", "change"],
        metrics_types=["model_confidence"],
        description=(
            "Answer a question requiring comparison or reasoning over "
            "multiple observations."
        ),
    ),

    GeoIntent.IMAGE_CAPTIONING: IntentMetadata(
        intent=GeoIntent.IMAGE_CAPTIONING,
        min_images_required=1,
        max_images_required=1,
        input_modes=[InputMode.SINGLE_IMAGE],
        capabilities=[ExecutionCapability.RS_CAPTION],
        required_evidence=["image"],
        target_types=["scene", "terrain", "infrastructure", "land_cover"],
        metrics_types=["model_confidence"],
        description=(
            "Generate an evidence-grounded description of a supplied "
            "remote-sensing image."
        ),
    ),

    GeoIntent.OBJECT_GROUNDING: IntentMetadata(
        intent=GeoIntent.OBJECT_GROUNDING,
        min_images_required=1,
        max_images_required=1,
        input_modes=[InputMode.SINGLE_IMAGE],
        capabilities=[ExecutionCapability.RS_GROUNDING],
        required_evidence=["image", "text_target"],
        optional_evidence=["georeferencing"],
        target_types=[
            "building",
            "road",
            "water",
            "vegetation",
            "ship",
            "aircraft",
            "structure",
            "user_defined_object",
        ],
        metrics_types=["target_count", "geometry"],
        description=(
            "Locate or spatially highlight a target described in natural "
            "language."
        ),
    ),

    GeoIntent.OBJECT_COUNTING: IntentMetadata(
        intent=GeoIntent.OBJECT_COUNTING,
        min_images_required=1,
        max_images_required=1,
        input_modes=[InputMode.SINGLE_IMAGE],
        capabilities=[ExecutionCapability.RS_GROUNDING],
        required_evidence=["image", "countable_target"],
        optional_evidence=["georeferencing"],
        target_types=[
            "building",
            "vehicle",
            "ship",
            "aircraft",
            "structure",
            "user_defined_object",
        ],
        metrics_types=["count", "geometry"],
        description=(
            "Count identifiable objects in an image when the selected "
            "grounding capability supports that target."
        ),
    ),

    # ================================================================
    # GENERAL CHANGE
    # ================================================================

    GeoIntent.BI_TEMPORAL_CHANGE: IntentMetadata(
        intent=GeoIntent.BI_TEMPORAL_CHANGE,
        min_images_required=2,
        max_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "two_images",
            "spatial_alignment",
            "temporal_information",
        ],
        optional_evidence=["change_mask", "change_geometry"],
        target_types=[
            "surface",
            "land_cover",
            "infrastructure",
            "vegetation",
            "water",
            "urban",
        ],
        metrics_types=[
            "changed_area",
            "change_fraction",
            "change_geometry",
        ],
        description=(
            "Detect and explain differences between two observations of "
            "the same or comparable area."
        ),
        clarification_required_when=[
            "fewer than two comparable observations"
        ],
    ),

    GeoIntent.REGION_CHANGE_COMPARISON: IntentMetadata(
        intent=GeoIntent.REGION_CHANGE_COMPARISON,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL, InputMode.MULTI_IMAGE],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "multiple_observations",
            "spatial_context",
        ],
        optional_evidence=["change_geometry", "measurements"],
        target_types=["region", "surface", "land_cover"],
        metrics_types=[
            "changed_area",
            "change_fraction",
            "regional_difference",
        ],
        description=(
            "Analyze change within a spatial region using multiple "
            "observations."
        ),
    ),

    # ================================================================
    # WATER / FLOOD
    # ================================================================

    GeoIntent.WATER_LOSS: IntentMetadata(
        intent=GeoIntent.WATER_LOSS,
        min_images_required=2,
        max_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "two_images",
            "spatial_alignment",
            "temporal_information",
        ],
        optional_evidence=[
            "water_change_mask",
            "water_geometry",
            "area_measurement",
        ],
        target_types=["lake", "reservoir", "river", "water_body"],
        metrics_types=[
            "water_area_change",
            "water_change_fraction",
        ],
        description=(
            "Analyze observed reduction or change in water extent between "
            "comparable observations."
        ),
    ),

    GeoIntent.FLOOD_INUNDATION: IntentMetadata(
        intent=GeoIntent.FLOOD_INUNDATION,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "reference_observation",
            "event_observation",
            "spatial_alignment",
        ],
        optional_evidence=[
            "inundation_mask",
            "inundation_geometry",
            "area_measurement",
        ],
        target_types=[
            "flood",
            "inundation",
            "water",
            "settlement",
            "infrastructure",
        ],
        metrics_types=[
            "inundated_area",
            "water_extent_change",
        ],
        description=(
            "Identify and explain flood or inundation-related spatial "
            "differences between observations."
        ),
    ),

    GeoIntent.SAR_FLOOD_MAPPING: IntentMetadata(
        intent=GeoIntent.SAR_FLOOD_MAPPING,
        min_images_required=1,
        input_modes=[
            InputMode.SINGLE_IMAGE,
            InputMode.BI_TEMPORAL,
        ],
        capabilities=[
            ExecutionCapability.SPECIALIZED_AGENT,
            ExecutionCapability.CHANGE_DETECTION,
        ],
        required_evidence=["SAR_observation"],
        optional_evidence=[
            "reference_observation",
            "inundation_geometry",
            "backscatter_measurements",
        ],
        target_types=["flood", "inundation", "water"],
        metrics_types=[
            "inundated_area",
            "change_geometry",
        ],
        description=(
            "Analyze flooding using SAR observations when SAR data and "
            "a compatible processing capability are actually available."
        ),
        clarification_required_when=[
            "requested SAR analysis but no SAR observation is available"
        ],
    ),

    # ================================================================
    # URBAN
    # ================================================================

    GeoIntent.URBAN_EXPANSION: IntentMetadata(
        intent=GeoIntent.URBAN_EXPANSION,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "two_images",
            "spatial_alignment",
            "temporal_information",
        ],
        optional_evidence=[
            "built_up_change_geometry",
            "area_measurement",
        ],
        target_types=[
            "urban",
            "building",
            "settlement",
            "construction",
            "road",
        ],
        metrics_types=[
            "changed_area",
            "built_up_change",
        ],
        description=(
            "Analyze observed urban or built-up expansion between "
            "comparable observations."
        ),
    ),

    GeoIntent.URBAN_ANALYSIS if hasattr(GeoIntent, "URBAN_ANALYSIS") else GeoIntent.URBAN_EXPANSION: IntentMetadata(
        intent=GeoIntent.URBAN_EXPANSION,
        min_images_required=1,
        input_modes=[
            InputMode.SINGLE_IMAGE,
            InputMode.BI_TEMPORAL,
        ],
        capabilities=[
            ExecutionCapability.RS_VQA,
            ExecutionCapability.RS_GROUNDING,
            ExecutionCapability.CHANGE_DETECTION,
        ],
        required_evidence=["image"],
        optional_evidence=["second_image", "geometry"],
        target_types=[
            "urban",
            "building",
            "settlement",
            "road",
            "construction",
        ],
        metrics_types=[
            "object_count",
            "geometry",
            "changed_area",
        ],
        description=(
            "Analyze urban structures, settlements, roads, or built-up "
            "features in supplied imagery."
        ),
    ),

    # ================================================================
    # VEGETATION / FOREST
    # ================================================================

    GeoIntent.DEFORESTATION: IntentMetadata(
        intent=GeoIntent.DEFORESTATION,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "two_images",
            "spatial_alignment",
            "temporal_information",
        ],
        optional_evidence=[
            "vegetation_change_geometry",
            "area_measurement",
        ],
        target_types=[
            "forest",
            "tree_cover",
            "vegetation",
        ],
        metrics_types=[
            "changed_area",
            "vegetation_change_fraction",
        ],
        description=(
            "Analyze observed loss of forest or vegetation cover between "
            "comparable observations."
        ),
    ),

    GeoIntent.VEGETATION_GROWTH: IntentMetadata(
        intent=GeoIntent.VEGETATION_GROWTH,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "two_images",
            "spatial_alignment",
            "temporal_information",
        ],
        optional_evidence=[
            "vegetation_change_geometry",
            "area_measurement",
        ],
        target_types=[
            "vegetation",
            "forest",
            "crop",
            "canopy",
        ],
        metrics_types=[
            "changed_area",
            "vegetation_change_fraction",
        ],
        description=(
            "Analyze observed vegetation or canopy increase between "
            "comparable observations."
        ),
    ),

    GeoIntent.AGRICULTURE_MONITORING: IntentMetadata(
        intent=GeoIntent.AGRICULTURE_MONITORING,
        min_images_required=1,
        input_modes=[
            InputMode.SINGLE_IMAGE,
            InputMode.BI_TEMPORAL,
        ],
        capabilities=[
            ExecutionCapability.RS_VQA,
            ExecutionCapability.RS_GROUNDING,
            ExecutionCapability.CHANGE_DETECTION,
        ],
        required_evidence=["image"],
        optional_evidence=[
            "second_image",
            "field_geometry",
            "spectral_measurements",
        ],
        target_types=[
            "crop",
            "field",
            "farmland",
            "vegetation",
        ],
        metrics_types=[
            "object_count",
            "area",
            "change",
        ],
        description=(
            "Analyze agricultural or crop-related visual patterns using "
            "available imagery and evidence."
        ),
    ),

    GeoIntent.DROUGHT_ANALYSIS: IntentMetadata(
        intent=GeoIntent.DROUGHT_ANALYSIS,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "multiple_observations",
            "temporal_information",
        ],
        optional_evidence=[
            "vegetation_measurements",
            "moisture_measurements",
        ],
        target_types=[
            "vegetation",
            "agriculture",
            "soil",
            "water",
        ],
        metrics_types=[
            "observed_change",
        ],
        description=(
            "Analyze evidence of vegetation, moisture, or agricultural "
            "change associated with dry conditions."
        ),
        clarification_required_when=[
            "required environmental measurements are unavailable"
        ],
    ),

    # ================================================================
    # FIRE / DAMAGE
    # ================================================================

    GeoIntent.WILDFIRE_BURN: IntentMetadata(
        intent=GeoIntent.WILDFIRE_BURN,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "pre_event_observation",
            "post_event_observation",
            "spatial_alignment",
        ],
        optional_evidence=[
            "burn_geometry",
            "spectral_measurements",
        ],
        target_types=[
            "burn_scar",
            "fire",
            "vegetation",
        ],
        metrics_types=[
            "changed_area",
            "burned_area",
        ],
        description=(
            "Analyze observed burn-related changes between pre-event and "
            "post-event imagery."
        ),
    ),

    GeoIntent.DAMAGE_ASSESSMENT: IntentMetadata(
        intent=GeoIntent.DAMAGE_ASSESSMENT,
        min_images_required=2,
        input_modes=[InputMode.BI_TEMPORAL],
        capabilities=[
            ExecutionCapability.CHANGE_DETECTION,
            ExecutionCapability.CHANGE_VQA,
        ],
        required_evidence=[
            "pre_event_observation",
            "post_event_observation",
            "spatial_alignment",
        ],
        optional_evidence=[
            "damage_geometry",
            "grounding_results",
        ],
        target_types=[
            "building",
            "road",
            "bridge",
            "infrastructure",
            "structure",
        ],
        metrics_types=[
            "changed_area",
            "affected_objects",
        ],
        description=(
            "Analyze visible structural or infrastructure differences "
            "between pre-event and post-event observations."
        ),
        clarification_required_when=[
            "no comparable pre/post observations"
        ],
    ),

    # ================================================================
    # SPECTRAL / CROSS-MODAL
    # ================================================================

    GeoIntent.SPECTRAL_INDEX: IntentMetadata(
        intent=GeoIntent.SPECTRAL_INDEX,
        min_images_required=1,
        input_modes=[InputMode.SINGLE_IMAGE],
        capabilities=[ExecutionCapability.SPECIALIZED_AGENT],
        required_evidence=[
            "appropriate_spectral_bands",
        ],
        optional_evidence=[
            "mask",
            "georeferencing",
        ],
        target_types=[
            "vegetation",
            "water",
            "built_up",
            "soil",
        ],
        metrics_types=[
            "index_value",
            "index_statistics",
            "index_geometry",
        ],
        description=(
            "Compute a requested spectral index only when the supplied "
            "imagery contains the required bands and valid metadata."
        ),
        clarification_required_when=[
            "required bands are unavailable",
            "input is not multispectral when multispectral data is required",
        ],
    ),

    GeoIntent.OPTICAL_SAR_FUSION: IntentMetadata(
        intent=GeoIntent.OPTICAL_SAR_FUSION,
        min_images_required=2,
        input_modes=[InputMode.CROSS_MODAL_PAIR],
        capabilities=[ExecutionCapability.OPTICAL_SAR_FUSION],
        required_evidence=[
            "optical_observation",
            "SAR_observation",
        ],
        optional_evidence=[
            "spatial_alignment",
            "fusion_output",
        ],
        target_types=[
            "water",
            "urban",
            "vegetation",
            "surface",
            "change",
        ],
        metrics_types=[
            "fusion_output",
            "alignment_quality",
        ],
        description=(
            "Analyze complementary optical and SAR observations using "
            "the registered optical-SAR fusion capability."
        ),
        clarification_required_when=[
            "both optical and SAR observations are unavailable"
        ],
    ),

    GeoIntent.THERMAL_HOTSPOT: IntentMetadata(
        intent=GeoIntent.THERMAL_HOTSPOT,
        min_images_required=1,
        input_modes=[
            InputMode.SINGLE_IMAGE,
            InputMode.MULTI_IMAGE,
        ],
        capabilities=[ExecutionCapability.SPECIALIZED_AGENT],
        required_evidence=[
            "thermal_observation",
        ],
        optional_evidence=[
            "temperature_measurements",
            "hotspot_geometry",
        ],
        target_types=[
            "thermal_hotspot",
            "surface_temperature",
        ],
        metrics_types=[
            "temperature",
            "hotspot_count",
            "hotspot_geometry",
        ],
        description=(
            "Analyze thermal observations when the supplied data actually "
            "contains thermal measurements."
        ),
        clarification_required_when=[
            "thermal data is unavailable"
        ],
        sensor_reality_note=(
            "The ontology does not assume that an optical image contains "
            "thermal measurements. A true thermal analysis requires an "
            "input product containing thermal information."
        ),
    ),

    # ================================================================
    # GIS
    # ================================================================

    GeoIntent.AREA_MEASUREMENT: IntentMetadata(
        intent=GeoIntent.AREA_MEASUREMENT,
        min_images_required=0,
        input_modes=[
            InputMode.SPATIAL_CONTEXT,
            InputMode.IMAGE_OR_SPATIAL_CONTEXT,
        ],
        capabilities=[ExecutionCapability.GIS_ANALYSIS],
        required_evidence=[
            "valid_geometry",
        ],
        optional_evidence=[
            "source_crs",
            "analysis_crs",
            "pixel_resolution",
            "mask",
        ],
        target_types=[
            "AOI",
            "polygon",
            "change_region",
            "water_region",
            "vegetation_region",
            "urban_region",
        ],
        metrics_types=[
            "area",
            "geometry",
        ],
        description=(
            "Measure the area of a supplied or evidence-derived geometry. "
            "Area must be calculated from real geometry/georeferencing."
        ),
        clarification_required_when=[
            "no valid geometry is available"
        ],
    ),

    GeoIntent.MAP_VISUALIZATION: IntentMetadata(
        intent=GeoIntent.MAP_VISUALIZATION,
        min_images_required=0,
        input_modes=[
            InputMode.SPATIAL_CONTEXT,
            InputMode.IMAGE_OR_SPATIAL_CONTEXT,
        ],
        capabilities=[ExecutionCapability.GIS_ANALYSIS],
        required_evidence=[
            "renderable_geometry_or_image",
        ],
        optional_evidence=[
            "map_pin",
            "AOI",
            "change_geometry",
        ],
        target_types=[
            "AOI",
            "geometry",
            "change_region",
            "image",
        ],
        metrics_types=[
            "geometry",
            "feature_count",
        ],
        description=(
            "Render available imagery or evidence-derived spatial "
            "features on the interactive map."
        ),
    ),

    GeoIntent.REGION_COMPARISON: IntentMetadata(
        intent=GeoIntent.REGION_COMPARISON,
        min_images_required=0,
        input_modes=[
            InputMode.SPATIAL_CONTEXT,
            InputMode.IMAGE_OR_SPATIAL_CONTEXT,
            InputMode.MULTI_IMAGE,
        ],
        capabilities=[
            ExecutionCapability.GIS_ANALYSIS,
            ExecutionCapability.CHANGE_DETECTION,
        ],
        required_evidence=[
            "region_a",
            "region_b",
        ],
        optional_evidence=[
            "matching_observations",
            "measurements",
        ],
        target_types=[
            "region",
            "AOI",
            "city",
            "landscape",
        ],
        metrics_types=[
            "region_a_metrics",
            "region_b_metrics",
            "difference",
        ],
        description=(
            "Compare two explicitly identified spatial regions or "
            "evidence-backed areas."
        ),
        clarification_required_when=[
            "fewer than two identifiable regions"
        ],
    ),

    # ================================================================
    # SATELLITE / DATA SEARCH
    # ================================================================

    GeoIntent.SATELLITE_SEARCH: IntentMetadata(
        intent=GeoIntent.SATELLITE_SEARCH,
        min_images_required=0,
        input_modes=[InputMode.CATALOG_DATA, InputMode.SPATIAL_CONTEXT],
        capabilities=[ExecutionCapability.CATALOG_SEARCH],
        required_evidence=[],
        optional_evidence=[
            "location",
            "time_range",
            "sensor",
            "cloud_constraints",
        ],
        target_types=[
            "satellite_scene",
            "observation",
            "imagery",
        ],
        metrics_types=[
            "scene_count",
        ],
        description=(
            "Search an available imagery/catalog service for observations "
            "matching the user's spatial, temporal, or sensor constraints."
        ),
        clarification_required_when=[
            "no spatial or temporal search constraint is available"
        ],
    ),

    # ================================================================
    # MISSION
    # ================================================================

    GeoIntent.MISSION_WORKFLOW: IntentMetadata(
        intent=GeoIntent.MISSION_WORKFLOW,
        min_images_required=0,
        input_modes=[
            InputMode.SINGLE_IMAGE,
            InputMode.BI_TEMPORAL,
            InputMode.CROSS_MODAL_PAIR,
            InputMode.SPATIAL_CONTEXT,
            InputMode.CATALOG_DATA,
        ],
        capabilities=[ExecutionCapability.SPECIALIZED_AGENT],
        required_evidence=[
            "mission_objective",
        ],
        optional_evidence=[
            "imagery",
            "spatial_context",
            "temporal_context",
            "catalog_results",
        ],
        target_types=[
            "environment",
            "urban",
            "agriculture",
            "disaster",
            "water",
            "infrastructure",
        ],
        metrics_types=[
            "completed_steps",
            "evidence_count",
        ],
        description=(
            "Execute a multi-step geospatial intelligence workflow where "
            "the user requests a broader analytical objective."
        ),
    ),

    # ================================================================
    # CONVERSATIONAL
    # ================================================================

    GeoIntent.FOLLOW_UP_REFINEMENT: IntentMetadata(
        intent=GeoIntent.FOLLOW_UP_REFINEMENT,
        min_images_required=0,
        input_modes=[InputMode.CONVERSATION_CONTEXT],
        capabilities=[ExecutionCapability.CONTEXT_ONLY],
        required_evidence=[
            "previous_query_context",
        ],
        optional_evidence=[
            "previous_results",
            "previous_geometry",
            "previous_measurements",
        ],
        target_types=[
            "previous_result",
            "previous_target",
        ],
        metrics_types=[],
        description=(
            "Refine, filter, quantify, locate, or reinterpret an earlier "
            "result using the existing conversation context."
        ),
    ),

    GeoIntent.CLARIFICATION: IntentMetadata(
        intent=GeoIntent.CLARIFICATION,
        min_images_required=0,
        input_modes=[InputMode.CONVERSATION_CONTEXT],
        capabilities=[ExecutionCapability.CONTEXT_ONLY],
        required_evidence=[],
        target_types=[],
        metrics_types=[],
        description=(
            "The request cannot safely be executed without additional "
            "spatial, temporal, image, or target information."
        ),
    ),

    GeoIntent.GENERAL_EARTH_KNOWLEDGE: IntentMetadata(
        intent=GeoIntent.GENERAL_EARTH_KNOWLEDGE,
        min_images_required=0,
        input_modes=[InputMode.NONE],
        capabilities=[ExecutionCapability.KNOWLEDGE],
        required_evidence=[],
        target_types=["earth", "geography", "remote_sensing"],
        metrics_types=[],
        description=(
            "General geographic or remote-sensing knowledge that does not "
            "require analysis of a user-specific image."
        ),
    ),

    GeoIntent.UNSUPPORTED: IntentMetadata(
        intent=GeoIntent.UNSUPPORTED,
        min_images_required=0,
        input_modes=[InputMode.NONE],
        capabilities=[ExecutionCapability.NONE],
        required_evidence=[],
        target_types=[],
        metrics_types=[],
        description=(
            "The request cannot currently be mapped safely to a supported "
            "SatQuery-X capability."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Keyword definitions
# ---------------------------------------------------------------------------

# These are semantic hints only.
# They do NOT mean that a capability is automatically available.

_CHANGE_TERMS = (
    "change",
    "changed",
    "changes",
    "difference",
    "differences",
    "before and after",
    "before vs after",
    "compare these images",
    "compare the images",
    "what happened",
    "what has changed",
    "what changed",
    "what is changing",
    "between these two",
    "between the two",
)

_WATER_TERMS = (
    "water",
    "lake",
    "reservoir",
    "river",
    "pond",
    "waterbody",
    "water body",
    "water spread",
    "water extent",
)

_FLOOD_TERMS = (
    "flood",
    "flooding",
    "flooded",
    "inundation",
    "inundated",
    "submerged",
    "waterlogging",
)

_URBAN_TERMS = (
    "urban",
    "city",
    "town",
    "built-up",
    "built up",
    "construction",
    "settlement",
    "buildings",
    "building",
    "road expansion",
    "urban sprawl",
)

_VEGETATION_TERMS = (
    "vegetation",
    "forest",
    "forests",
    "tree cover",
    "canopy",
    "green cover",
    "greening",
    "crop",
    "crops",
    "agriculture",
    "farmland",
    "forest loss",
    "deforestation",
)

_FIRE_TERMS = (
    "wildfire",
    "forest fire",
    "fire",
    "burn scar",
    "burned area",
    "burnt area",
)

_DAMAGE_TERMS = (
    "damage",
    "damaged",
    "destroyed",
    "destruction",
    "post disaster",
    "post-disaster",
    "disaster damage",
)

_SAR_TERMS = (
    "sar",
    "radar",
    "sentinel-1",
)

_OPTICAL_TERMS = (
    "optical",
    "multispectral",
    "multi spectral",
    "rgb",
)

_THERMAL_TERMS = (
    "thermal",
    "temperature",
    "surface temperature",
    "hotspot",
    "hotspots",
    "heat map",
    "heatmap",
)

_INDEX_TERMS = (
    "ndvi",
    "ndwi",
    "ndbi",
    "mndwi",
    "savi",
    "spectral index",
    "spectral indices",
    "index value",
)

_COUNT_TERMS = (
    "how many",
    "count",
    "counting",
    "number of",
    "total number",
)

_GROUNDING_TERMS = (
    "highlight",
    "outline",
    "locate",
    "locate the",
    "where are",
    "where is",
    "mark",
    "show me where",
    "delineate",
    "boundary",
    "boundaries",
    "polygon",
    "polygons",
)

_MAP_TERMS = (
    "show on map",
    "show in map",
    "map",
    "visualize",
    "visualise",
    "display",
    "render",
    "highlight on map",
)

_AREA_TERMS = (
    "area",
    "how large",
    "how big",
    "size of",
    "hectares",
    "hectare",
    "square kilometer",
    "square kilometers",
    "sq km",
    "km2",
    "km²",
)

_SEARCH_TERMS = (
    "search satellite",
    "search imagery",
    "search image",
    "find satellite",
    "find imagery",
    "find scenes",
    "find observations",
    "available imagery",
    "available scenes",
    "satellite scenes",
    "satellite imagery",
    "download imagery",
)

_MISSION_TERMS = (
    "analyze everything",
    "complete analysis",
    "full analysis",
    "full assessment",
    "comprehensive analysis",
    "run a mission",
    "mission",
    "intelligence assessment",
    "investigate this area",
    "investigate the area",
)

_GENERAL_KNOWLEDGE_TERMS = (
    "what is",
    "what are",
    "who",
    "largest mountain",
    "highest mountain",
    "deepest ocean",
    "longest river",
    "remote sensing",
    "satellite sensor",
    "how does sar work",
    "how does satellite imaging work",
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    """Return True if any semantic term appears in text."""

    q = text.lower()

    for term in terms:
        if term in q:
            return True

    return False


def _normalize_text(text: str) -> str:
    """Normalize whitespace without altering meaning."""

    return re.sub(r"\s+", " ", (text or "").strip())


def _safe_mapping(value: Any) -> Dict[str, Any]:
    """Convert mapping-like values to a dictionary."""

    if isinstance(value, dict):
        return dict(value)

    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    return {}


def _context_value(
    context_engine: Any,
    method_name: str,
    default: Any = None,
) -> Any:
    """
    Safely retrieve information from ContextEngine.

    The ontology must remain usable even when ContextEngine evolves.
    """

    if context_engine is None:
        return default

    method = getattr(context_engine, method_name, None)

    if not callable(method):
        return default

    try:
        return method()
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------


def _extract_coordinate_mentions(text: str) -> List[Dict[str, Any]]:
    """
    Extract explicit coordinates supplied by the user.

    Important:
        Coordinates are accepted only because the user explicitly supplied
        them. This function does not fabricate an extent around a point.
    """

    results: List[Dict[str, Any]] = []

    # Decimal coordinate pair.
    pattern = re.compile(
        r"(?<![\d.])"
        r"(-?\d{1,3}(?:\.\d+)?)"
        r"\s*[, ]\s*"
        r"(-?\d{1,3}(?:\.\d+)?)"
        r"(?![\d.])"
    )

    for match in pattern.finditer(text):
        try:
            first = float(match.group(1))
            second = float(match.group(2))
        except ValueError:
            continue

        # Geographic coordinate ranges.
        if not (-90 <= first <= 90 and -180 <= second <= 180):
            continue

        results.append(
            {
                "type": "point",
                "coordinates": [first, second],
                "source": "user_explicit_coordinates",
                "is_valid": True,
            }
        )

    return results


def _extract_explicit_bbox(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract an explicitly supplied bounding box.

    Supported:
        bbox=min_lon,min_lat,max_lon,max_lat
    """

    pattern = re.search(
        r"(?:bbox|bounding\s*box)\s*[:=]?\s*"
        r"(-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )

    if not pattern:
        return None

    try:
        min_lon = float(pattern.group(1))
        min_lat = float(pattern.group(2))
        max_lon = float(pattern.group(3))
        max_lat = float(pattern.group(4))
    except ValueError:
        return None

    if not (
        -180 <= min_lon <= 180
        and -180 <= max_lon <= 180
        and -90 <= min_lat <= 90
        and -90 <= max_lat <= 90
    ):
        return None

    if min_lon > max_lon or min_lat > max_lat:
        return None

    return {
        "type": "bbox",
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "source": "user_explicit_bbox",
        "is_valid": True,
    }


# ---------------------------------------------------------------------------
# Target extraction
# ---------------------------------------------------------------------------


def extract_target(text: str) -> str:
    """
    Extract the main analytical target.

    This is intentionally conservative. The target is a semantic label,
    not a claim that the target actually exists in the image.
    """

    q = text.lower()

    if _contains_any(q, _FLOOD_TERMS):
        return "flood_inundation"

    if _contains_any(q, ("water loss", "water depletion", "drying", "shrink")):
        return "water_loss"

    if _contains_any(q, _WATER_TERMS):
        return "water"

    if _contains_any(
        q,
        (
            "deforestation",
            "forest loss",
            "tree loss",
            "canopy loss",
            "logging",
        ),
    ):
        return "vegetation_loss"

    if _contains_any(
        q,
        (
            "vegetation growth",
            "greening",
            "reforestation",
            "canopy gain",
            "crop growth",
        ),
    ):
        return "vegetation_growth"

    if _contains_any(q, _VEGETATION_TERMS):
        return "vegetation"

    if _contains_any(q, _URBAN_TERMS):
        return "urban"

    if _contains_any(q, _FIRE_TERMS):
        return "burn_scar"

    if _contains_any(q, _DAMAGE_TERMS):
        return "damage"

    if _contains_any(q, _THERMAL_TERMS):
        return "thermal_hotspot"

    if _contains_any(q, _SAR_TERMS):
        return "SAR"

    return "surface"


# ---------------------------------------------------------------------------
# Multiple-location extraction
# ---------------------------------------------------------------------------


def extract_multiple_locations(
    query: str,
    context_engine: Any = None,
) -> List[Dict[str, Any]]:
    """
    Extract explicit comparison regions without using a static gazetteer.

    Important:
        This function does NOT decide that an arbitrary word is a real
        geographic location. Actual location resolution belongs to the
        location resolver / spatial context layer.
    """

    text = _normalize_text(query)

    results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------
    # Explicit coordinate locations.
    # ---------------------------------------------------------------

    coordinates = _extract_coordinate_mentions(text)

    for item in coordinates:
        results.append(item)

    # ---------------------------------------------------------------
    # Explicit comparison phrases.
    # ---------------------------------------------------------------

    comparison_match = re.search(
        r"\b(?:compare|difference\s+between|versus|vs\.?)\b"
        r"\s+(.+?)"
        r"\s+\b(?:and|with|to|vs\.?)\b"
        r"\s+(.+?)(?:[?.!]|$)",
        text,
        re.IGNORECASE,
    )

    if comparison_match:
        first = comparison_match.group(1).strip(" ,")
        second = comparison_match.group(2).strip(" ,")

        if first and second:
            results.extend(
                [
                    {
                        "name": first,
                        "source": "explicit_comparison_candidate",
                        "is_resolved": False,
                    },
                    {
                        "name": second,
                        "source": "explicit_comparison_candidate",
                        "is_resolved": False,
                    },
                ]
            )

    # ---------------------------------------------------------------
    # Context-backed comparison regions.
    # ---------------------------------------------------------------

    previous_context = _context_value(
        context_engine,
        "get_comparison_locations",
        None,
    )

    if isinstance(previous_context, list):
        for location in previous_context:
            if isinstance(location, dict):
                results.append(dict(location))

    # De-duplicate obvious duplicates.
    deduplicated: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for item in results:
        key = repr(sorted(item.items()))

        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(item)

    return deduplicated


# ---------------------------------------------------------------------------
# Follow-up detection
# ---------------------------------------------------------------------------


def _detect_follow_up_action(
    query: str,
    context_engine: Any,
) -> Optional[str]:
    """Identify the requested operation on a previous result."""

    q = query.lower().strip()

    if context_engine is None:
        return None

    is_follow_up = _context_value(
        context_engine,
        "is_follow_up_query",
        False,
    )

    if not is_follow_up:
        return None

    if re.search(
        r"^(only|just)\s+(show\s+)?"
        r"(vegetation|water|urban|buildings?|forest|roads?|damage)",
        q,
    ):
        return "filter_target"

    if re.search(
        r"^(how much|what is the total area|what's the total area|"
        r"how many|give me the area)",
        q,
    ):
        return "quantify"

    if re.search(
        r"^(where|which part|show the polygons|show the map|"
        r"show me where|highlight)",
        q,
    ):
        return "locate"

    if re.search(
        r"^(zoom|focus|focus on)",
        q,
    ):
        return "spatial_focus"

    if re.search(
        r"^(compare|compare it|compare them|what about the other)",
        q,
    ):
        return "compare"

    if re.search(
        r"^(explain|why|why did|why has|tell me more)",
        q,
    ):
        return "explain"

    return "refine"


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------


def classify_geo_intent(
    text: str,
    context_engine: Any = None,
) -> Tuple[GeoIntent, str, Dict[str, Any]]:
    """
    Classify a natural-language geospatial request.

    Returns
    -------
    Tuple[GeoIntent, str, Dict[str, Any]]
        intent:
            The classified GeoIntent.

        target:
            Semantic analytical target.

        extra_info:
            Planner-facing metadata.

    Important:
        Classification does not execute anything and does not assert that
        the required data exists.
    """

    q = _normalize_text(text).lower()

    extra_info: Dict[str, Any] = {
        "original_text": text,
        "classifier_version": "2.0-evidence-grounded",
    }

    if not q:
        return (
            GeoIntent.CLARIFICATION,
            "unknown",
            {
                **extra_info,
                "reason": "empty_query",
            },
        )

    # ------------------------------------------------------------------
    # Explicit coordinate context
    # ------------------------------------------------------------------

    explicit_coordinates = _extract_coordinate_mentions(text)

    if explicit_coordinates:
        extra_info["explicit_coordinates"] = explicit_coordinates

    explicit_bbox = _extract_explicit_bbox(text)

    if explicit_bbox:
        extra_info["explicit_bbox"] = explicit_bbox

    # ------------------------------------------------------------------
    # Follow-up query
    # ------------------------------------------------------------------

    follow_up_action = _detect_follow_up_action(
        text,
        context_engine,
    )

    if follow_up_action:
        last_target = _context_value(
            context_engine,
            "get_last_target",
            None,
        )

        last_metrics = _context_value(
            context_engine,
            "get_last_metrics",
            None,
        )

        extra_info.update(
            {
                "is_follow_up": True,
                "follow_up_action": follow_up_action,
                "previous_target": last_target,
                "previous_metrics": last_metrics,
            }
        )

        if follow_up_action == "quantify":
            return (
                GeoIntent.AREA_MEASUREMENT,
                last_target or "previous_result",
                extra_info,
            )

        if follow_up_action in {
            "locate",
            "spatial_focus",
        }:
            return (
                GeoIntent.OBJECT_GROUNDING,
                last_target or "previous_result",
                extra_info,
            )

        return (
            GeoIntent.FOLLOW_UP_REFINEMENT,
            last_target or "previous_result",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Multi-region comparison
    # ------------------------------------------------------------------

    multiple_locations = extract_multiple_locations(
        text,
        context_engine=context_engine,
    )

    explicit_comparison = bool(
        re.search(
            r"\b(compare|comparison|versus|vs\.?|difference between)\b",
            q,
        )
    )

    if explicit_comparison and len(multiple_locations) >= 2:
        target = extract_target(text)

        extra_info.update(
            {
                "multi_locations": multiple_locations,
                "location_a": multiple_locations[0],
                "location_b": multiple_locations[1],
                "comparison_type": "multi_region",
            }
        )

        if _contains_any(q, _CHANGE_TERMS):
            return (
                GeoIntent.REGION_CHANGE_COMPARISON,
                target,
                extra_info,
            )

        return (
            GeoIntent.REGION_COMPARISON,
            target,
            extra_info,
        )

    # ------------------------------------------------------------------
    # Mission / comprehensive workflow
    # ------------------------------------------------------------------

    if _contains_any(q, _MISSION_TERMS):
        extra_info["requires_multi_step_workflow"] = True

        return (
            GeoIntent.MISSION_WORKFLOW,
            extract_target(text),
            extra_info,
        )

    # ------------------------------------------------------------------
    # Optical + SAR fusion
    # ------------------------------------------------------------------

    has_optical = _contains_any(q, _OPTICAL_TERMS)
    has_sar = _contains_any(q, _SAR_TERMS)

    if has_optical and has_sar:
        extra_info["requires_cross_modal_inputs"] = True

        return (
            GeoIntent.OPTICAL_SAR_FUSION,
            extract_target(text),
            extra_info,
        )

    # ------------------------------------------------------------------
    # Thermal
    # ------------------------------------------------------------------

    if _contains_any(q, _THERMAL_TERMS):
        extra_info["requires_thermal_evidence"] = True

        return (
            GeoIntent.THERMAL_HOTSPOT,
            "thermal_hotspot",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Spectral index
    # ------------------------------------------------------------------

    if _contains_any(q, _INDEX_TERMS):
        index_name = "spectral_index"

        for index in (
            "ndvi",
            "ndwi",
            "ndbi",
            "mndwi",
            "savi",
        ):
            if index in q:
                index_name = index.upper()
                break

        extra_info["requested_index"] = index_name

        return (
            GeoIntent.SPECTRAL_INDEX,
            index_name,
            extra_info,
        )

    # ------------------------------------------------------------------
    # SAR flood analysis
    # ------------------------------------------------------------------

    if has_sar and _contains_any(q, _FLOOD_TERMS):
        extra_info["requires_SAR"] = True

        return (
            GeoIntent.SAR_FLOOD_MAPPING,
            "flood_inundation",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Satellite/catalog search
    # ------------------------------------------------------------------

    if _contains_any(q, _SEARCH_TERMS):
        extra_info["requires_catalog_search"] = True

        return (
            GeoIntent.SATELLITE_SEARCH,
            extract_target(text),
            extra_info,
        )

    # ------------------------------------------------------------------
    # Object counting
    # ------------------------------------------------------------------

    if _contains_any(q, _COUNT_TERMS):
        if _contains_any(q, ("building", "buildings", "house", "houses")):
            target = "buildings"
        elif _contains_any(q, ("ship", "ships", "vessel", "vessels")):
            target = "ships"
        elif _contains_any(q, ("vehicle", "vehicles", "car", "cars")):
            target = "vehicles"
        elif _contains_any(q, ("aircraft", "airplanes", "plane")):
            target = "aircraft"
        else:
            target = "objects"

        extra_info["count_target"] = target

        return (
            GeoIntent.OBJECT_COUNTING,
            target,
            extra_info,
        )

    # ------------------------------------------------------------------
    # Grounding / spatial highlighting
    # ------------------------------------------------------------------

    if _contains_any(q, _GROUNDING_TERMS):
        if _contains_any(q, _WATER_TERMS):
            target = "water"
        elif _contains_any(q, _VEGETATION_TERMS):
            target = "vegetation"
        elif _contains_any(q, _URBAN_TERMS):
            target = "urban"
        elif _contains_any(q, _DAMAGE_TERMS):
            target = "damage"
        else:
            target = "target"

        extra_info["grounding_target"] = target

        return (
            GeoIntent.OBJECT_GROUNDING,
            target,
            extra_info,
        )

    # ------------------------------------------------------------------
    # Area measurement
    # ------------------------------------------------------------------

    if _contains_any(q, _AREA_TERMS):
        target = extract_target(text)

        extra_info["requires_geometry"] = True

        return (
            GeoIntent.AREA_MEASUREMENT,
            target,
            extra_info,
        )

    # ------------------------------------------------------------------
    # Map visualization
    # ------------------------------------------------------------------

    if _contains_any(q, _MAP_TERMS):
        target = extract_target(text)

        extra_info["requires_map_rendering"] = True

        return (
            GeoIntent.MAP_VISUALIZATION,
            target,
            extra_info,
        )

    # ------------------------------------------------------------------
    # Flood / inundation
    # ------------------------------------------------------------------

    if _contains_any(q, _FLOOD_TERMS):
        return (
            GeoIntent.FLOOD_INUNDATION,
            "flood_inundation",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Water loss
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "water loss",
            "water depletion",
            "water level dropped",
            "water level decrease",
            "drying",
            "shrink",
            "shrinking",
            "depletion",
        ),
    ):
        return (
            GeoIntent.WATER_LOSS,
            "water_loss",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Deforestation
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "deforestation",
            "deforest",
            "forest loss",
            "tree loss",
            "canopy loss",
            "logging",
            "clear cut",
            "clearcut",
        ),
    ):
        return (
            GeoIntent.DEFORESTATION,
            "vegetation_loss",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Vegetation growth
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "vegetation growth",
            "greening",
            "reforestation",
            "canopy gain",
            "crop growth",
            "vegetation increase",
        ),
    ):
        return (
            GeoIntent.VEGETATION_GROWTH,
            "vegetation_growth",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Agriculture
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "agriculture",
            "agricultural",
            "crop",
            "crops",
            "farmland",
            "farm field",
            "crop field",
        ),
    ):
        if _contains_any(q, _CHANGE_TERMS):
            return (
                GeoIntent.VEGETATION_GROWTH,
                "agriculture_change",
                extra_info,
            )

        return (
            GeoIntent.AGRICULTURE_MONITORING,
            "agriculture",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Urban expansion
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "urban expansion",
            "urban sprawl",
            "city expansion",
            "built-up expansion",
            "built up expansion",
            "new construction",
            "construction growth",
        ),
    ):
        return (
            GeoIntent.URBAN_EXPANSION,
            "urban_expansion",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Damage assessment
    # ------------------------------------------------------------------

    if _contains_any(q, _DAMAGE_TERMS):
        return (
            GeoIntent.DAMAGE_ASSESSMENT,
            "damage",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Wildfire / burn scar
    # ------------------------------------------------------------------

    if _contains_any(q, _FIRE_TERMS):
        return (
            GeoIntent.WILDFIRE_BURN,
            "burn_scar",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Drought
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "drought",
            "dry stress",
            "water stress",
            "moisture stress",
        ),
    ):
        return (
            GeoIntent.DROUGHT_ANALYSIS,
            "drought",
            extra_info,
        )

    # ------------------------------------------------------------------
    # General change detection
    # ------------------------------------------------------------------

    if _contains_any(q, _CHANGE_TERMS):
        target = extract_target(text)

        if target == "water":
            return (
                GeoIntent.WATER_LOSS,
                "water_change",
                extra_info,
            )

        if target in {
            "vegetation",
            "vegetation_loss",
            "vegetation_growth",
        }:
            return (
                GeoIntent.BI_TEMPORAL_CHANGE,
                target,
                extra_info,
            )

        if target == "urban":
            return (
                GeoIntent.URBAN_EXPANSION,
                "urban_expansion",
                extra_info,
            )

        return (
            GeoIntent.BI_TEMPORAL_CHANGE,
            "surface_change",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Explicit description / caption
    # ------------------------------------------------------------------

    if (
        q.startswith("describe")
        or q.startswith("give me a description")
        or "caption this" in q
        or "caption the image" in q
        or "describe this image" in q
        or "describe the image" in q
        or "overview of this image" in q
        or "scene description" in q
    ):
        return (
            GeoIntent.IMAGE_CAPTIONING,
            "scene_overview",
            extra_info,
        )

    # ------------------------------------------------------------------
    # Earth / remote-sensing knowledge
    # ------------------------------------------------------------------

    if _contains_any(q, _GENERAL_KNOWLEDGE_TERMS):
        # If the query clearly refers to a supplied image, it is not
        # general knowledge.
        image_reference = _contains_any(
            q,
            (
                "this image",
                "this satellite image",
                "this scene",
                "this area",
                "here",
                "this location",
            ),
        )

        if not image_reference:
            return (
                GeoIntent.GENERAL_EARTH_KNOWLEDGE,
                "earth_geography",
                extra_info,
            )

    # ------------------------------------------------------------------
    # VQA
    # ------------------------------------------------------------------

    if (
        q.endswith("?")
        or q.startswith("what ")
        or q.startswith("what's ")
        or q.startswith("is there")
        or q.startswith("are there")
        or q.startswith("does ")
        or q.startswith("do ")
        or q.startswith("which ")
        or q.startswith("where ")
        or q.startswith("how ")
    ):
        return (
            GeoIntent.SINGLE_IMAGE_VQA,
            extract_target(text),
            extra_info,
        )

    # ------------------------------------------------------------------
    # Contextual image reference
    # ------------------------------------------------------------------

    if _contains_any(
        q,
        (
            "this image",
            "this scene",
            "this satellite image",
            "this area",
            "here",
            "this place",
        ),
    ):
        return (
            GeoIntent.SINGLE_IMAGE_VQA,
            extract_target(text),
            extra_info,
        )

    # ------------------------------------------------------------------
    # Conservative fallback
    # ------------------------------------------------------------------

    return (
        GeoIntent.UNSUPPORTED,
        extract_target(text),
        {
            **extra_info,
            "reason": "no_supported_intent_pattern",
        },
    )


# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------


def get_intent_metadata(
    intent: GeoIntent,
) -> IntentMetadata:
    """Return metadata for an intent."""

    return INTENT_METADATA_REGISTRY.get(
        intent,
        INTENT_METADATA_REGISTRY[GeoIntent.UNSUPPORTED],
    )


def get_required_capabilities(
    intent: GeoIntent,
) -> List[ExecutionCapability]:
    """Return capabilities associated with an intent."""

    metadata = get_intent_metadata(intent)

    return list(metadata.capabilities)


def get_required_input_modes(
    intent: GeoIntent,
) -> List[InputMode]:
    """Return accepted input modes for an intent."""

    metadata = get_intent_metadata(intent)

    return list(metadata.input_modes)


def get_required_evidence(
    intent: GeoIntent,
) -> List[str]:
    """Return evidence requirements for an intent."""

    metadata = get_intent_metadata(intent)

    return list(metadata.required_evidence)


def intent_requires_images(
    intent: GeoIntent,
) -> bool:
    """Return whether the intent requires imagery."""

    metadata = get_intent_metadata(intent)

    return metadata.min_images_required > 0


def intent_requires_two_images(
    intent: GeoIntent,
) -> bool:
    """Return whether at least two images are required."""

    metadata = get_intent_metadata(intent)

    return metadata.min_images_required >= 2


def intent_is_conversational(
    intent: GeoIntent,
) -> bool:
    """Return whether the intent primarily operates on conversation context."""

    return intent in {
        GeoIntent.FOLLOW_UP_REFINEMENT,
        GeoIntent.CLARIFICATION,
    }


def intent_is_change_analysis(
    intent: GeoIntent,
) -> bool:
    """Return whether the intent requires temporal/change reasoning."""

    return intent in {
        GeoIntent.BI_TEMPORAL_CHANGE,
        GeoIntent.REGION_CHANGE_COMPARISON,
        GeoIntent.WATER_LOSS,
        GeoIntent.FLOOD_INUNDATION,
        GeoIntent.URBAN_EXPANSION,
        GeoIntent.DEFORESTATION,
        GeoIntent.VEGETATION_GROWTH,
        GeoIntent.DROUGHT_ANALYSIS,
        GeoIntent.WILDFIRE_BURN,
        GeoIntent.DAMAGE_ASSESSMENT,
        GeoIntent.MULTI_IMAGE_VQA,
    }


def intent_is_cross_modal(
    intent: GeoIntent,
) -> bool:
    """Return whether the intent requires multiple sensor modalities."""

    return intent == GeoIntent.OPTICAL_SAR_FUSION


def intent_needs_spatial_context(
    intent: GeoIntent,
) -> bool:
    """Return whether spatial context is important for execution."""

    return intent in {
        GeoIntent.AREA_MEASUREMENT,
        GeoIntent.MAP_VISUALIZATION,
        GeoIntent.REGION_COMPARISON,
        GeoIntent.REGION_CHANGE_COMPARISON,
        GeoIntent.OBJECT_GROUNDING,
        GeoIntent.MISSION_WORKFLOW,
    }


# ---------------------------------------------------------------------------
# Model compatibility
# ---------------------------------------------------------------------------


MODEL_CAPABILITY_MAP: Dict[str, ExecutionCapability] = {
    "RS_VQA": ExecutionCapability.RS_VQA,
    "RS_CAPTION": ExecutionCapability.RS_CAPTION,
    "RS_GROUNDING": ExecutionCapability.RS_GROUNDING,
    "CHANGE_DETECTION": ExecutionCapability.CHANGE_DETECTION,
    "CHANGE_VQA": ExecutionCapability.CHANGE_VQA,
    "OPTICAL_SAR_FUSION": ExecutionCapability.OPTICAL_SAR_FUSION,
}


def capabilities_supported_by_models(
    available_models: Optional[Sequence[str]],
    intent: GeoIntent,
) -> List[str]:
    """
    Return registered model names that can satisfy an intent.

    This function does not claim that the models are loaded or that
    execution will succeed. It only performs capability matching.
    """

    if not available_models:
        return []

    required = set(get_required_capabilities(intent))

    supported: List[str] = []

    for model_name in available_models:
        capability = MODEL_CAPABILITY_MAP.get(str(model_name))

        if capability in required:
            supported.append(str(model_name))

    return supported


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------


def classify_intent(
    text: str,
    context_engine: Any = None,
) -> Tuple[GeoIntent, str, Dict[str, Any]]:
    """
    Backward-compatible alias for classify_geo_intent().
    """

    return classify_geo_intent(
        text=text,
        context_engine=context_engine,
    )


def get_metadata(
    intent: GeoIntent,
) -> IntentMetadata:
    """Backward-compatible alias."""

    return get_intent_metadata(intent)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def intent_to_dict(
    intent: GeoIntent,
) -> Dict[str, Any]:
    """
    Serialize ontology metadata for planner/API/debug use.
    """

    metadata = get_intent_metadata(intent)

    return {
        "intent": metadata.intent.value,
        "min_images_required": metadata.min_images_required,
        "max_images_required": metadata.max_images_required,
        "input_modes": [
            mode.value
            for mode in metadata.input_modes
        ],
        "capabilities": [
            capability.value
            for capability in metadata.capabilities
        ],
        "required_evidence": list(
            metadata.required_evidence
        ),
        "optional_evidence": list(
            metadata.optional_evidence
        ),
        "target_types": list(
            metadata.target_types
        ),
        "description": metadata.description,
        "clarification_required_when": list(
            metadata.clarification_required_when
        ),
        # Compatibility information.
        "allow_auto_catalog_fetch": metadata.allow_auto_catalog_fetch,
        "default_bands": list(metadata.default_bands),
        "recommended_sensors": list(metadata.recommended_sensors),
        "metrics_types": list(metadata.metrics_types),
        "sensor_reality_note": metadata.sensor_reality_note,
    }


# ---------------------------------------------------------------------------
# Public ontology API
# ---------------------------------------------------------------------------


__all__ = [
    "GeoIntent",
    "InputMode",
    "ExecutionCapability",
    "IntentMetadata",
    "INTENT_METADATA_REGISTRY",
    "MODEL_CAPABILITY_MAP",
    "extract_multiple_locations",
    "extract_target",
    "classify_geo_intent",
    "classify_intent",
    "get_intent_metadata",
    "get_metadata",
    "get_required_capabilities",
    "get_required_input_modes",
    "get_required_evidence",
    "intent_requires_images",
    "intent_requires_two_images",
    "intent_is_conversational",
    "intent_is_change_analysis",
    "intent_is_cross_modal",
    "intent_needs_spatial_context",
    "capabilities_supported_by_models",
    "intent_to_dict",
]