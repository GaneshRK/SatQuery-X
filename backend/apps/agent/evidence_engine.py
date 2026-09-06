"""
SatQuery-X Evidence Engine
==========================

Transforms outputs from actual models/tools into a structured evidence
representation consumed by the reasoning and response layers.

This module is deliberately NON-GENERATIVE.

It never:
- invents measurements
- invents coordinates
- invents dates
- invents sensors
- invents CRS
- invents cloud percentages
- invents geographic areas
- invents confidence
- creates synthetic observations

It only organizes evidence already returned by upstream components.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping


ENGINE_VERSION = "3.0"

VALID_EVIDENCE_KINDS = {
    "observation",
    "measurement",
    "provenance",
    "validation",
    "limitation",
    "interpretation",
    "input",
}

SUCCESS_STATUSES = {
    "ok",
    "success",
    "completed",
    "done",
}

FAILURE_STATUSES = {
    "failed",
    "error",
    "unavailable",
}

KNOWN_MEASUREMENT_KEYS = {
    "mean_ndvi",
    "mean_ndwi",
    "mean_ndbi",
    "mean_nbr",
    "min_ndvi",
    "max_ndvi",
    "min_ndwi",
    "max_ndwi",
    "min_ndbi",
    "max_ndbi",
    "min_nbr",
    "max_nbr",

    "detected_change_km2",
    "detected_change_ha",
    "detected_change_pct",

    "built_up_area_km2",
    "built_up_pct",

    "vegetation_area_km2",
    "vegetation_pct",

    "dense_vegetation_km2",
    "sparse_vegetation_km2",

    "water_body_area_km2",
    "open_water_area_km2",
    "open_water_pct",

    "water_features_count",
    "structures_detected_count",

    "salt_pan_area_km2",
    "salt_pan_pct",

    "bare_soil_area_km2",
    "bare_soil_pct",

    "aoi_total_area_km2",
    "analysis_aoi_area_km2",
    "analysis_aoi_bbox_km2",

    "actual_raster_footprint_km2",
    "valid_cloud_free_area_km2",
    "valid_analytical_area_km2",
    "usable_analytical_area_pct",

    "scene_cloud_cover_pct",
    "aoi_cloud_cover_pct",
    "shadow_cover_pct",
    "haze_pct",
    "nodata_pct",

    "area_km2",
    "area_ha",

    "pixel_count",
    "valid_pixel_count",
    "changed_pixel_count",
    "total_pixel_count",

    "overlap_area_km2",
    "overlap_area_pct",

    "mean_temperature",
    "min_temperature",
    "max_temperature",
}


# ============================================================================
# Generic helpers
# ============================================================================


def _remove_none(value: Any) -> Any:
    """
    Remove None values recursively.

    This does not create replacement values.
    """

    if isinstance(value, Mapping):
        return {
            str(key): _remove_none(item)
            for key, item in value.items()
            if item is not None
        }

    if isinstance(value, list):
        return [
            _remove_none(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, tuple):
        return [
            _remove_none(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, float):
        if not math.isfinite(value):
            return None

    return value


def _as_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(result):
        return None

    return result


def _first_present(
    *values: Any,
) -> Any:
    for value in values:
        if value is not None:
            if isinstance(
                value,
                str,
            ):
                if value.strip():
                    return value
            else:
                return value

    return None


def _is_mapping(
    value: Any,
) -> bool:
    return isinstance(
        value,
        Mapping,
    )


def _feature_count(
    value: Any,
) -> int | None:
    if isinstance(
        value,
        list,
    ):
        return len(value)

    if isinstance(
        value,
        Mapping,
    ):
        features = value.get(
            "features"
        )

        if isinstance(
            features,
            list,
        ):
            return len(features)

    return None


# ============================================================================
# Evidence structures
# ============================================================================


@dataclass
class EvidenceItem:
    """
    One auditable evidence item.
    """

    id: str

    kind: str

    source: str | None = None

    description: str | None = None

    value: Any = None

    unit: str | None = None

    confidence: float | None = None

    spatial_reference: dict[str, Any] | None = None

    temporal_reference: dict[str, Any] | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return _remove_none(
            asdict(self)
        )


@dataclass
class StructuredEvidenceReport:
    """
    Structured evidence consumed by GeoReason and response composition.
    """

    observations: list[dict[str, Any]] = field(
        default_factory=list
    )

    measurements: dict[str, Any] = field(
        default_factory=dict
    )

    gis_measurements: dict[str, Any] = field(
        default_factory=dict
    )

    aoi_telemetry: dict[str, Any] = field(
        default_factory=dict
    )

    data_quality: dict[str, Any] = field(
        default_factory=dict
    )

    satellite_facts: list[dict[str, Any]] = field(
        default_factory=list
    )

    provenance: list[dict[str, Any]] = field(
        default_factory=list
    )

    confidence: float | None = None

    calibrated_confidence: float | None = None

    calibrated_confidence_pct: float | None = None

    confidence_factors: dict[str, Any] = field(
        default_factory=dict
    )

    limitations: list[str] = field(
        default_factory=list
    )

    validation: dict[str, Any] = field(
        default_factory=dict
    )

    evidence_items: list[dict[str, Any]] = field(
        default_factory=list
    )

    evidence_graph: dict[str, Any] = field(
        default_factory=dict
    )

    interpretations: list[dict[str, Any]] = field(
        default_factory=list
    )

    status: str = "partial"

    message: str | None = None

    query_text: str | None = None

    engine_version: str = ENGINE_VERSION

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return _remove_none(
            asdict(self)
        )

    def has_measurements(
        self,
    ) -> bool:
        return bool(
            self.measurements
            or self.gis_measurements
        )

    def has_observations(
        self,
    ) -> bool:
        return bool(
            self.observations
        )

    def has_provenance(
        self,
    ) -> bool:
        return bool(
            self.provenance
            or self.satellite_facts
        )

    def has_confidence(
        self,
    ) -> bool:
        return (
            self.confidence is not None
            or self.calibrated_confidence is not None
            or self.calibrated_confidence_pct is not None
        )

    def has_core_evidence(
        self,
    ) -> bool:
        return (
            self.has_observations()
            or self.has_measurements()
        )


# ============================================================================
# Evidence Engine
# ============================================================================


class EvidenceEngine:
    """
    Converts actual execution outputs into structured evidence.

    No scientific calculation occurs here.
    """

    VERSION = ENGINE_VERSION

    # =========================================================================
    # Public API
    # =========================================================================

    @classmethod
    def build_report(
        cls,
        execution_results: Mapping[str, Any] | None = None,
        input_context: Mapping[str, Any] | None = None,
        query_text: str | None = None,
        execution_trace: list[Mapping[str, Any]] | None = None,
    ) -> StructuredEvidenceReport:

        report = StructuredEvidenceReport(
            query_text=(
                str(query_text).strip()
                if query_text is not None
                and str(query_text).strip()
                else None
            )
        )

        results = dict(
            execution_results or {}
        )

        context = dict(
            input_context or {}
        )

        # --------------------------------------------------------------
        # Consume actual execution results.
        # --------------------------------------------------------------

        for source, raw_output in results.items():
            cls._consume_result(
                report=report,
                source=str(source),
                raw_output=raw_output,
                context=context,
            )

        # --------------------------------------------------------------
        # Preserve actual context.
        # --------------------------------------------------------------

        cls._collect_context(
            report=report,
            context=context,
        )

        # --------------------------------------------------------------
        # Preserve concise execution trace.
        # --------------------------------------------------------------

        if execution_trace:
            report.evidence_graph[
                "execution_trace"
            ] = [
                cls._sanitize_trace_item(
                    item
                )
                for item in execution_trace
                if isinstance(
                    item,
                    Mapping,
                )
            ]

        # --------------------------------------------------------------
        # Validate.
        # --------------------------------------------------------------

        report.validation = cls.validate_report(
            report
        )

        # --------------------------------------------------------------
        # Status.
        # --------------------------------------------------------------

        report.status = cls._determine_status(
            report
        )

        if not report.has_core_evidence():
            report.message = (
                "No directly usable observation or quantitative "
                "measurement was returned by the executed analysis."
            )

        return report

    @classmethod
    def generate_report(
        cls,
        execution_results: Mapping[str, Any] | None = None,
        input_context: Mapping[str, Any] | None = None,
        query_text: str | None = None,
        execution_trace: list[Mapping[str, Any]] | None = None,
    ) -> StructuredEvidenceReport:
        return cls.build_report(
            execution_results=execution_results,
            input_context=input_context,
            query_text=query_text,
            execution_trace=execution_trace,
        )

    @classmethod
    def create_report(
        cls,
        execution_results: Mapping[str, Any] | None = None,
        input_context: Mapping[str, Any] | None = None,
        query_text: str | None = None,
        execution_trace: list[Mapping[str, Any]] | None = None,
    ) -> StructuredEvidenceReport:
        return cls.build_report(
            execution_results=execution_results,
            input_context=input_context,
            query_text=query_text,
            execution_trace=execution_trace,
        )

    @classmethod
    def collect(
        cls,
        execution_results: Mapping[str, Any] | None = None,
        input_context: Mapping[str, Any] | None = None,
        query_text: str | None = None,
        execution_trace: list[Mapping[str, Any]] | None = None,
    ) -> StructuredEvidenceReport:
        return cls.build_report(
            execution_results=execution_results,
            input_context=input_context,
            query_text=query_text,
            execution_trace=execution_trace,
        )

    @classmethod
    def build_evidence_graph(
        cls,
        execution_results: Mapping[str, Any] | None = None,
        input_context: Mapping[str, Any] | None = None,
        execution_trace: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        report = cls.build_report(
            execution_results=execution_results,
            input_context=input_context,
            execution_trace=execution_trace,
        )

        return report.evidence_graph

    # =========================================================================
    # Validation
    # =========================================================================

    @classmethod
    def validate_report(
        cls,
        report: StructuredEvidenceReport,
    ) -> dict[str, Any]:

        issues: list[str] = []

        warnings: list[str] = []

        # --------------------------------------------------------------
        # Evidence items.
        # --------------------------------------------------------------

        for index, item in enumerate(
            report.evidence_items
        ):
            if not isinstance(
                item,
                Mapping,
            ):
                issues.append(
                    f"Evidence item {index} is not a mapping."
                )
                continue

            kind = item.get(
                "kind"
            )

            if kind not in VALID_EVIDENCE_KINDS:
                issues.append(
                    f"Evidence item {index} has unsupported kind "
                    f"'{kind}'."
                )

            if not item.get(
                "source"
            ):
                warnings.append(
                    f"Evidence item {index} has no source."
                )

        # --------------------------------------------------------------
        # Observations.
        # --------------------------------------------------------------

        for index, observation in enumerate(
            report.observations
        ):
            if not isinstance(
                observation,
                Mapping,
            ):
                issues.append(
                    f"Observation {index} is not a mapping."
                )
                continue

            description = _first_present(
                observation.get(
                    "observation"
                ),
                observation.get(
                    "description"
                ),
                observation.get(
                    "finding"
                ),
                observation.get(
                    "answer"
                ),
                observation.get(
                    "caption"
                ),
            )

            if description is None:
                warnings.append(
                    f"Observation {index} has no textual description."
                )

        # --------------------------------------------------------------
        # Measurements.
        # --------------------------------------------------------------

        for key, value in report.measurements.items():
            if value is None:
                issues.append(
                    f"Measurement '{key}' has a null value."
                )
                continue

            numeric = _as_float(
                value
            )

            if numeric is not None:
                if not math.isfinite(
                    numeric
                ):
                    issues.append(
                        f"Measurement '{key}' is not finite."
                    )

        for key, value in report.gis_measurements.items():
            if value is None:
                issues.append(
                    f"GIS measurement '{key}' has a null value."
                )

        # --------------------------------------------------------------
        # Confidence.
        # --------------------------------------------------------------

        for field_name in (
            "confidence",
            "calibrated_confidence",
        ):
            value = getattr(
                report,
                field_name,
            )

            if value is None:
                continue

            numeric = _as_float(
                value
            )

            if numeric is None:
                issues.append(
                    f"{field_name} is not numeric."
                )
            elif not 0.0 <= numeric <= 1.0:
                issues.append(
                    f"{field_name} is outside the expected 0-1 range."
                )

        if report.calibrated_confidence_pct is not None:
            numeric = _as_float(
                report.calibrated_confidence_pct
            )

            if numeric is None:
                issues.append(
                    "calibrated_confidence_pct is not numeric."
                )
            elif not 0.0 <= numeric <= 100.0:
                issues.append(
                    "calibrated_confidence_pct is outside the "
                    "expected 0-100 range."
                )

        # --------------------------------------------------------------
        # Duplicate evidence.
        # --------------------------------------------------------------

        duplicate_count = cls._count_duplicate_items(
            report.evidence_items
        )

        if duplicate_count:
            warnings.append(
                f"{duplicate_count} duplicate evidence item(s) "
                "were detected."
            )

        return {
            "valid": not issues,
            "issues": issues,
            "warnings": warnings,
            "evidence_count": len(
                report.evidence_items
            ),
            "observation_count": len(
                report.observations
            ),
            "measurement_count": len(
                report.measurements
            ),
            "gis_measurement_count": len(
                report.gis_measurements
            ),
            "provenance_count": (
                len(report.provenance)
                + len(report.satellite_facts)
            ),
            "interpretation_count": len(
                report.interpretations
            ),
            "limitation_count": len(
                report.limitations
            ),
        }

    @classmethod
    def validate(
        cls,
        report: StructuredEvidenceReport,
    ) -> dict[str, Any]:
        return cls.validate_report(
            report
        )

    # =========================================================================
    # Result ingestion
    # =========================================================================

    @classmethod
    def _consume_result(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        raw_output: Any,
        context: Mapping[str, Any],
    ) -> None:

        if raw_output is None:
            return

        raw_output = cls._normalize_output(
            raw_output
        )

        if isinstance(
            raw_output,
            str,
        ):
            text = raw_output.strip()

            if text:
                cls._add_observation(
                    report=report,
                    source=source,
                    description=text,
                )

            return

        if isinstance(
            raw_output,
            Mapping,
        ):
            cls._collect_mapping_result(
                report=report,
                source=source,
                result=dict(raw_output),
                context=context,
            )
            return

        if isinstance(
            raw_output,
            list,
        ):
            for index, item in enumerate(
                raw_output
            ):
                cls._consume_result(
                    report=report,
                    source=f"{source}[{index}]",
                    raw_output=item,
                    context=context,
                )

            return

        text = str(
            raw_output
        ).strip()

        if text:
            cls._add_observation(
                report=report,
                source=source,
                description=text,
            )

    @classmethod
    def _normalize_output(
        cls,
        value: Any,
    ) -> Any:

        if hasattr(
            value,
            "to_dict",
        ):
            try:
                converted = value.to_dict()

                if converted is not value:
                    return converted

            except Exception:
                pass

        if hasattr(
            value,
            "__dict__",
        ):
            try:
                return dict(
                    value.__dict__
                )
            except Exception:
                pass

        return value

    # =========================================================================
    # Mapping ingestion
    # =========================================================================

    @classmethod
    def _collect_mapping_result(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: dict[str, Any],
        context: Mapping[str, Any],
    ) -> None:

        clean_result = _remove_none(
            result
        )

        status = str(
            result.get(
                "status",
                "",
            )
        ).lower()

        # --------------------------------------------------------------
        # Failure information.
        # --------------------------------------------------------------

        if status in FAILURE_STATUSES:
            error = _first_present(
                result.get("error"),
                result.get("message"),
            )

            if error:
                cls._add_limitation(
                    report,
                    source,
                    str(error),
                )

        # --------------------------------------------------------------
        # Observations.
        # --------------------------------------------------------------

        observation_fields = (
            "observation",
            "observations",
            "finding",
            "findings",
            "answer",
            "caption",
            "description",
            "summary",
            "interpretation",
        )

        for key in observation_fields:
            if key not in result:
                continue

            value = result.get(
                key
            )

            if value is None:
                continue

            if key == "interpretation":
                cls._collect_interpretations(
                    report,
                    source,
                    value,
                )
                continue

            if isinstance(
                value,
                list,
            ):
                for item in value:
                    if isinstance(
                        item,
                        Mapping,
                    ):
                        text = _first_present(
                            item.get("observation"),
                            item.get("description"),
                            item.get("finding"),
                            item.get("text"),
                            item.get("label"),
                        )

                        if text:
                            cls._add_observation(
                                report=report,
                                source=source,
                                description=str(text),
                                spatial_reference=(
                                    item.get(
                                        "spatial_reference"
                                    )
                                ),
                                temporal_reference=(
                                    item.get(
                                        "temporal_reference"
                                    )
                                ),
                                metadata=item,
                            )

                    elif item is not None:
                        cls._add_observation(
                            report=report,
                            source=source,
                            description=str(item),
                        )

            elif isinstance(
                value,
                str,
            ):
                if value.strip():
                    cls._add_observation(
                        report=report,
                        source=source,
                        description=value,
                    )

        # --------------------------------------------------------------
        # Explicit measurements.
        # --------------------------------------------------------------

        cls._collect_measurements(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Spatial outputs.
        # --------------------------------------------------------------

        cls._collect_spatial_outputs(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Provenance.
        # --------------------------------------------------------------

        cls._collect_provenance(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Data quality.
        # --------------------------------------------------------------

        cls._collect_quality(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Confidence.
        # --------------------------------------------------------------

        cls._collect_confidence(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Limitations.
        # --------------------------------------------------------------

        cls._collect_limitations(
            report,
            source,
            result,
        )

        # --------------------------------------------------------------
        # Validation.
        # --------------------------------------------------------------

        validation = result.get(
            "validation"
        )

        if isinstance(
            validation,
            Mapping,
        ):
            report.validation.setdefault(
                "upstream",
                [],
            ).append(
                {
                    "source": source,
                    **_remove_none(
                        dict(validation)
                    ),
                }
            )

        # --------------------------------------------------------------
        # Generic evidence.
        # --------------------------------------------------------------

        evidence = result.get(
            "evidence"
        )

        if isinstance(
            evidence,
            list,
        ):
            for item in evidence:
                if isinstance(
                    item,
                    Mapping,
                ):
                    cls._add_evidence_item(
                        report=report,
                        kind=str(
                            item.get(
                                "kind",
                                "observation",
                            )
                        ),
                        source=str(
                            item.get(
                                "source",
                                source,
                            )
                        ),
                        description=item.get(
                            "description"
                        ),
                        value=item.get(
                            "value"
                        ),
                        unit=item.get(
                            "unit"
                        ),
                        confidence=_as_float(
                            item.get(
                                "confidence"
                            )
                        ),
                        spatial_reference=(
                            item.get(
                                "spatial_reference"
                            )
                        ),
                        temporal_reference=(
                            item.get(
                                "temporal_reference"
                            )
                        ),
                        metadata=item.get(
                            "metadata",
                            {},
                        ),
                    )

        # --------------------------------------------------------------
        # Graph source node.
        # --------------------------------------------------------------

        report.evidence_graph.setdefault(
            "sources",
            [],
        ).append(
            {
                "source": source,
                "status": status or None,
                "keys": sorted(
                    str(key)
                    for key in clean_result.keys()
                ),
            }
        )

    # =========================================================================
    # Measurements
    # =========================================================================

    @classmethod
    def _collect_measurements(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        measurement_mapping = result.get(
            "measurements"
        )

        if isinstance(
            measurement_mapping,
            Mapping,
        ):
            for key, value in measurement_mapping.items():
                if value is None:
                    continue

                report.measurements[
                    str(key)
                ] = value

                cls._add_evidence_item(
                    report=report,
                    kind="measurement",
                    source=source,
                    description=(
                        f"Measurement returned by {source}: "
                        f"{key}"
                    ),
                    value=value,
                    metadata={
                        "measurement_key": str(key),
                    },
                )

        gis_mapping = result.get(
            "gis_measurements"
        )

        if isinstance(
            gis_mapping,
            Mapping,
        ):
            for key, value in gis_mapping.items():
                if value is None:
                    continue

                report.gis_measurements[
                    str(key)
                ] = value

                cls._add_evidence_item(
                    report=report,
                    kind="measurement",
                    source=source,
                    description=(
                        f"GIS measurement returned by {source}: "
                        f"{key}"
                    ),
                    value=value,
                    metadata={
                        "measurement_key": str(key),
                        "category": "gis",
                    },
                )

        for key in KNOWN_MEASUREMENT_KEYS:
            if key not in result:
                continue

            value = result.get(
                key
            )

            if value is None:
                continue

            report.measurements[
                key
            ] = value

            cls._add_evidence_item(
                report=report,
                kind="measurement",
                source=source,
                description=(
                    f"Explicit measurement returned by {source}: "
                    f"{key}"
                ),
                value=value,
                metadata={
                    "measurement_key": key,
                },
            )

    # =========================================================================
    # Spatial outputs
    # =========================================================================

    @classmethod
    def _collect_spatial_outputs(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        spatial_keys = (
            "geometry",
            "geometries",
            "features",
            "geojson",
            "vector",
            "mask",
            "change_mask",
            "overlay",
            "boxes",
            "bbox",
            "bounds",
        )

        for key in spatial_keys:
            if key not in result:
                continue

            value = result.get(
                key
            )

            if value is None:
                continue

            record = {
                "source": source,
                "type": key,
                "available": True,
            }

            count = _feature_count(
                value
            )

            if count is not None:
                record[
                    "feature_count"
                ] = count

            report.evidence_graph.setdefault(
                "spatial_outputs",
                [],
            ).append(
                record
            )

    # =========================================================================
    # Provenance
    # =========================================================================

    @classmethod
    def _collect_provenance(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        provenance = result.get(
            "provenance"
        )

        if isinstance(
            provenance,
            Mapping,
        ):
            item = {
                "source": source,
                **dict(provenance),
            }

            report.provenance.append(
                _remove_none(item)
            )

        elif isinstance(
            provenance,
            list,
        ):
            for item in provenance:
                if isinstance(
                    item,
                    Mapping,
                ):
                    record = {
                        "source": source,
                        **dict(item),
                    }

                    report.provenance.append(
                        _remove_none(record)
                    )

        # --------------------------------------------------------------
        # Satellite facts.
        # --------------------------------------------------------------

        satellite_fields = (
            "sensor",
            "satellite",
            "platform",
            "mission",
            "acquisition_date",
            "observation_date",
            "scene_id",
            "product_id",
            "processing_level",
            "crs",
            "resolution_m",
        )

        facts = {}

        for key in satellite_fields:
            value = result.get(
                key
            )

            if value is not None:
                facts[key] = value

        if facts:
            facts["source"] = source

            report.satellite_facts.append(
                _remove_none(
                    facts
                )
            )

    # =========================================================================
    # Quality
    # =========================================================================

    @classmethod
    def _collect_quality(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        quality = result.get(
            "quality"
        )

        if isinstance(
            quality,
            Mapping,
        ):
            report.data_quality.update(
                {
                    str(key): value
                    for key, value in quality.items()
                    if value is not None
                }
            )

        quality_keys = (
            "cloud_cover_pct",
            "scene_cloud_cover_pct",
            "aoi_cloud_cover_pct",
            "shadow_cover_pct",
            "haze_pct",
            "nodata_pct",
            "usable_analytical_area_pct",
            "usable_clear_data_pct",
            "resolution_m",
            "crs",
            "is_georeferenced",
            "band_count",
            "dtype",
        )

        for key in quality_keys:
            if key not in result:
                continue

            value = result.get(
                key
            )

            if value is not None:
                report.data_quality[
                    key
                ] = value

    # =========================================================================
    # Confidence
    # =========================================================================

    @classmethod
    def _collect_confidence(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        confidence = _as_float(
            result.get(
                "confidence"
            )
        )

        if confidence is not None:
            if report.confidence is None:
                report.confidence = confidence

        calibrated = _as_float(
            result.get(
                "calibrated_confidence"
            )
        )

        if calibrated is not None:
            report.calibrated_confidence = (
                calibrated
            )

        calibrated_pct = _as_float(
            result.get(
                "calibrated_confidence_pct"
            )
        )

        if calibrated_pct is not None:
            report.calibrated_confidence_pct = (
                calibrated_pct
            )

        factors = result.get(
            "confidence_factors"
        )

        if isinstance(
            factors,
            Mapping,
        ):
            report.confidence_factors.update(
                {
                    str(key): value
                    for key, value in factors.items()
                    if value is not None
                }
            )

    # =========================================================================
    # Limitations
    # =========================================================================

    @classmethod
    def _collect_limitations(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        result: Mapping[str, Any],
    ) -> None:

        limitations = result.get(
            "limitations"
        )

        if isinstance(
            limitations,
            str,
        ):
            cls._add_limitation(
                report,
                source,
                limitations,
            )

        elif isinstance(
            limitations,
            list,
        ):
            for limitation in limitations:
                if limitation:
                    cls._add_limitation(
                        report,
                        source,
                        str(limitation),
                    )

        for key in (
            "warning",
            "warnings",
            "uncertainty",
            "uncertainties",
        ):
            value = result.get(
                key
            )

            if isinstance(
                value,
                str,
            ):
                cls._add_limitation(
                    report,
                    source,
                    value,
                )

            elif isinstance(
                value,
                list,
            ):
                for item in value:
                    if item:
                        cls._add_limitation(
                            report,
                            source,
                            str(item),
                        )

    @classmethod
    def _add_limitation(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        text: str,
    ) -> None:

        clean = str(
            text
        ).strip()

        if not clean:
            return

        if clean not in report.limitations:
            report.limitations.append(
                clean
            )

        cls._add_evidence_item(
            report=report,
            kind="limitation",
            source=source,
            description=clean,
        )

    # =========================================================================
    # Observations
    # =========================================================================

    @classmethod
    def _add_observation(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        description: str,
        spatial_reference: Mapping[str, Any] | None = None,
        temporal_reference: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:

        text = str(
            description
        ).strip()

        if not text:
            return

        observation = {
            "source": source,
            "observation": text,
        }

        if spatial_reference:
            observation[
                "spatial_reference"
            ] = dict(
                spatial_reference
            )

        if temporal_reference:
            observation[
                "temporal_reference"
            ] = dict(
                temporal_reference
            )

        if metadata:
            observation[
                "metadata"
            ] = dict(
                metadata
            )

        observation = _remove_none(
            observation
        )

        if observation in report.observations:
            return

        report.observations.append(
            observation
        )

        cls._add_evidence_item(
            report=report,
            kind="observation",
            source=source,
            description=text,
            spatial_reference=(
                dict(spatial_reference)
                if spatial_reference
                else None
            ),
            temporal_reference=(
                dict(temporal_reference)
                if temporal_reference
                else None
            ),
            metadata=(
                dict(metadata)
                if metadata
                else {}
            ),
        )

    # =========================================================================
    # Interpretations
    # =========================================================================

    @classmethod
    def _collect_interpretations(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        value: Any,
    ) -> None:

        if isinstance(
            value,
            str,
        ):
            cls._add_interpretation(
                report,
                source,
                value,
            )

            return

        if isinstance(
            value,
            list,
        ):
            for item in value:
                if isinstance(
                    item,
                    Mapping,
                ):
                    text = _first_present(
                        item.get("text"),
                        item.get("interpretation"),
                        item.get("description"),
                    )

                    if text:
                        cls._add_interpretation(
                            report,
                            source,
                            str(text),
                            item,
                        )

                elif item:
                    cls._add_interpretation(
                        report,
                        source,
                        str(item),
                    )

    @classmethod
    def _add_interpretation(
        cls,
        report: StructuredEvidenceReport,
        source: str,
        text: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:

        clean = str(
            text
        ).strip()

        if not clean:
            return

        item = {
            "source": source,
            "text": clean,
        }

        if metadata:
            item[
                "metadata"
            ] = dict(
                metadata
            )

        item = _remove_none(
            item
        )

        if item in report.interpretations:
            return

        report.interpretations.append(
            item
        )

        cls._add_evidence_item(
            report=report,
            kind="interpretation",
            source=source,
            description=clean,
            metadata=(
                dict(metadata)
                if metadata
                else {}
            ),
        )

    # =========================================================================
    # Evidence item
    # =========================================================================

    @classmethod
    def _add_evidence_item(
        cls,
        report: StructuredEvidenceReport,
        kind: str,
        source: str | None = None,
        description: str | None = None,
        value: Any = None,
        unit: str | None = None,
        confidence: float | None = None,
        spatial_reference: Mapping[str, Any] | None = None,
        temporal_reference: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:

        if kind not in VALID_EVIDENCE_KINDS:
            kind = "observation"

        item_id = (
            f"evidence_"
            f"{len(report.evidence_items) + 1}"
        )

        item = EvidenceItem(
            id=item_id,
            kind=kind,
            source=source,
            description=description,
            value=value,
            unit=unit,
            confidence=confidence,
            spatial_reference=(
                dict(spatial_reference)
                if spatial_reference
                else None
            ),
            temporal_reference=(
                dict(temporal_reference)
                if temporal_reference
                else None
            ),
            metadata=dict(
                metadata or {}
            ),
        )

        report.evidence_items.append(
            item.to_dict()
        )

    # =========================================================================
    # Context
    # =========================================================================

    @classmethod
    def _collect_context(
        cls,
        report: StructuredEvidenceReport,
        context: Mapping[str, Any],
    ) -> None:

        if not context:
            return

        spatial = cls._first_mapping(
            context.get(
                "spatial_context"
            ),
            context.get(
                "active_map_context"
            ),
            context.get(
                "map_context"
            ),
            context.get(
                "active_aoi"
            ),
        )

        if spatial:
            report.evidence_graph[
                "spatial_context"
            ] = _remove_none(
                spatial
            )

        temporal = cls._first_mapping(
            context.get(
                "time_range"
            ),
            context.get(
                "temporal_context"
            ),
        )

        if temporal:
            report.evidence_graph[
                "temporal_context"
            ] = _remove_none(
                temporal
            )

        assets = context.get(
            "image_assets"
        )

        if isinstance(
            assets,
            list,
        ) and assets:
            report.evidence_graph[
                "input_assets"
            ] = [
                _remove_none(
                    dict(asset)
                )
                if isinstance(
                    asset,
                    Mapping,
                )
                else {
                    "value": str(asset)
                }
                for asset in assets
            ]

        intent = context.get(
            "intent"
        )

        if isinstance(
            intent,
            Mapping,
        ):
            report.evidence_graph[
                "intent"
            ] = _remove_none(
                dict(intent)
            )

    # =========================================================================
    # Evidence graph
    # =========================================================================

    @classmethod
    def _determine_status(
        cls,
        report: StructuredEvidenceReport,
    ) -> str:

        if not report.has_core_evidence():
            return "insufficient_evidence"

        validation = report.validation

        if validation.get(
            "valid"
        ) is False:
            return "validation_warning"

        if report.has_measurements():
            return "complete"

        if report.has_observations():
            return "partial"

        return "insufficient_evidence"

    @staticmethod
    def _sanitize_trace_item(
        item: Mapping[str, Any],
    ) -> dict[str, Any]:

        allowed = (
            "step",
            "tool",
            "status",
            "latency_ms",
            "optional",
            "model_version",
        )

        return {
            key: item.get(key)
            for key in allowed
            if item.get(key) is not None
        }

    @staticmethod
    def _first_mapping(
        *values: Any,
    ) -> dict[str, Any] | None:

        for value in values:
            if isinstance(
                value,
                Mapping,
            ):
                if value:
                    return dict(value)

        return None

    @staticmethod
    def _count_duplicate_items(
        items: list[dict[str, Any]],
    ) -> int:

        seen: set[str] = set()

        duplicates = 0

        for item in items:
            normalized = repr(
                _remove_none(item)
            )

            if normalized in seen:
                duplicates += 1
            else:
                seen.add(
                    normalized
                )

        return duplicates


# ============================================================================
# Module-level compatibility helpers
# ============================================================================


def build_evidence_report(
    execution_results: Mapping[str, Any] | None = None,
    input_context: Mapping[str, Any] | None = None,
    query_text: str | None = None,
    execution_trace: list[Mapping[str, Any]] | None = None,
) -> StructuredEvidenceReport:

    return EvidenceEngine.build_report(
        execution_results=execution_results,
        input_context=input_context,
        query_text=query_text,
        execution_trace=execution_trace,
    )


def build_evidence_graph(
    execution_results: Mapping[str, Any] | None = None,
    input_context: Mapping[str, Any] | None = None,
    execution_trace: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:

    return EvidenceEngine.build_evidence_graph(
        execution_results=execution_results,
        input_context=input_context,
        execution_trace=execution_trace,
    )