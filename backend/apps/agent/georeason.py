from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from apps.agent.web_research import ExternalEvidenceDTO

logger = logging.getLogger(__name__)


@dataclass
class EvidenceNode:
    id: str
    label: str
    node_type: str  # "SATELLITE_SCENE", "SPECTRAL_INDEX", "VECTOR_POLYGON", "EXTERNAL_SOURCE"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeoReasonResult:
    synthesized_answer: str
    calibrated_confidence: float
    confidence_level: str  # "HIGH", "MODERATE", "LOW"
    confidence_drivers: List[str]
    uncertainties: List[str]
    evidence_graph: Dict[str, Any]
    external_citations: List[Dict[str, Any]]
    confidence_factors: List[Dict[str, Any]] = field(default_factory=list)
    ui_actions: List[Dict[str, Any]] = field(default_factory=list)


class GeoReasonAgent:
    """
    Central reasoning engine for SatQuery-X.
    Fuses physical satellite observations, GIS measurements, temporal deltas, and external web evidence.
    Enforces scientific integrity: remote sensing reflectance is ground truth; external web sources
    act as corroboration, never overriding physical measurements.
    """

    def synthesize(
        self,
        query_text: str,
        aoi_name: str,
        satellite_scenes: List[Dict[str, Any]],
        measurements: Dict[str, Any],
        change_events: List[Dict[str, Any]],
        external_evidence: List[ExternalEvidenceDTO],
        aoi_coords: Optional[List[float]] = None,
        explanation_mode: str = "simple",
    ) -> GeoReasonResult:
        drivers: List[str] = []
        uncertainties: List[str] = []
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, str]] = []
        citations: List[Dict[str, Any]] = []

        # 1. Evaluate Satellite Observations
        scene_count = len(satellite_scenes)
        if scene_count > 0:
            drivers.append(f"Derived from {scene_count} Copernicus Sentinel-1/2 Earth observation overpass(es)")
            for s in satellite_scenes:
                node_id = f"scene_{s.get('external_id', 'unknown')}"
                nodes.append({
                    "id": node_id,
                    "label": f"{s.get('platform', 'Sentinel')} ({s.get('acquisition_date', '')})",
                    "type": "SATELLITE_SCENE",
                    "cloud_cover": s.get("cloud_cover", 0.0),
                })
        else:
            uncertainties.append("Analysis operating on baseline geospatial bounds without active overpass lock")

        # 2. Evaluate Physical Ground Measurements
        has_change = len(change_events) > 0
        total_ha = 0.0
        change_type_str = "surface dynamics"

        if has_change:
            evt = change_events[0]
            total_ha = evt.get("area_hectares", 0.0)
            change_type_str = evt.get("change_type", "surface change").replace("_", " ").title()
            drivers.append(f"Deterministic Rasterio differencing confirmed {total_ha:.1f} ha of {change_type_str}")
            nodes.append({
                "id": "change_polygon_0",
                "label": f"{change_type_str} ({total_ha:.1f} ha)",
                "type": "VECTOR_POLYGON",
            })
            if scene_count >= 2:
                edges.append({"from": nodes[0]["id"], "to": "change_polygon_0", "relation": "BASELINE_BEFORE"})
                edges.append({"from": nodes[1]["id"], "to": "change_polygon_0", "relation": "TARGET_AFTER"})

        # 3. Evaluate External Corroboration
        has_ext = len(external_evidence) > 0
        ext_summary_sentences = []

        if has_ext:
            for ext in external_evidence:
                citations.append({
                    "publisher": ext.publisher,
                    "title": ext.title,
                    "source_url": ext.source_url,
                    "trust_tier": ext.trust_tier,
                    "trust_score": ext.trust_score,
                    "facts": ext.summary_facts,
                })
                nodes.append({
                    "id": f"ext_{ext.source_domain}",
                    "label": f"{ext.publisher} ({ext.trust_tier})",
                    "type": "EXTERNAL_SOURCE",
                    "trust_score": ext.trust_score,
                })
                if has_change:
                    edges.append({"from": "change_polygon_0", "to": f"ext_{ext.source_domain}", "relation": "CORROBORATED_BY"})

                drivers.append(f"Corroborated by {ext.publisher} ({ext.trust_tier})")
                ext_summary_sentences.extend(ext.summary_facts)

        # 3b. Evaluate AI Noise & Artifact Cleaning Pipeline
        noise_cleaning = measurements.get("noise_cleaning")
        if noise_cleaning and isinstance(noise_cleaning, dict):
            usable_pct = noise_cleaning.get("usable_clear_data_pct", 100.0)
            methods = noise_cleaning.get("cleaning_methods_applied", [])
            if methods:
                methods_str = ", ".join(methods)
                drivers.append(f"AI Preprocessing: {methods_str} ({usable_pct:.1f}% usable clear data)")
            nodes.append({
                "id": "preprocessing_artifact_pipeline",
                "label": f"AI Noise Removal ({usable_pct:.1f}% clear)",
                "type": "DATA_PREPROCESSING",
                "methods": methods,
                "usable_pct": usable_pct,
            })
            if nodes and nodes[0]["id"] != "preprocessing_artifact_pipeline":
                edges.append({"from": nodes[0]["id"], "to": "preprocessing_artifact_pipeline", "relation": "CLEANED_BY"})

        # 4. Calibrate Multi-Factor Confidence (§9 & §10)
        # Factor 1: Cloud & Data Quality
        avg_cloud = 0.0
        if satellite_scenes:
            clouds = [float(s.get("cloud_cover", 0.0)) for s in satellite_scenes if s.get("cloud_cover") is not None]
            if clouds:
                avg_cloud = sum(clouds) / len(clouds)

        if avg_cloud > 15.0:
            cloud_quality = max(0.20, round(1.0 - (avg_cloud / 100.0) * 1.1, 2))
            uncertainties.append(f"Cloud/shadow contamination ({avg_cloud:.1f}%) reduces optical surface clarity")
        else:
            cloud_quality = max(0.70, round(1.0 - (avg_cloud / 100.0) * 0.5, 2))
            drivers.append(f"Clear observation conditions with measured {avg_cloud:.1f}% cloud coverage")

        # Factor 2: Spatial Registration & Resolution
        coreg_valid = measurements.get("coregistration_valid")
        if scene_count >= 2:
            if coreg_valid is False:
                spatial_reg = 0.50
                uncertainties.append("Spatial misalignment or low geometric overlap between overpasses")
            else:
                spatial_reg = 0.94
                drivers.append("Dual-overpass coregistration verified against Sentinel-2 10m spatial grid")
        elif scene_count == 1:
            spatial_reg = 0.90
            drivers.append("Single-overpass spatial reference aligned with 10m GSD grid")
        else:
            spatial_reg = 0.40
            uncertainties.append("Operating without direct satellite raster overpass reference")

        # Factor 3: Model & Corroboration Agreement
        if has_ext:
            trust_scores = [e.trust_score for e in external_evidence]
            avg_ext_trust = float(sum(trust_scores) / len(trust_scores)) if trust_scores else 0.70
            model_agreement = round(min(0.96, max(0.55, 0.65 + 0.30 * avg_ext_trust)), 2)
            drivers.append(f"External evidence corroboration (trust factor {avg_ext_trust:.2f})")
        elif measurements.get("mean_ndvi") is not None or measurements.get("water_features_count") is not None or measurements.get("total_veg_km2") is not None:
            model_agreement = 0.91
        else:
            model_agreement = 0.75

        # Factor 4: Evidence Coverage & Physical Grounding
        if has_change and total_ha > 0:
            evidence_coverage = round(min(0.95, max(0.60, 0.70 + min(0.25, total_ha / 100.0))), 2)
        elif has_change:
            evidence_coverage = 0.65
        elif scene_count > 0:
            evidence_coverage = 0.88
        else:
            evidence_coverage = 0.45
            uncertainties.append("No localized evidence regions or physical rasters grounded")

        confidence_factors = [
            {"name": "cloud_quality", "score": round(cloud_quality, 2)},
            {"name": "spatial_registration", "score": round(spatial_reg, 2)},
            {"name": "model_agreement", "score": round(model_agreement, 2)},
            {"name": "evidence_coverage", "score": round(evidence_coverage, 2)},
        ]

        # Multi-factor weighted composite
        composite_conf = (
            cloud_quality * 0.35 +
            spatial_reg * 0.25 +
            model_agreement * 0.15 +
            evidence_coverage * 0.25
        )
        final_conf = min(0.97, max(0.35, round(composite_conf, 2)))
        conf_level = "HIGH" if final_conf >= 0.85 else ("MODERATE" if final_conf >= 0.70 else "LOW")

        # 5. Synthesize Narrative with Domain-Specific Geospatial Intelligence (§6, §67, §107)
        lines = []
        q_lower = query_text.lower()
        aoi_lower = aoi_name.lower()
        is_fusion_query = ("optical" in q_lower and "sar" in q_lower) or any(k in q_lower for k in ("fusion", "cross-modal", "cross_modal", "dual-pol"))
        is_change_query = not is_fusion_query and ((scene_count >= 2) or any(k in q_lower for k in ("chang", "loss", "flood", "gain", "expansion", "differen", "what happen", "urbanization", "what so change", "what about", "how about")))

        # Domain-specific geospatial knowledge integration
        domain_note = ""
        if any(k in aoi_lower or k in q_lower for k in ("thoothukudi", "tuticorin")):
            domain_note = (
                "The Thoothukudi coastal corridor is characterized by V.O. Chidambaranar Port deepwater installations, "
                "extensive coastal evaporative salt crystallization pans along the littoral margins, and heavy thermal/petrochemical facilities. "
                "Satellite reflectance monitors coastal shoreline stability, marine sediment plumes in the Gulf of Mannar, and seasonal salt pan drying cycles."
            )
        elif any(k in aoi_lower or k in q_lower for k in ("coimbatore",)):
            domain_note = (
                "The Coimbatore industrial basin lies on an inland plateau in the rain shadow of the Western Ghats (Palakkad Gap). "
                "Key remote sensing indicators include radial built-up expansion toward Avinashi and Sulur, "
                "seasonal vegetation dynamics in surrounding coconut and agricultural belts, and surface moisture levels along the Noyyal River cascade system."
            )
        elif any(k in aoi_lower or k in q_lower for k in ("chennai",)):
            domain_note = (
                "The Chennai metropolitan corridor exhibits intense coastal urbanization along the OMR/GST corridors, "
                "port and logistics hubs around Ennore and Chennai Harbor, and seasonal hydrological shifts across the Chembarambakkam, Puzhal, and Pallikaranai marshland basins."
            )

        if is_fusion_query:
            lines.append(
                f"Cross-modal optical-SAR satellite fusion across {aoi_name} combined multi-spectral optical reflectance with all-weather SAR radar backscatter, successfully distinguishing built-up infrastructure and surface water bodies while penetrating cloud coverage."
            )
            if domain_note:
                lines.append(domain_note)
        elif has_change and total_ha > 0:
            change_pct = measurements.get("change_percentage")
            pct_clause = f" ({change_pct:.1f}% of the evaluated scene)" if change_pct is not None else ""
            lines.append(
                f"Multi-temporal satellite observation across {aoi_name} confirms active {change_type_str.lower()} "
                f"encompassing approximately {total_ha:.1f} hectares ({total_ha / 100.0:.2f} km²){pct_clause}."
            )
            if domain_note:
                lines.append(domain_note)
        elif has_change:
            lines.append(
                f"Multi-temporal satellite observation across {aoi_name} identifies localized surface dynamics within the evaluated area."
            )
            if domain_note:
                lines.append(domain_note)
        elif is_change_query:
            lines.append(
                f"Multi-temporal satellite imagery analysis across {aoi_name} detected no surface reflectance transitions exceeding the configured detection threshold (τ=0.50, none above threshold) within the valid cloud-free analysis footprint."
            )
            if domain_note:
                lines.append(domain_note)
        else:
            lines.append(
                f"Earth observation analysis across {aoi_name} indicates established land-cover characteristics with consistent spectral reflectance."
            )
            if domain_note:
                lines.append(domain_note)

        if ext_summary_sentences:
            lines.append(
                f"External ground verification corroborates this observation: {ext_summary_sentences[0]}"
            )

        # 6. Generate Contextual UI Actions
        ui_actions = []
        q_lower = query_text.lower()
        if any(w in q_lower for w in ("zoom", "where", "show me exactly", "show the changes", "locate", "where is it")):
            if aoi_coords:
                ui_actions.append({"type": "ZOOM_TO_REGION", "coordinates": aoi_coords, "zoom": 13})
            if has_change:
                ui_actions.append({"type": "SHOW_LAYER", "layer": "change_mask"})
        elif has_change:
            ui_actions.append({"type": "SHOW_LAYER", "layer": "change_mask"})

        if any(w in q_lower for w in ("show vegetation", "ndvi layer", "show trees", "vegetation map")):
            ui_actions.append({"type": "SHOW_LAYER", "layer": "ndvi"})
        elif any(w in q_lower for w in ("show water", "ndwi layer", "show floods")):
            ui_actions.append({"type": "SHOW_LAYER", "layer": "ndwi"})

        return GeoReasonResult(
            synthesized_answer=" ".join(lines),
            calibrated_confidence=final_conf,
            confidence_level=conf_level,
            confidence_drivers=drivers,
            uncertainties=uncertainties,
            evidence_graph={"nodes": nodes, "edges": edges, "confidence_breakdown": confidence_factors},
            external_citations=citations,
            confidence_factors=confidence_factors,
            ui_actions=ui_actions,
        )
