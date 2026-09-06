"""
GeoReason Agent for SatQuery-X.

Purpose
-------
Fuse actual remote-sensing evidence, GIS measurements, temporal evidence,
validation results, and optional external corroboration into a conservative
geospatial interpretation.

Scientific integrity rules
--------------------------
1. Never fabricate a measurement.
2. Never assume Sentinel-1, Sentinel-2, Landsat, CRS, GSD, date, or sensor.
3. Never create confidence values from arbitrary constants.
4. Never claim a change when the evidence does not demonstrate it.
5. Never claim "no change" merely because no change result was returned.
6. External web evidence is corroboration/context, not replacement for raster
   evidence.
7. Do not inject location-specific facts unless supplied by an actual evidence
   source.
8. Do not expose chain-of-thought.
9. Only provide concise, auditable reasoning summaries.
10. Missing evidence must remain missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import logging
import math

logger = logging.getLogger(__name__)


# ============================================================================
# Data structures
# ============================================================================


@dataclass
class EvidenceNode:
    """
    Node in the auditable evidence graph.
    """

    id: str
    label: str
    node_type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.node_type,
            "metadata": _remove_none(self.metadata),
        }


@dataclass
class GeoReasonResult:
    """
    Result produced by GeoReasonAgent.

    `calibrated_confidence` is optional in practice. It is retained as a
    float for backward compatibility, but zero is NOT used to represent
    missing confidence. When confidence cannot be honestly established,
    `confidence_level` is LOW/UNKNOWN and the confidence metadata explains
    why.
    """

    synthesized_answer: str
    calibrated_confidence: float | None
    confidence_level: str
    confidence_drivers: list[str]
    uncertainties: list[str]
    evidence_graph: dict[str, Any]
    external_citations: list[dict[str, Any]]
    confidence_factors: list[dict[str, Any]] = field(
        default_factory=list
    )
    ui_actions: list[dict[str, Any]] = field(
        default_factory=list
    )


# ============================================================================
# GeoReason Agent
# ============================================================================


class GeoReasonAgent:
    """
    Conservative geospatial evidence reasoner.

    This component does not perform remote-sensing calculations itself.
    It interprets outputs already produced by analysis tools/models.

    It intentionally avoids:
        - hardcoded geographic facts,
        - hardcoded satellite identities,
        - arbitrary confidence weights,
        - arbitrary thresholds,
        - fabricated areas,
        - fabricated coordinates,
        - fabricated cloud percentages.
    """

    VERSION = "2.0"

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        query_text: str,
        aoi_name: str | None,
        satellite_scenes: list[dict[str, Any]] | None,
        measurements: dict[str, Any] | None,
        change_events: list[dict[str, Any]] | None,
        external_evidence: list[Any] | None,
        aoi_coords: list[float] | tuple[float, ...] | None = None,
        explanation_mode: str = "simple",
    ) -> GeoReasonResult:
        """
        Synthesize actual evidence into a concise geospatial interpretation.

        Parameters
        ----------
        query_text:
            Original user request.

        aoi_name:
            Resolved location/AOI name if known.

        satellite_scenes:
            Actual scene metadata returned by providers or uploaded imagery
            metadata.

        measurements:
            Actual GIS/spectral measurements.

        change_events:
            Actual change-analysis outputs.

        external_evidence:
            Optional web/knowledge corroboration.

        aoi_coords:
            Actual coordinates if resolved from map/geocoder/context.

        explanation_mode:
            Presentation mode. Supported values are informational only and
            do not alter scientific evidence.

        Returns
        -------
        GeoReasonResult
        """

        query = str(
            query_text or ""
        ).strip()

        area_name = (
            str(aoi_name).strip()
            if aoi_name
            else "the evaluated area"
        )

        scenes = [
            dict(scene)
            for scene in (satellite_scenes or [])
            if isinstance(scene, Mapping)
        ]

        metrics = dict(
            measurements or {}
        )

        changes = [
            dict(event)
            for event in (change_events or [])
            if isinstance(event, Mapping)
        ]

        external = list(
            external_evidence or []
        )

        drivers: list[str] = []
        uncertainties: list[str] = []
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        citations: list[dict[str, Any]] = []
        ui_actions: list[dict[str, Any]] = []

        # --------------------------------------------------------------
        # 1. Build scene evidence.
        # --------------------------------------------------------------

        scene_node_ids = self._add_scene_evidence(
            scenes=scenes,
            nodes=nodes,
            drivers=drivers,
            uncertainties=uncertainties,
        )

        # --------------------------------------------------------------
        # 2. Build measurement evidence.
        # --------------------------------------------------------------

        measurement_node_ids = self._add_measurement_evidence(
            measurements=metrics,
            nodes=nodes,
            drivers=drivers,
        )

        # --------------------------------------------------------------
        # 3. Build change evidence.
        # --------------------------------------------------------------

        change_info = self._add_change_evidence(
            changes=changes,
            nodes=nodes,
            edges=edges,
            scene_node_ids=scene_node_ids,
            drivers=drivers,
            uncertainties=uncertainties,
        )

        # --------------------------------------------------------------
        # 4. Add preprocessing/data-quality evidence.
        # --------------------------------------------------------------

        self._add_quality_evidence(
            measurements=metrics,
            nodes=nodes,
            edges=edges,
            scene_node_ids=scene_node_ids,
            drivers=drivers,
            uncertainties=uncertainties,
        )

        # --------------------------------------------------------------
        # 5. Add external corroboration.
        # --------------------------------------------------------------

        self._add_external_evidence(
            external_evidence=external,
            nodes=nodes,
            edges=edges,
            citations=citations,
            change_node_ids=change_info["node_ids"],
            drivers=drivers,
        )

        # --------------------------------------------------------------
        # 6. Determine confidence only from actual supplied evidence.
        # --------------------------------------------------------------

        confidence_result = self._assess_confidence(
            scenes=scenes,
            measurements=metrics,
            changes=changes,
            external_evidence=external,
            drivers=drivers,
            uncertainties=uncertainties,
        )

        # --------------------------------------------------------------
        # 7. Build evidence-grounded narrative.
        # --------------------------------------------------------------

        synthesized_answer = self._build_narrative(
            query_text=query,
            aoi_name=area_name,
            scenes=scenes,
            measurements=metrics,
            change_events=changes,
            external_evidence=external,
            explanation_mode=explanation_mode,
            uncertainties=uncertainties,
        )

        # --------------------------------------------------------------
        # 8. UI actions from explicit user request + actual evidence.
        # --------------------------------------------------------------

        ui_actions = self._build_ui_actions(
            query_text=query,
            aoi_coords=aoi_coords,
            changes=changes,
            measurements=metrics,
        )

        # --------------------------------------------------------------
        # 9. Evidence graph.
        # --------------------------------------------------------------

        evidence_graph = {
            "nodes": nodes,
            "edges": edges,
            "confidence_breakdown": confidence_result[
                "factors"
            ],
        }

        return GeoReasonResult(
            synthesized_answer=synthesized_answer,
            calibrated_confidence=confidence_result[
                "confidence"
            ],
            confidence_level=confidence_result[
                "level"
            ],
            confidence_drivers=drivers,
            uncertainties=uncertainties,
            evidence_graph=evidence_graph,
            external_citations=citations,
            confidence_factors=confidence_result[
                "factors"
            ],
            ui_actions=ui_actions,
        )

    # ------------------------------------------------------------------
    # Scene evidence
    # ------------------------------------------------------------------

    def _add_scene_evidence(
        self,
        scenes: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        drivers: list[str],
        uncertainties: list[str],
    ) -> list[str]:
        node_ids: list[str] = []

        if not scenes:
            uncertainties.append(
                "No satellite scene metadata was supplied to the "
                "geospatial reasoning stage."
            )
            return node_ids

        for index, scene in enumerate(scenes):
            external_id = _first_present(
                scene.get("external_id"),
                scene.get("scene_id"),
                scene.get("id"),
                scene.get("asset_id"),
            )

            node_id = (
                f"scene_{external_id}"
                if external_id is not None
                else f"scene_{index + 1}"
            )

            platform = _first_present(
                scene.get("platform"),
                scene.get("satellite"),
                scene.get("mission"),
            )

            sensor = _first_present(
                scene.get("sensor"),
                scene.get("instrument"),
                scene.get("instrument_name"),
            )

            acquisition_date = _first_present(
                scene.get("acquisition_date"),
                scene.get("date"),
                scene.get("datetime"),
                scene.get("timestamp"),
            )

            label_parts: list[str] = []

            if platform:
                label_parts.append(
                    str(platform)
                )

            if sensor:
                label_parts.append(
                    str(sensor)
                )

            if acquisition_date:
                label_parts.append(
                    str(acquisition_date)
                )

            label = (
                " | ".join(label_parts)
                if label_parts
                else f"Satellite observation {index + 1}"
            )

            metadata = self._scene_metadata(
                scene
            )

            nodes.append(
                EvidenceNode(
                    id=node_id,
                    label=label,
                    node_type="SATELLITE_SCENE",
                    metadata=metadata,
                ).to_dict()
            )

            node_ids.append(
                node_id
            )

            provenance_description = self._scene_description(
                scene
            )

            if provenance_description:
                drivers.append(
                    provenance_description
                )

        return node_ids

    # ------------------------------------------------------------------

    @staticmethod
    def _scene_metadata(
        scene: Mapping[str, Any],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}

        keys = (
            "external_id",
            "scene_id",
            "asset_id",
            "platform",
            "satellite",
            "mission",
            "sensor",
            "instrument",
            "acquisition_date",
            "date",
            "datetime",
            "timestamp",
            "cloud_cover",
            "cloud_cover_pct",
            "crs",
            "resolution_m",
            "gsd_m",
            "bounds",
            "geometry",
        )

        for key in keys:
            value = scene.get(key)

            if value is not None:
                metadata[key] = value

        return metadata

    # ------------------------------------------------------------------

    @staticmethod
    def _scene_description(
        scene: Mapping[str, Any],
    ) -> str | None:
        parts: list[str] = []

        platform = _first_present(
            scene.get("platform"),
            scene.get("satellite"),
            scene.get("mission"),
        )

        sensor = _first_present(
            scene.get("sensor"),
            scene.get("instrument"),
        )

        date = _first_present(
            scene.get("acquisition_date"),
            scene.get("date"),
            scene.get("datetime"),
        )

        if platform:
            parts.append(
                str(platform)
            )

        if sensor:
            parts.append(
                f"using {sensor}"
            )

        if date:
            parts.append(
                f"acquired on {date}"
            )

        if not parts:
            return None

        return (
            "Evidence includes an actual satellite observation "
            + " ".join(parts)
            + "."
        )

    # ------------------------------------------------------------------
    # Measurement evidence
    # ------------------------------------------------------------------

    def _add_measurement_evidence(
        self,
        measurements: dict[str, Any],
        nodes: list[dict[str, Any]],
        drivers: list[str],
    ) -> list[str]:
        node_ids: list[str] = []

        if not measurements:
            return node_ids

        for index, (key, value) in enumerate(
            measurements.items(),
            start=1,
        ):
            if value is None:
                continue

            if isinstance(value, Mapping):
                continue

            if isinstance(value, (list, tuple)):
                if not value:
                    continue

            node_id = (
                f"measurement_{index}"
            )

            label = _humanize_key(
                key
            )

            metadata = {
                "measurement_key": key,
                "value": value,
            }

            nodes.append(
                EvidenceNode(
                    id=node_id,
                    label=label,
                    node_type="MEASUREMENT",
                    metadata=metadata,
                ).to_dict()
            )

            node_ids.append(
                node_id
            )

            drivers.append(
                f"Measured evidence is available for {label}."
            )

        return node_ids

    # ------------------------------------------------------------------
    # Change evidence
    # ------------------------------------------------------------------

    def _add_change_evidence(
        self,
        changes: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        scene_node_ids: list[str],
        drivers: list[str],
        uncertainties: list[str],
    ) -> dict[str, Any]:
        node_ids: list[str] = []

        if not changes:
            return {
                "node_ids": node_ids,
                "has_change": False,
            }

        for index, event in enumerate(
            changes,
            start=1,
        ):
            node_id = (
                f"change_event_{index}"
            )

            node_ids.append(
                node_id
            )

            change_type = _first_present(
                event.get("change_type"),
                event.get("type"),
                event.get("class"),
                event.get("category"),
            )

            area = _first_present(
                event.get("area_hectares"),
                event.get("area_ha"),
                event.get("area_km2"),
                event.get("detected_change_km2"),
            )

            description = _first_present(
                event.get("description"),
                event.get("summary"),
                event.get("observation"),
            )

            metadata = dict(event)

            nodes.append(
                EvidenceNode(
                    id=node_id,
                    label=(
                        str(change_type)
                        if change_type
                        else "Detected change event"
                    ),
                    node_type="CHANGE_EVENT",
                    metadata=metadata,
                ).to_dict()
            )

            # ----------------------------------------------------------
            # Never say "confirmed" merely because an event dictionary
            # exists. Use explicit status if available.
            # ----------------------------------------------------------

            status = _first_present(
                event.get("status"),
                event.get("validation_status"),
                event.get("verification_status"),
            )

            if status:
                drivers.append(
                    f"Change analysis returned an event with "
                    f"status '{status}'."
                )
            else:
                drivers.append(
                    "Change analysis returned a localized change event."
                )

            if change_type:
                drivers.append(
                    f"Reported change category: {change_type}."
                )

            if area is not None:
                unit = (
                    "ha"
                    if event.get("area_hectares") is not None
                    or event.get("area_ha") is not None
                    else "km²"
                )

                drivers.append(
                    "Reported change extent: "
                    f"{_format_number(area)} {unit}."
                )

            if description:
                drivers.append(
                    str(description)
                )

            # ----------------------------------------------------------
            # Link the change event to actual scenes when available.
            # ----------------------------------------------------------

            for scene_node_id in scene_node_ids:
                edges.append(
                    {
                        "from": scene_node_id,
                        "to": node_id,
                        "relation": "SUPPORTS_CHANGE_ANALYSIS",
                    }
                )

            # ----------------------------------------------------------
            # Explicit geometry evidence.
            # ----------------------------------------------------------

            geometry = _first_present(
                event.get("geometry"),
                event.get("geojson"),
                event.get("polygon"),
                event.get("features"),
            )

            if geometry is not None:
                geometry_node_id = (
                    f"{node_id}_geometry"
                )

                nodes.append(
                    EvidenceNode(
                        id=geometry_node_id,
                        label="Change geometry",
                        node_type="VECTOR_POLYGON",
                        metadata={
                            "geometry": geometry,
                        },
                    ).to_dict()
                )

                edges.append(
                    {
                        "from": node_id,
                        "to": geometry_node_id,
                        "relation": "HAS_SPATIAL_GEOMETRY",
                    }
                )

            if status is not None and str(status).lower() in {
                "failed",
                "invalid",
                "unverified",
            }:
                uncertainties.append(
                    "The returned change event is not fully validated."
                )

        return {
            "node_ids": node_ids,
            "has_change": True,
        }

    # ------------------------------------------------------------------
    # Quality evidence
    # ------------------------------------------------------------------

    def _add_quality_evidence(
        self,
        measurements: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        scene_node_ids: list[str],
        drivers: list[str],
        uncertainties: list[str],
    ) -> None:
        quality = measurements.get(
            "data_quality"
        )

        if not isinstance(quality, Mapping):
            quality = measurements.get(
                "quality"
            )

        if isinstance(quality, Mapping):
            quality_dict = dict(
                quality
            )

            quality_node = EvidenceNode(
                id="data_quality",
                label="Data quality assessment",
                node_type="DATA_QUALITY",
                metadata=quality_dict,
            )

            nodes.append(
                quality_node.to_dict()
            )

            for scene_id in scene_node_ids:
                edges.append(
                    {
                        "from": scene_id,
                        "to": "data_quality",
                        "relation": "ASSESSED_FOR_QUALITY",
                    }
                )

            for key, value in quality_dict.items():
                if value is None:
                    continue

                drivers.append(
                    f"Data-quality evidence includes "
                    f"{_humanize_key(key)}: {value}."
                )

        noise_cleaning = measurements.get(
            "noise_cleaning"
        )

        if isinstance(noise_cleaning, Mapping):
            methods = noise_cleaning.get(
                "cleaning_methods_applied"
            )

            if isinstance(methods, list) and methods:
                method_text = ", ".join(
                    str(method)
                    for method in methods
                )

                drivers.append(
                    "Preprocessing metadata reports the following "
                    f"methods: {method_text}."
                )

            usable = noise_cleaning.get(
                "usable_clear_data_pct"
            )

            if usable is not None:
                drivers.append(
                    "Preprocessing reported usable-data coverage of "
                    f"{usable}%."
                )

            node = EvidenceNode(
                id="preprocessing",
                label="Image preprocessing",
                node_type="DATA_PREPROCESSING",
                metadata=dict(
                    noise_cleaning
                ),
            )

            nodes.append(
                node.to_dict()
            )

            for scene_id in scene_node_ids:
                edges.append(
                    {
                        "from": scene_id,
                        "to": "preprocessing",
                        "relation": "PROCESSED_BY",
                    }
                )

        # --------------------------------------------------------------
        # Do not infer cloud-free usability from missing cloud metadata.
        # --------------------------------------------------------------

        if scene_node_ids:
            cloud_values = []

            for scene in measurements.get(
                "satellite_scenes",
                [],
            ) if isinstance(
                measurements.get("satellite_scenes"),
                list,
            ) else []:
                if not isinstance(scene, Mapping):
                    continue

                cloud = _first_present(
                    scene.get("cloud_cover_pct"),
                    scene.get("cloud_cover"),
                )

                numeric = _as_float(
                    cloud
                )

                if numeric is not None:
                    cloud_values.append(
                        numeric
                    )

            if not cloud_values:
                uncertainties.append(
                    "Cloud-cover metadata was not available for "
                    "the quality assessment."
                )

    # ------------------------------------------------------------------
    # External evidence
    # ------------------------------------------------------------------

    def _add_external_evidence(
        self,
        external_evidence: list[Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        citations: list[dict[str, Any]],
        change_node_ids: list[str],
        drivers: list[str],
    ) -> None:
        if not external_evidence:
            return

        for index, evidence in enumerate(
            external_evidence,
            start=1,
        ):
            data = self._external_to_dict(
                evidence
            )

            if not data:
                continue

            source_domain = _first_present(
                data.get("source_domain"),
                data.get("domain"),
                data.get("source_url"),
            )

            publisher = _first_present(
                data.get("publisher"),
                data.get("organization"),
                data.get("source"),
            )

            title = data.get(
                "title"
            )

            node_id = (
                f"external_source_{index}"
            )

            label_parts = []

            if publisher:
                label_parts.append(
                    str(publisher)
                )

            if source_domain:
                label_parts.append(
                    str(source_domain)
                )

            label = (
                " — ".join(label_parts)
                if label_parts
                else "External evidence source"
            )

            nodes.append(
                EvidenceNode(
                    id=node_id,
                    label=label,
                    node_type="EXTERNAL_SOURCE",
                    metadata={
                        "title": title,
                        "source_url": data.get(
                            "source_url"
                        ),
                        "trust_tier": data.get(
                            "trust_tier"
                        ),
                        "trust_score": data.get(
                            "trust_score"
                        ),
                    },
                ).to_dict()
            )

            citation = {
                key: value
                for key, value in {
                    "publisher": publisher,
                    "title": title,
                    "source_url": data.get(
                        "source_url"
                    ),
                    "trust_tier": data.get(
                        "trust_tier"
                    ),
                    "trust_score": data.get(
                        "trust_score"
                    ),
                    "facts": data.get(
                        "summary_facts"
                    ),
                }.items()
                if value is not None
            }

            if citation:
                citations.append(
                    citation
                )

            facts = data.get(
                "summary_facts"
            )

            if isinstance(facts, list):
                for fact in facts:
                    if fact:
                        drivers.append(
                            "External source reports: "
                            f"{fact}"
                        )

            elif facts:
                drivers.append(
                    "External source reports: "
                    f"{facts}"
                )

            # External evidence is linked as corroboration only.
            for change_node_id in change_node_ids:
                edges.append(
                    {
                        "from": change_node_id,
                        "to": node_id,
                        "relation": "CORROBORATED_BY",
                    }
                )

    # ------------------------------------------------------------------

    @staticmethod
    def _external_to_dict(
        evidence: Any,
    ) -> dict[str, Any]:
        if evidence is None:
            return {}

        if isinstance(
            evidence,
            Mapping,
        ):
            return dict(
                evidence
            )

        if hasattr(
            evidence,
            "to_dict",
        ):
            try:
                value = evidence.to_dict()

                if isinstance(
                    value,
                    Mapping,
                ):
                    return dict(
                        value
                    )
            except Exception:
                logger.debug(
                    "Unable to serialize external evidence.",
                    exc_info=True,
                )

        result: dict[str, Any] = {}

        for field_name in (
            "publisher",
            "title",
            "source_url",
            "source_domain",
            "trust_tier",
            "trust_score",
            "summary_facts",
        ):
            if hasattr(
                evidence,
                field_name,
            ):
                value = getattr(
                    evidence,
                    field_name,
                )

                if value is not None:
                    result[field_name] = value

        return result

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _assess_confidence(
        self,
        scenes: list[dict[str, Any]],
        measurements: dict[str, Any],
        changes: list[dict[str, Any]],
        external_evidence: list[Any],
        drivers: list[str],
        uncertainties: list[str],
    ) -> dict[str, Any]:
        """
        Assess confidence from explicit upstream confidence evidence.

        IMPORTANT:
        This method does NOT manufacture a confidence score using arbitrary
        weights.

        If upstream tools/models supply explicit confidence values, they are
        summarized. Otherwise confidence remains None.
        """

        explicit_confidences: list[float] = []

        # --------------------------------------------------------------
        # Scene-level confidence.
        # --------------------------------------------------------------

        for scene in scenes:
            for key in (
                "confidence",
                "quality_score",
                "validation_score",
            ):
                value = _as_float(
                    scene.get(key)
                )

                if value is None:
                    continue

                normalized = _normalize_confidence(
                    value
                )

                if normalized is not None:
                    explicit_confidences.append(
                        normalized
                    )

        # --------------------------------------------------------------
        # Measurement-level confidence.
        # --------------------------------------------------------------

        for key in (
            "confidence",
            "model_confidence",
            "validation_score",
            "evidence_score",
        ):
            value = _as_float(
                measurements.get(key)
            )

            if value is None:
                continue

            normalized = _normalize_confidence(
                value
            )

            if normalized is not None:
                explicit_confidences.append(
                    normalized
                )

        # --------------------------------------------------------------
        # Change-level confidence.
        # --------------------------------------------------------------

        for event in changes:
            for key in (
                "confidence",
                "model_confidence",
                "validation_score",
                "evidence_score",
            ):
                value = _as_float(
                    event.get(key)
                )

                if value is None:
                    continue

                normalized = _normalize_confidence(
                    value
                )

                if normalized is not None:
                    explicit_confidences.append(
                        normalized
                    )

        # --------------------------------------------------------------
        # External confidence/trust is NOT silently converted into model
        # confidence. It is represented as a separate factor.
        # --------------------------------------------------------------

        external_scores: list[float] = []

        for evidence in external_evidence:
            data = self._external_to_dict(
                evidence
            )

            value = _as_float(
                data.get("trust_score")
            )

            if value is not None:
                normalized = _normalize_confidence(
                    value
                )

                if normalized is not None:
                    external_scores.append(
                        normalized
                    )

        factors: list[dict[str, Any]] = []

        if explicit_confidences:
            mean_confidence = (
                sum(explicit_confidences)
                / len(explicit_confidences)
            )

            factors.append(
                {
                    "name": "upstream_confidence",
                    "score": round(
                        mean_confidence,
                        4,
                    ),
                    "basis": (
                        "Explicit confidence values supplied by "
                        "upstream evidence-producing components."
                    ),
                }
            )

            drivers.append(
                "Confidence was inherited from explicit upstream "
                "evidence rather than generated locally."
            )

        else:
            uncertainties.append(
                "No explicit upstream confidence score was supplied; "
                "a numeric confidence value was not generated."
            )

        if external_scores:
            mean_external = (
                sum(external_scores)
                / len(external_scores)
            )

            factors.append(
                {
                    "name": "external_source_trust",
                    "score": round(
                        mean_external,
                        4,
                    ),
                    "basis": (
                        "Trust scores reported by external evidence "
                        "sources; not treated as raster confidence."
                    ),
                }
            )

        # --------------------------------------------------------------
        # Determine qualitative level without pretending that it is a
        # statistical probability.
        # --------------------------------------------------------------

        if explicit_confidences:
            mean_confidence = (
                sum(explicit_confidences)
                / len(explicit_confidences)
            )

            if mean_confidence >= 0.85:
                level = "HIGH"
            elif mean_confidence >= 0.70:
                level = "MODERATE"
            else:
                level = "LOW"

            confidence = round(
                mean_confidence,
                4,
            )

        else:
            confidence = None
            level = "UNKNOWN"

        # --------------------------------------------------------------
        # Evidence availability is described separately from confidence.
        # --------------------------------------------------------------

        if scenes:
            factors.append(
                {
                    "name": "scene_evidence",
                    "available": True,
                    "count": len(scenes),
                }
            )

        if changes:
            factors.append(
                {
                    "name": "change_evidence",
                    "available": True,
                    "count": len(changes),
                }
            )

        if measurements:
            factors.append(
                {
                    "name": "measurement_evidence",
                    "available": True,
                    "count": len(measurements),
                }
            )

        if not scenes and not measurements and not changes:
            uncertainties.append(
                "The reasoning stage received no direct raster-derived "
                "scene, measurement, or change evidence."
            )

        return {
            "confidence": confidence,
            "level": level,
            "factors": factors,
        }

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------

    def _build_narrative(
        self,
        query_text: str,
        aoi_name: str,
        scenes: list[dict[str, Any]],
        measurements: dict[str, Any],
        change_events: list[dict[str, Any]],
        external_evidence: list[Any],
        explanation_mode: str,
        uncertainties: list[str],
    ) -> str:
        """
        Build a conservative natural-language synthesis.

        This method only describes evidence that exists. It does not infer
        geographic facts from the AOI name.
        """

        query_lower = query_text.lower()

        sentences: list[str] = []

        is_fusion_query = self._is_fusion_query(
            query_lower
        )

        is_change_query = self._is_change_query(
            query_lower
        )

        # --------------------------------------------------------------
        # Cross-modal interpretation.
        # --------------------------------------------------------------

        if is_fusion_query:
            if measurements or scenes:
                sentences.append(
                    f"The available evidence supports a cross-modal "
                    f"optical/SAR analysis for {aoi_name}."
                )

                if measurements:
                    sentences.append(
                        "The interpretation is based on the "
                        "measurements returned by the executed "
                        "analysis rather than on assumed sensor behavior."
                    )
            else:
                sentences.append(
                    f"A cross-modal optical/SAR request was identified "
                    f"for {aoi_name}, but the required analysis evidence "
                    "is not available in the current execution result."
                )

        # --------------------------------------------------------------
        # Change interpretation.
        # --------------------------------------------------------------

        elif change_events:
            sentences.append(
                f"The executed change-analysis workflow returned "
                f"{len(change_events)} change event"
                f"{'s' if len(change_events) != 1 else ''} "
                f"for {aoi_name}."
            )

            for event in change_events[:3]:
                event_sentence = self._change_sentence(
                    event
                )

                if event_sentence:
                    sentences.append(
                        event_sentence
                    )

        elif is_change_query:
            sentences.append(
                f"The request concerns change in {aoi_name}, but "
                "the available execution evidence does not contain "
                "a validated change result."
            )

        # --------------------------------------------------------------
        # Measurement interpretation.
        # --------------------------------------------------------------

        measurement_sentences = (
            self._measurement_sentences(
                measurements
            )
        )

        sentences.extend(
            measurement_sentences
        )

        # --------------------------------------------------------------
        # Generic observation.
        # --------------------------------------------------------------

        if not sentences:
            if scenes:
                sentences.append(
                    f"The available satellite observation evidence "
                    f"for {aoi_name} was processed successfully."
                )
            else:
                sentences.append(
                    f"The available evidence for {aoi_name} is "
                    "insufficient to make a grounded geospatial "
                    "interpretation."
                )

        # --------------------------------------------------------------
        # External evidence.
        # --------------------------------------------------------------

        external_sentence = (
            self._external_sentence(
                external_evidence
            )
        )

        if external_sentence:
            sentences.append(
                external_sentence
            )

        # --------------------------------------------------------------
        # Limitations.
        # --------------------------------------------------------------

        if uncertainties:
            sentences.append(
                "Important limitation: "
                + uncertainties[0]
            )

        return " ".join(
            sentence.strip()
            for sentence in sentences
            if sentence and sentence.strip()
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _change_sentence(
        event: Mapping[str, Any],
    ) -> str | None:
        change_type = _first_present(
            event.get("change_type"),
            event.get("type"),
            event.get("class"),
            event.get("category"),
        )

        area_ha = _first_present(
            event.get("area_hectares"),
            event.get("area_ha"),
        )

        area_km2 = _first_present(
            event.get("area_km2"),
            event.get("detected_change_km2"),
        )

        if change_type and area_ha is not None:
            return (
                f"The reported change category is "
                f"{change_type}, with an extent of "
                f"{_format_number(area_ha)} ha."
            )

        if change_type and area_km2 is not None:
            return (
                f"The reported change category is "
                f"{change_type}, with an extent of "
                f"{_format_number(area_km2)} km²."
            )

        if change_type:
            return (
                f"The reported change category is "
                f"{change_type}."
            )

        if area_ha is not None:
            return (
                "The change result includes a reported extent of "
                f"{_format_number(area_ha)} ha."
            )

        if area_km2 is not None:
            return (
                "The change result includes a reported extent of "
                f"{_format_number(area_km2)} km²."
            )

        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _measurement_sentences(
        measurements: Mapping[str, Any],
    ) -> list[str]:
        sentences: list[str] = []

        interesting_keys = (
            "mean_ndvi",
            "mean_ndwi",
            "mean_ndbi",
            "mean_nbr",
            "vegetation_area_km2",
            "built_up_area_km2",
            "water_body_area_km2",
            "open_water_area_km2",
            "detected_change_km2",
            "structures_detected_count",
            "water_features_count",
        )

        for key in interesting_keys:
            value = measurements.get(
                key
            )

            if value is None:
                continue

            label = _humanize_key(
                key
            )

            unit = _measurement_unit(
                key
            )

            if unit:
                sentences.append(
                    f"{label} was measured as "
                    f"{_format_number(value)} {unit}."
                )
            else:
                sentences.append(
                    f"{label} was measured as "
                    f"{_format_number(value)}."
                )

        return sentences[:5]

    # ------------------------------------------------------------------

    @staticmethod
    def _external_sentence(
        external_evidence: list[Any],
    ) -> str | None:
        if not external_evidence:
            return None

        source_names: list[str] = []

        for evidence in external_evidence:
            if isinstance(
                evidence,
                Mapping,
            ):
                name = _first_present(
                    evidence.get("publisher"),
                    evidence.get("source"),
                    evidence.get("source_domain"),
                )
            else:
                name = _first_present(
                    getattr(
                        evidence,
                        "publisher",
                        None,
                    ),
                    getattr(
                        evidence,
                        "source_domain",
                        None,
                    ),
                )

            if name:
                source_names.append(
                    str(name)
                )

        if not source_names:
            return (
                "External evidence was available as contextual "
                "corroboration."
            )

        unique_names = list(
            dict.fromkeys(
                source_names
            )
        )

        return (
            "External sources were used only as contextual "
            "corroboration: "
            + ", ".join(unique_names)
            + "."
        )

    # ------------------------------------------------------------------
    # Query interpretation
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fusion_query(
        query_lower: str,
    ) -> bool:
        optical = (
            "optical" in query_lower
            or "multispectral" in query_lower
            or "multispectral" in query_lower
        )

        sar = (
            "sar" in query_lower
            or "radar" in query_lower
        )

        fusion = any(
            term in query_lower
            for term in (
                "fusion",
                "cross-modal",
                "cross modal",
                "dual-pol",
                "dual polarization",
            )
        )

        return (
            optical and sar
        ) or fusion

    # ------------------------------------------------------------------

    @staticmethod
    def _is_change_query(
        query_lower: str,
    ) -> bool:
        return any(
            term in query_lower
            for term in (
                "change",
                "changed",
                "difference",
                "compare over time",
                "before and after",
                "before-after",
                "temporal",
                "loss",
                "gain",
                "expansion",
                "decline",
                "increase",
                "decrease",
                "flooding",
                "deforestation",
            )
        )

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

    @staticmethod
    def _build_ui_actions(
        query_text: str,
        aoi_coords: list[float] | tuple[float, ...] | None,
        changes: list[dict[str, Any]],
        measurements: dict[str, Any],
    ) -> list[dict[str, Any]]:
        query_lower = query_text.lower()

        actions: list[dict[str, Any]] = []

        wants_location = any(
            term in query_lower
            for term in (
                "where",
                "locate",
                "show me",
                "zoom",
                "exact location",
                "on the map",
            )
        )

        if (
            wants_location
            and aoi_coords
            and len(aoi_coords) >= 2
        ):
            actions.append(
                {
                    "type": "ZOOM_TO_REGION",
                    "coordinates": list(
                        aoi_coords[:2]
                    ),
                }
            )

        if changes and any(
            term in query_lower
            for term in (
                "change",
                "changed",
                "show",
                "where",
                "map",
                "locate",
            )
        ):
            actions.append(
                {
                    "type": "SHOW_LAYER",
                    "layer": "change_mask",
                }
            )

        if any(
            term in query_lower
            for term in (
                "vegetation map",
                "ndvi layer",
                "show vegetation",
                "vegetation layer",
            )
        ):
            if (
                "mean_ndvi" in measurements
                or "vegetation_area_km2" in measurements
            ):
                actions.append(
                    {
                        "type": "SHOW_LAYER",
                        "layer": "ndvi",
                    }
                )

        if any(
            term in query_lower
            for term in (
                "water map",
                "ndwi layer",
                "show water",
                "water layer",
            )
        ):
            if (
                "water_body_area_km2"
                in measurements
                or "open_water_area_km2"
                in measurements
            ):
                actions.append(
                    {
                        "type": "SHOW_LAYER",
                        "layer": "ndwi",
                    }
                )

        return actions

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(
        self,
        result: GeoReasonResult,
    ) -> dict[str, Any]:
        """
        Convert GeoReasonResult into a JSON-safe dictionary.
        """

        return {
            "synthesized_answer": result.synthesized_answer,
            "calibrated_confidence": result.calibrated_confidence,
            "confidence_level": result.confidence_level,
            "confidence_drivers": result.confidence_drivers,
            "uncertainties": result.uncertainties,
            "evidence_graph": result.evidence_graph,
            "external_citations": result.external_citations,
            "confidence_factors": result.confidence_factors,
            "ui_actions": result.ui_actions,
        }


# ============================================================================
# Compatibility helpers
# ============================================================================


def synthesize_geo_reasoning(
    query_text: str,
    aoi_name: str | None,
    satellite_scenes: list[dict[str, Any]] | None,
    measurements: dict[str, Any] | None,
    change_events: list[dict[str, Any]] | None,
    external_evidence: list[Any] | None,
    aoi_coords: list[float] | tuple[float, ...] | None = None,
    explanation_mode: str = "simple",
) -> GeoReasonResult:
    """
    Module-level compatibility wrapper.
    """

    return GeoReasonAgent().synthesize(
        query_text=query_text,
        aoi_name=aoi_name,
        satellite_scenes=satellite_scenes,
        measurements=measurements,
        change_events=change_events,
        external_evidence=external_evidence,
        aoi_coords=aoi_coords,
        explanation_mode=explanation_mode,
    )


# ============================================================================
# Private utility functions
# ============================================================================


def _first_present(
    *values: Any,
) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(
            value,
            str,
        ) and not value.strip():
            continue

        return value

    return None


def _as_float(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if isinstance(
        value,
        (int, float),
    ):
        number = float(
            value
        )

        if math.isfinite(number):
            return number

        return None

    if isinstance(
        value,
        str,
    ):
        try:
            number = float(
                value.strip()
            )

            if math.isfinite(number):
                return number

        except (
            TypeError,
            ValueError,
        ):
            return None

    return None


def _normalize_confidence(
    value: float,
) -> float | None:
    """
    Normalize an explicit confidence value.

    Accepted forms:
        0..1   -> probability-style confidence
        0..100 -> percentage-style confidence

    Values outside those ranges are rejected rather than clamped.
    """

    if not math.isfinite(
        value
    ):
        return None

    if 0.0 <= value <= 1.0:
        return value

    if 0.0 <= value <= 100.0:
        return value / 100.0

    return None


def _format_number(
    value: Any,
) -> str:
    numeric = _as_float(
        value
    )

    if numeric is None:
        return str(
            value
        )

    if numeric.is_integer():
        return f"{int(numeric):,}"

    return (
        f"{numeric:,.3f}"
        .rstrip("0")
        .rstrip(".")
    )


def _measurement_unit(
    key: str,
) -> str | None:
    if key.endswith(
        "_km2"
    ):
        return "km²"

    if key.endswith(
        "_ha"
    ):
        return "ha"

    if key.endswith(
        "_pct"
    ):
        return "%"

    return None


def _humanize_key(
    key: str,
) -> str:
    return (
        str(key)
        .replace(
            "_",
            " ",
        )
        .strip()
        .capitalize()
    )


def _remove_none(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Mapping,
    ):
        return {
            key: _remove_none(item)
            for key, item in value.items()
            if item is not None
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _remove_none(item)
            for item in value
            if item is not None
        ]

    if isinstance(
        value,
        tuple,
    ):
        return [
            _remove_none(item)
            for item in value
            if item is not None
        ]

    return value