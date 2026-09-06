"""SatQuery AI Comprehensive Intent Ontology and Semantic Intent Classifier.
Defines 20+ fine-grained geospatial intents, required input constraints,
and multi-location comparative classification per §7, §24, §57.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple

from apps.agent.context_engine import ContextEngine, ResolvedSpatialContext, ResolvedTemporalContext
from apps.agent.geocoding import _GEOCODE_CACHE, resolve_location


class GeoIntent(str, Enum):
    # Change Detection & Dynamics
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

    # Single Scene & Visual Analysis
    OBJECT_COUNTING = "OBJECT_COUNTING"
    OBJECT_GROUNDING = "OBJECT_GROUNDING"
    SINGLE_IMAGE_VQA = "SINGLE_IMAGE_VQA"
    MULTI_IMAGE_VQA = "MULTI_IMAGE_VQA"
    IMAGE_CAPTIONING = "IMAGE_CAPTIONING"

    # Sensor & Cross-Modal
    SAR_FLOOD_MAPPING = "SAR_FLOOD_MAPPING"
    OPTICAL_SAR_FUSION = "OPTICAL_SAR_FUSION"
    SPECTRAL_INDEX = "SPECTRAL_INDEX"

    # Multi-Region & Comparative
    REGION_COMPARISON = "REGION_COMPARISON"

    # Search & Mission
    SATELLITE_SEARCH = "SATELLITE_SEARCH"
    MISSION_WORKFLOW = "MISSION_WORKFLOW"

    # Spatial Visualization & Thermal Hotspots
    THERMAL_HOTSPOT = "THERMAL_HOTSPOT"
    MAP_VISUALIZATION = "MAP_VISUALIZATION"
    AREA_MEASUREMENT = "AREA_MEASUREMENT"
    VEGETATION_ANALYSIS = "VEGETATION_ANALYSIS"
    WATER_ANALYSIS = "WATER_ANALYSIS"
    URBAN_ANALYSIS = "URBAN_ANALYSIS"
    REGION_CHANGE_COMPARISON = "REGION_CHANGE_COMPARISON"

    # Conversational Flow & General Knowledge
    FOLLOW_UP_REFINEMENT = "FOLLOW_UP_REFINEMENT"
    CLARIFICATION = "CLARIFICATION"
    GENERAL_EARTH_KNOWLEDGE = "GENERAL_EARTH_KNOWLEDGE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class IntentMetadata:
    intent: GeoIntent
    min_images_required: int = 1
    allow_auto_catalog_fetch: bool = True
    default_bands: List[str] = field(default_factory=lambda: ["B04", "B03", "B02", "B08"])
    recommended_sensors: List[str] = field(default_factory=lambda: ["SENTINEL-2"])
    metrics_types: List[str] = field(default_factory=lambda: ["area_km2", "model_confidence_pct"])
    description: str = ""
    sensor_reality_note: Optional[str] = None


INTENT_METADATA_REGISTRY: Dict[GeoIntent, IntentMetadata] = {
    GeoIntent.BI_TEMPORAL_CHANGE: IntentMetadata(
        intent=GeoIntent.BI_TEMPORAL_CHANGE,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        metrics_types=["total_changed_km2", "change_pct", "model_confidence_pct"],
        description="Detect general surface and land-cover changes between two temporal observations.",
    ),
    GeoIntent.WATER_LOSS: IntentMetadata(
        intent=GeoIntent.WATER_LOSS,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B03", "B08", "B11", "B12"],
        metrics_types=["water_lost_km2", "water_lost_pct", "depletion_rate_ha_day", "model_confidence_pct"],
        description="Quantify shrinkage or drying of water bodies, lakes, and reservoirs.",
    ),
    GeoIntent.FLOOD_INUNDATION: IntentMetadata(
        intent=GeoIntent.FLOOD_INUNDATION,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["VV", "VH", "B03", "B08"],
        recommended_sensors=["SENTINEL-1", "SENTINEL-2"],
        metrics_types=["inundated_area_km2", "water_expansion_pct", "settlements_affected", "model_confidence_pct"],
        description="Delineate inundated terrain and water spread from floods or heavy rainfall.",
    ),
    GeoIntent.URBAN_EXPANSION: IntentMetadata(
        intent=GeoIntent.URBAN_EXPANSION,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B04", "B03", "B02", "B08", "B11"],
        metrics_types=["built_up_added_km2", "urban_expansion_pct", "growth_direction", "model_confidence_pct"],
        description="Measure new buildings, settlements, and road network sprawl.",
    ),
    GeoIntent.DEFORESTATION: IntentMetadata(
        intent=GeoIntent.DEFORESTATION,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B04", "B08", "B11"],
        metrics_types=["canopy_lost_km2", "loss_pct", "ndvi_depletion_mean", "model_confidence_pct"],
        description="Detect tree cover loss, clear-cutting, and agricultural encroachment.",
    ),
    GeoIntent.VEGETATION_GROWTH: IntentMetadata(
        intent=GeoIntent.VEGETATION_GROWTH,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B04", "B08"],
        metrics_types=["canopy_gained_km2", "greening_pct", "ndvi_increase_mean", "model_confidence_pct"],
        description="Identify re-vegetation, crop maturation, and reforestation canopy gain.",
    ),
    GeoIntent.DROUGHT_ANALYSIS: IntentMetadata(
        intent=GeoIntent.DROUGHT_ANALYSIS,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B08", "B11", "B12"],
        metrics_types=["soil_moisture_index_delta", "vegetation_condition_index", "model_confidence_pct"],
        description="Assess agricultural moisture stress and persistent dry anomalies.",
    ),
    GeoIntent.WILDFIRE_BURN: IntentMetadata(
        intent=GeoIntent.WILDFIRE_BURN,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        default_bands=["B08", "B12"],
        metrics_types=["burned_area_km2", "nbr_severity_score", "model_confidence_pct"],
        description="Identify burned scars and severity per Normalized Burn Ratio.",
    ),
    GeoIntent.AGRICULTURE_MONITORING: IntentMetadata(
        intent=GeoIntent.AGRICULTURE_MONITORING,
        min_images_required=1,
        allow_auto_catalog_fetch=True,
        default_bands=["B04", "B08", "B05", "B06"],
        metrics_types=["active_cropland_km2", "mean_ndvi", "crop_vigor_score", "model_confidence_pct"],
        description="Classify agricultural field vigor and phenology states.",
    ),
    GeoIntent.DAMAGE_ASSESSMENT: IntentMetadata(
        intent=GeoIntent.DAMAGE_ASSESSMENT,
        min_images_required=2,
        allow_auto_catalog_fetch=True,
        metrics_types=["damaged_structures_count", "damage_ratio_pct", "model_confidence_pct"],
        description="Post-disaster structural and infrastructure damage estimation.",
    ),
    GeoIntent.OBJECT_COUNTING: IntentMetadata(
        intent=GeoIntent.OBJECT_COUNTING,
        min_images_required=1,
        metrics_types=["count", "density_per_km2", "model_confidence_pct"],
        description="Count distinct localized objects (vessels, buildings, storage tanks).",
    ),
    GeoIntent.OBJECT_GROUNDING: IntentMetadata(
        intent=GeoIntent.OBJECT_GROUNDING,
        min_images_required=1,
        metrics_types=["target_extent_km2", "polygon_count", "model_confidence_pct"],
        description="Locate, outline, and highlight specific ground targets.",
    ),
    GeoIntent.SINGLE_IMAGE_VQA: IntentMetadata(
        intent=GeoIntent.SINGLE_IMAGE_VQA,
        min_images_required=1,
        metrics_types=["model_confidence_pct"],
        description="Natural language question answering on a single observation.",
    ),
    GeoIntent.MULTI_IMAGE_VQA: IntentMetadata(
        intent=GeoIntent.MULTI_IMAGE_VQA,
        min_images_required=2,
        metrics_types=["model_confidence_pct"],
        description="Cross-temporal reasoning comparing multiple observations.",
    ),
    GeoIntent.IMAGE_CAPTIONING: IntentMetadata(
        intent=GeoIntent.IMAGE_CAPTIONING,
        min_images_required=1,
        metrics_types=["model_confidence_pct"],
        description="Generate comprehensive geological and infrastructural scene descriptions.",
    ),
    GeoIntent.SAR_FLOOD_MAPPING: IntentMetadata(
        intent=GeoIntent.SAR_FLOOD_MAPPING,
        min_images_required=1,
        default_bands=["VV", "VH"],
        recommended_sensors=["SENTINEL-1"],
        metrics_types=["sar_water_km2", "backscatter_threshold_db", "model_confidence_pct"],
        description="SAR backscatter thresholding for all-weather, cloud-penetrating water detection.",
    ),
    GeoIntent.OPTICAL_SAR_FUSION: IntentMetadata(
        intent=GeoIntent.OPTICAL_SAR_FUSION,
        min_images_required=2,
        recommended_sensors=["SENTINEL-2", "SENTINEL-1"],
        metrics_types=["fused_water_km2", "fused_built_up_km2", "fusion_alignment_score", "model_confidence_pct"],
        description="Fuse optical multi-spectral with polarimetric SAR to suppress cloud and false specular reflections.",
    ),
    GeoIntent.SPECTRAL_INDEX: IntentMetadata(
        intent=GeoIntent.SPECTRAL_INDEX,
        min_images_required=1,
        metrics_types=["mean_index_value", "min_index_value", "max_index_value", "model_confidence_pct"],
        description="Compute rigorous multi-spectral index rasters (NDVI, NDWI, NDBI, MNDWI).",
    ),
    GeoIntent.REGION_COMPARISON: IntentMetadata(
        intent=GeoIntent.REGION_COMPARISON,
        min_images_required=0,
        allow_auto_catalog_fetch=True,
        metrics_types=["region_a_metrics", "region_b_metrics", "comparative_delta"],
        description="Multi-AOI spatial comparison across land-cover, growth, or water resources.",
    ),
    GeoIntent.SATELLITE_SEARCH: IntentMetadata(
        intent=GeoIntent.SATELLITE_SEARCH,
        min_images_required=0,
        metrics_types=["scenes_found_count", "best_cloud_cover_pct"],
        description="Search STAC catalogs for available Sentinel or Landsat granules.",
    ),
    GeoIntent.MISSION_WORKFLOW: IntentMetadata(
        intent=GeoIntent.MISSION_WORKFLOW,
        min_images_required=1,
        metrics_types=["mission_steps_completed", "model_confidence_pct"],
        description="Multi-step comprehensive environmental or urban intelligence mission.",
    ),
    GeoIntent.FOLLOW_UP_REFINEMENT: IntentMetadata(
        intent=GeoIntent.FOLLOW_UP_REFINEMENT,
        min_images_required=0,
        metrics_types=["filtered_area_km2", "model_confidence_pct"],
        description="Filter, zoom, or quantify previous turn results without re-running full acquisition.",
    ),
    GeoIntent.CLARIFICATION: IntentMetadata(
        intent=GeoIntent.CLARIFICATION,
        min_images_required=0,
        metrics_types=[],
        description="Elicit user clarification for missing spatial, temporal, or target parameters.",
    ),
    GeoIntent.THERMAL_HOTSPOT: IntentMetadata(
        intent=GeoIntent.THERMAL_HOTSPOT,
        min_images_required=1,
        recommended_sensors=["SENTINEL-2", "LANDSAT-8/9-TIRS", "MODIS"],
        metrics_types=["hotspot_count", "primary_centroid_coords", "thermal_density_score", "model_confidence_pct"],
        description="Spatial change density heatmap & cluster centroids with thermal sensor reality grounding (Sentinel-2 VNIR/SWIR vs Landsat TIRS).",
        sensor_reality_note="Sentinel-2 MSI is an optical VNIR/SWIR instrument and lacks a thermal infrared (TIR) radiometer. True surface temperature requires Landsat-8/9 TIRS or MODIS.",
    ),
    GeoIntent.MAP_VISUALIZATION: IntentMetadata(
        intent=GeoIntent.MAP_VISUALIZATION,
        min_images_required=1,
        metrics_types=["polygon_count", "total_area_km2", "model_confidence_pct"],
        description="Interactive GIS vector map and density heatmap rendering on MapLibre.",
    ),
    GeoIntent.AREA_MEASUREMENT: IntentMetadata(
        intent=GeoIntent.AREA_MEASUREMENT,
        min_images_required=1,
        metrics_types=["total_area_km2", "pixel_count", "source_crs", "analysis_crs"],
        description="Rigorously proven surface area metric integration backed by pixel count and equal-area projection.",
    ),
    GeoIntent.GENERAL_EARTH_KNOWLEDGE: IntentMetadata(
        intent=GeoIntent.GENERAL_EARTH_KNOWLEDGE,
        min_images_required=0,
        metrics_types=[],
        description="Global topographical, geographical, and remote-sensing sensor knowledge.",
    ),
}


def extract_multiple_locations(query: str) -> List[Dict[str, Any]]:
    """Detects multiple geographic locations mentioned in comparative queries."""
    q = query.lower()

    # 1. Check pattern e.g. "compare X and Y", "difference between X and Y"
    comp_match = re.search(
        r"(?:compare|difference between|versus|vs\.?)\s+([a-zA-Z\s]{2,25})\s+(?:and|with|to|vs\.?)\s+([a-zA-Z\s]{2,25})",
        query,
        re.IGNORECASE,
    )
    if comp_match:
        from apps.agent.location_resolver import LocationResolver
        detected_comp = []
        loc1_name = comp_match.group(1).strip()
        loc2_name = comp_match.group(2).strip()
        for cand in [loc1_name, loc2_name]:
            cand_clean = cand.strip()
            # Try resolving via LocationResolver (exact, gazetteer alias, or fuzzy typo-tolerant)
            resolved = LocationResolver.resolve(cand_clean, allow_fuzzy=True, allow_network=False)
            if resolved and resolved.is_valid:
                detected_comp.append(resolved.to_dict())
            else:
                cand_lower = cand_clean.lower()
                if cand_lower in _GEOCODE_CACHE:
                    detected_comp.append(dict(_GEOCODE_CACHE[cand_lower]))
                else:
                    # Unresolvable geographic domain -> mark explicitly as invalid
                    detected_comp.append({
                        "name": cand_clean.title(),
                        "canonical_name": cand_clean.title(),
                        "bbox": None,
                        "coords": None,
                        "is_valid": False,
                        "source": "unresolved_candidate",
                    })
        return detected_comp

    # 2. Check known cache keys if not an explicit 2-location comparison pattern
    detected = []
    for key, val in _GEOCODE_CACHE.items():
        if re.search(rf"\b{re.escape(key)}\b", q):
            if not any(d["name"] == val["name"] for d in detected):
                detected.append(dict(val))

    return detected


def classify_geo_intent(
    text: str,
    context_engine: Optional[ContextEngine] = None,
) -> Tuple[GeoIntent, str, Dict[str, Any]]:
    """Accurately classifies the user query into a GeoIntent with target and execution hints.

    Returns:
        (intent, target, extra_info)
    """
    q = text.lower().strip()
    extra_info: Dict[str, Any] = {}

    # 1. Multi-location comparison check
    detected_locations = extract_multiple_locations(text)
    is_comparison_query = (
        len(detected_locations) >= 2
        or "compare " in q
        or " versus " in q
        or " vs " in q
        or "difference between " in q
    )
    if is_comparison_query and len(detected_locations) >= 2:
        extra_info["multi_locations"] = detected_locations
        extra_info["location_a"] = detected_locations[0]
        extra_info["location_b"] = detected_locations[1]

        # Determine target of comparison
        if any(w in q for w in ("urban", "expansion", "city", "built", "construction")):
            target = "urban_expansion"
        elif any(w in q for w in ("water", "reservoir", "lake", "river", "flood", "port")):
            target = "water_resources"
        elif any(w in q for w in ("vegetation", "forest", "green", "canopy", "agriculture")):
            target = "canopy_and_vegetation"
        else:
            target = "landscape_and_urban_dynamics"

        return GeoIntent.REGION_COMPARISON, target, extra_info

    # 2. Follow-up query detection
    if context_engine is not None and context_engine.is_follow_up_query(text):
        last_metrics = context_engine.get_last_metrics()
        last_target = context_engine.get_last_target() or "surface_change"
        extra_info["is_follow_up"] = True
        extra_info["previous_metrics"] = last_metrics

        # Filter follow-up (e.g. "only show vegetation", "just water")
        if re.search(r"^(only|just)\s+(show\s+)?(vegetation|water|urban|buildings|forest|roads|damage)", q):
            m = re.search(r"^(only|just)\s+(show\s+)?([a-z]+)", q)
            filtered_target = m.group(3) if m else last_target
            extra_info["follow_up_action"] = "filter_target"
            extra_info["filter_target"] = filtered_target
            return GeoIntent.FOLLOW_UP_REFINEMENT, filtered_target, extra_info

        # Quantification follow-up (e.g. "how much?", "what is the total area?")
        if re.search(r"^how\s+much|^what\s+is\s+the\s+(total\s+)?area|^how\s+many\s+(km2|hectares|sq\s*km)", q):
            extra_info["follow_up_action"] = "quantify"
            return GeoIntent.FOLLOW_UP_REFINEMENT, last_target, extra_info

        # Spatial grounding follow-up (e.g. "where did it happen?", "show the polygons")
        if re.search(r"^where|^which\s+part|^show\s+(the\s+)?(polygons|map|boundaries)", q):
            extra_info["follow_up_action"] = "locate_and_segment"
            return GeoIntent.FOLLOW_UP_REFINEMENT, last_target, extra_info

    # 2b. Thermal Hotspot / Spatial Change Heatmap Queries
    if any(k in q for k in (
        "heat coordinate", "heat cordinates", "heat coordinates", "visualize heat", "visualize the heat",
        "thermal", "hotspot", "hotspots", "heat map", "heatmap", "surface temperature", "temperature coordinates"
    )):
        extra_info["sensor_reality_note"] = (
            "Sentinel-2 MSI operates in VNIR/SWIR (optical) and does not carry a thermal infrared (TIR) radiometer. "
            "Landsat-8/9 TIRS or MODIS is required for radiometric surface temperature. "
            "Generating spatial change density heatmap and cluster centroid coordinates."
        )
        return GeoIntent.THERMAL_HOTSPOT, "spatial_change_hotspots", extra_info

    # 2c. General Earth Knowledge
    if any(k in q for k in (
        "largest mountain", "highest mountain", "tallest mountain", "highest peak",
        "deepest ocean", "longest river", "what is the largest mountain"
    )):
        return GeoIntent.GENERAL_EARTH_KNOWLEDGE, "earth_geography", extra_info

    # 3. Optical + SAR Fusion check
    if ("optical" in q and "sar" in q) or ("radar" in q and "optical" in q):
        return GeoIntent.OPTICAL_SAR_FUSION, "cross_modal_fusion", extra_info

    # 4. Pure SAR Flood Mapping
    if ("sar" in q or "radar" in q or "sentinel-1" in q) and any(w in q for w in ("flood", "water", "inundat")):
        return GeoIntent.SAR_FLOOD_MAPPING, "radar_flood", extra_info

    # 5. Catalog Search
    if any(k in q for k in ("search satellite", "find sentinel", "search scene", "download imagery", "copernicus stac")):
        sensor = "SENTINEL-1" if ("sar" in q or "radar" in q) else "SENTINEL-2"
        return GeoIntent.SATELLITE_SEARCH, sensor, extra_info

    # 6. Object Counting
    if any(k in q for k in ("how many", "count ", "number of")):
        target = "buildings" if ("building" in q or "house" in q or "structure" in q) else (
            "ships" if ("ship" in q or "vessel" in q) else "objects"
        )
        return GeoIntent.OBJECT_COUNTING, target, extra_info

    # 7. Object Grounding / Spatial Highlighting
    if any(k in q for k in ("highlight", "outline", "delineate", "locate the")):
        target = "water" if "water" in q else ("vegetation" if "vegetation" in q else "buildings")
        return GeoIntent.OBJECT_GROUNDING, target, extra_info

    # 8. Spectral Index Explicit Calculation
    if any(idx in q for idx in ("ndvi", "ndwi", "ndbi", "mndwi", "savi", "spectral index")):
        idx_name = "NDVI" if "ndvi" in q else ("NDWI" if "ndwi" in q else ("NDBI" if "ndbi" in q else "SPECTRAL_INDEX"))
        return GeoIntent.SPECTRAL_INDEX, idx_name, extra_info

    # 9. Flood Inundation & Water dynamics
    if any(k in q for k in ("flood", "inundat", "submerged", "water spread")):
        return GeoIntent.FLOOD_INUNDATION, "flood_inundation", extra_info

    if any(k in q for k in ("water loss", "drying", "shrink", "deplet", "dry up", "lake level")):
        return GeoIntent.WATER_LOSS, "water_loss", extra_info

    # 10. Deforestation vs Vegetation Growth
    if any(k in q for k in ("deforest", "canopy loss", "tree loss", "logging", "clearcut", "forest loss")):
        return GeoIntent.DEFORESTATION, "vegetation_loss", extra_info

    if any(k in q for k in ("reforest", "greening", "vegetation growth", "crop growth", "canopy gain")):
        return GeoIntent.VEGETATION_GROWTH, "vegetation_gain", extra_info

    # 11. Urban Sprawl / Expansion
    if any(k in q for k in ("urban expansion", "city expansion", "urban sprawl", "built-up expansion", "new construction")):
        return GeoIntent.URBAN_EXPANSION, "urban_expansion", extra_info

    # 12. Wildfire burn scars
    if any(k in q for k in ("wildfire", "fire scar", "burn scar", "burned area", "forest fire")):
        return GeoIntent.WILDFIRE_BURN, "burn_scar", extra_info

    # 13. General Change Detection / Bi-Temporal Dynamics
    is_change_intent = (
        "between these two" in q
        or "what changed" in q
        or "what is changing" in q
        or "what has changed" in q
        or "what the changes" in q
        or "changes in here" in q
        or "change in here" in q
        or "changes here" in q
        or "what are the changes" in q
        or "any change" in q
        or "surface dynamic" in q
        or ("increased" in q and "decreased" in q)
        or ("increase" in q and "decrease" in q)
        or "remained unchanged" in q
    )
    if is_change_intent:
        if any(w in q for w in ("vegetation", "forest", "green", "agriculture", "crop")):
            return GeoIntent.DEFORESTATION, "vegetation_loss", extra_info
        if any(w in q for w in ("water", "reservoir", "lake", "river")):
            return GeoIntent.WATER_LOSS, "water_change", extra_info
        if any(w in q for w in ("building", "urban", "settlement", "construction")):
            return GeoIntent.URBAN_EXPANSION, "urban_expansion", extra_info

        return GeoIntent.BI_TEMPORAL_CHANGE, "surface_change", extra_info

    # 14. Single Image VQA vs Description
    if q.startswith("describe") or "caption" in q or "overview of this image" in q or "summary of this area" in q:
        return GeoIntent.IMAGE_CAPTIONING, "scene_overview", extra_info

    if q.endswith("?") or any(q.startswith(w) for w in ("what", "is there", "are there", "how", "does")):
        return GeoIntent.SINGLE_IMAGE_VQA, "vqa_query", extra_info

    # Default: Scene description
    return GeoIntent.IMAGE_CAPTIONING, "general_terrain", extra_info
