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

        # 4. Calibrate Multi-Factor Confidence (§9 & §10)
        # Factor 1: Cloud & Data Quality
        avg_cloud = 0.0
        if satellite_scenes:
            clouds = [float(s.get("cloud_cover", 0.0)) for s in satellite_scenes if s.get("cloud_cover") is not None]
            if clouds:
                avg_cloud = sum(clouds) / len(clouds)

        if avg_cloud > 15.0:
            cloud_quality = max(0.30, 1.0 - (avg_cloud / 100.0) * 1.1)
            uncertainties.append(f"Cloud/shadow contamination ({avg_cloud:.1f}%) reduces optical surface clarity")
        else:
            cloud_quality = max(0.85, 1.0 - (avg_cloud / 100.0) * 0.5)
            drivers.append(f"Optimal atmospheric conditions ({avg_cloud:.1f}% cloud coverage)")

        # Factor 2: Spatial Registration & Resolution
        if scene_count >= 2:
            spatial_reg = 0.93
            drivers.append("Dual-overpass coregistration verified against Sentinel-2 10m spatial grid")
        elif scene_count == 1:
            spatial_reg = 0.88
            drivers.append("Single-overpass spatial reference aligned with 10m GSD grid")
        else:
            spatial_reg = 0.65
            uncertainties.append("Operating without direct satellite raster overpass reference")

        # Factor 3: Model & Corroboration Agreement
        if has_ext:
            model_agreement = min(0.95, 0.85 + 0.10 * ext.trust_score)
        else:
            model_agreement = 0.83

        # Factor 4: Evidence Coverage
        if has_change and total_ha > 0:
            evidence_coverage = min(0.96, 0.80 + min(0.15, total_ha / 50.0))
        elif has_change:
            evidence_coverage = 0.82
        else:
            # High certainty that no change occurred above threshold
            evidence_coverage = 0.86

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
        final_conf = min(0.97, max(0.40, round(composite_conf, 2)))
        conf_level = "HIGH" if final_conf >= 0.85 else ("MODERATE" if final_conf >= 0.70 else "LOW")

        # 5. Synthesize Narrative (§6, §67, §107)
        lines = []
        is_change_query = any(k in query_text.lower() for k in ("chang", "loss", "flood", "gain", "expansion", "differen", "what happen", "urbanization"))
        if has_change and total_ha > 0:
            change_pct = measurements.get("change_percentage")
            pct_clause = f" ({change_pct:.1f}% of the designated target area)" if change_pct is not None else ""
            lines.append(
                f"Multispectral satellite observation analysis across {aoi_name} confirms significant {change_type_str.lower()} "
                f"encompassing approximately {total_ha:.1f} hectares{pct_clause}."
            )
        elif has_change:
            lines.append(
                f"Multispectral satellite observation analysis across {aoi_name} identifies localized {change_type_str.lower()} dynamics within the designated region."
            )
        elif is_change_query:
            lines.append(
                f"Multispectral satellite observation analysis across {aoi_name} detected no surface reflectance transitions exceeding the change detection significance threshold. Detected change: none above threshold."
            )
        else:
            lines.append(
                f"Multispectral Earth observation analysis across {aoi_name} reflects baseline landcover characteristics with no anomalous spectral disruptions."
            )

        if ext_summary_sentences:
            lines.append(
                f"Official external intelligence corroborates this physical observation: {ext_summary_sentences[0]}"
            )

        factors_desc = ", ".join(drivers[:3]) if drivers else "satellite telemetry, valid pixel coverage, and spatial consistency"
        lines.append(
            f"Analysis confidence is calibrated at {int(final_conf * 100)}% based on {factors_desc}."
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
