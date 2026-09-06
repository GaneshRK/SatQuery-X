"""
Response Engine for SatQuery-X.

Purpose
-------
Convert persisted execution evidence into a human-readable answer without
inventing measurements, provenance, confidence, coordinates, sensor metadata,
or scientific conclusions.

Design principles
-----------------
1. Never manufacture numeric values.
2. Never assume a satellite, CRS, resolution, date, or cloud percentage.
3. Never convert missing measurements into zero.
4. Distinguish observations, measurements, interpretations, and limitations.
5. Confidence is shown only when produced upstream.
6. The response engine does not perform scientific analysis.
7. Comparison differences are derived only from explicitly supplied numeric
   measurements.
8. Identical observations are reported only when upstream evidence explicitly
   establishes identity.
9. No chain-of-thought is exposed.
10. Execution traces contain only concise auditable actions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ResponseEngine:
    """
    Evidence-grounded response composer.

    Presentation logic only.

    This class must never:
    - calculate remote-sensing indices,
    - estimate geographic areas,
    - invent satellite metadata,
    - infer coordinates,
    - fabricate confidence,
    - create missing observations,
    - or replace unavailable evidence with assumptions.
    """

    VERSION = "3.0"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def compose(
        cls,
        query_text: str,
        base_answer: str | None = None,
        evidence: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        execution_trace: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        """
        Compose a grounded user-facing answer.

        `base_answer` is accepted for compatibility with specialist model
        outputs. It is rendered as supplied and is not scientifically
        expanded or supplemented with invented claims.
        """

        evidence_dict = dict(evidence or {})
        context_dict = dict(context or {})

        sections: list[str] = []

        answer = cls._clean_text(base_answer)

        if answer:
            sections.append(answer)

        observation_section = cls._format_observations(
            evidence_dict
        )

        if observation_section:
            sections.append(observation_section)

        interpretation_section = cls._format_interpretations(
            evidence_dict
        )

        if interpretation_section:
            sections.append(interpretation_section)

        measurement_section = cls._format_measurements(
            evidence_dict
        )

        if measurement_section:
            sections.append(measurement_section)

        provenance_section = cls._format_provenance(
            evidence_dict
        )

        if provenance_section:
            sections.append(provenance_section)

        confidence_section = cls._format_confidence(
            evidence_dict
        )

        if confidence_section:
            sections.append(confidence_section)

        spatial_section = cls._format_spatial_context(
            context_dict
        )

        if spatial_section:
            sections.append(spatial_section)

        limitation_section = cls._format_limitations(
            evidence=evidence_dict,
            context=context_dict,
        )

        if limitation_section:
            sections.append(limitation_section)

        trace_section = cls._format_execution_trace(
            execution_trace
        )

        if trace_section:
            sections.append(trace_section)

        if not sections:
            return (
                "I could not produce a grounded answer from the available "
                "analysis evidence. The required observation or analysis "
                "output is not available."
            )

        return "\n\n".join(
            section.strip()
            for section in sections
            if section and section.strip()
        ).strip()

    # ------------------------------------------------------------------
    # Structured report support
    # ------------------------------------------------------------------

    @classmethod
    def compose_from_report(
        cls,
        query_text: str,
        report: Any,
        base_answer: str | None = None,
        context: Mapping[str, Any] | None = None,
        execution_trace: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        """
        Compose directly from a StructuredEvidenceReport-like object.
        """

        evidence = cls._report_to_dict(report)

        return cls.compose(
            query_text=query_text,
            base_answer=base_answer,
            evidence=evidence,
            context=context,
            execution_trace=execution_trace,
        )

    # ------------------------------------------------------------------
    # Backward-compatible API
    # ------------------------------------------------------------------

    @classmethod
    def format_grounded_answer(
        cls,
        base_answer: str,
        report: Any,
        location_name: str | None = None,
        intent_target: str | None = None,
        is_temporal: bool = False,
    ) -> str:
        """
        Backward-compatible formatter for StructuredEvidenceReport-like
        objects.

        No scientific defaults are inserted.
        """

        evidence = cls._report_to_dict(report)

        context: dict[str, Any] = {}

        if location_name:
            context["location_name"] = location_name

        if intent_target:
            context["intent_target"] = intent_target

        context["is_temporal"] = bool(is_temporal)

        return cls.compose(
            query_text="",
            base_answer=base_answer,
            evidence=evidence,
            context=context,
        )

    # ------------------------------------------------------------------

    @classmethod
    def format_comparison_answer(
        cls,
        loc_a: Mapping[str, Any] | None,
        loc_b: Mapping[str, Any] | None,
        metrics_a: Mapping[str, Any] | None = None,
        metrics_b: Mapping[str, Any] | None = None,
        target: str = "general",
        comparison_mode: str = "MODE_A_DESCRIPTIVE",
    ) -> str:
        """
        Format an evidence-backed comparison.

        Only values actually supplied by upstream analysis are displayed.

        Numeric differences are calculated only when both values are present
        and numerically comparable.

        No percentage change is invented.
        """

        location_a = dict(loc_a or {})
        location_b = dict(loc_b or {})

        measurements_a = dict(metrics_a or {})
        measurements_b = dict(metrics_b or {})

        # --------------------------------------------------------------
        # Explicit identical-observation result
        # --------------------------------------------------------------

        if cls._explicitly_identical(
            location_a,
            location_b,
            measurements_a,
            measurements_b,
        ):
            name_a = cls._location_name(
                location_a,
                "Observation A",
            )

            name_b = cls._location_name(
                location_b,
                "Observation B",
            )

            return (
                "### Comparison Result\n\n"
                f"The supplied observations for **{name_a}** and "
                f"**{name_b}** are identical at the evidence level "
                "reported by the analysis pipeline. There is no meaningful "
                "difference to report from those supplied observations."
            )

        name_a = cls._location_name(
            location_a,
            "Region A",
        )

        name_b = cls._location_name(
            location_b,
            "Region B",
        )

        mode_title = cls._comparison_mode_title(
            comparison_mode
        )

        sections: list[str] = [
            "### Comparative Earth Observation Analysis",
            f"**Comparison:** {name_a} vs {name_b}",
            f"**Mode:** {mode_title}",
        ]

        # --------------------------------------------------------------
        # Spatial context
        # --------------------------------------------------------------

        spatial_rows: list[tuple[str, str, str]] = []

        admin_a = cls._first_present(
            location_a.get("canonical_name"),
            location_a.get("administrative_region"),
            location_a.get("name"),
        )

        admin_b = cls._first_present(
            location_b.get("canonical_name"),
            location_b.get("administrative_region"),
            location_b.get("name"),
        )

        if admin_a is not None or admin_b is not None:
            spatial_rows.append(
                (
                    "Administrative Region",
                    cls._display_optional(admin_a),
                    cls._display_optional(admin_b),
                )
            )

        coords_a = cls._first_present(
            location_a.get("coords"),
            location_a.get("coordinates"),
            location_a.get("centroid"),
        )

        coords_b = cls._first_present(
            location_b.get("coords"),
            location_b.get("coordinates"),
            location_b.get("centroid"),
        )

        if coords_a is not None or coords_b is not None:
            spatial_rows.append(
                (
                    "Geographic Center",
                    cls._format_coordinate_value(coords_a),
                    cls._format_coordinate_value(coords_b),
                )
            )

        area_a = cls._first_present(
            measurements_a.get("aoi_total_area_km2"),
            measurements_a.get("analysis_aoi_area_km2"),
        )

        area_b = cls._first_present(
            measurements_b.get("aoi_total_area_km2"),
            measurements_b.get("analysis_aoi_area_km2"),
        )

        if area_a is not None or area_b is not None:
            spatial_rows.append(
                (
                    "AOI Area",
                    cls._format_measurement(
                        area_a,
                        "km²",
                    ),
                    cls._format_measurement(
                        area_b,
                        "km²",
                    ),
                )
            )

        valid_area_a = cls._first_present(
            measurements_a.get("valid_cloud_free_area_km2"),
            measurements_a.get("valid_analytical_area_km2"),
        )

        valid_area_b = cls._first_present(
            measurements_b.get("valid_cloud_free_area_km2"),
            measurements_b.get("valid_analytical_area_km2"),
        )

        if valid_area_a is not None or valid_area_b is not None:
            spatial_rows.append(
                (
                    "Valid Analytical Area",
                    cls._format_measurement(
                        valid_area_a,
                        "km²",
                    ),
                    cls._format_measurement(
                        valid_area_b,
                        "km²",
                    ),
                )
            )

        if spatial_rows:
            sections.append(
                cls._comparison_table(
                    "#### Spatial Context",
                    name_a,
                    name_b,
                    spatial_rows,
                )
            )

        # --------------------------------------------------------------
        # Quantitative measurements
        # --------------------------------------------------------------

        metric_specs = [
            (
                "Built-Up / Infrastructure",
                "built_up_area_km2",
                "built_up_pct",
            ),
            (
                "Vegetation",
                "vegetation_area_km2",
                "vegetation_pct",
            ),
            (
                "Open Surface Water",
                "open_water_area_km2",
                "open_water_pct",
            ),
            (
                "Water Body",
                "water_body_area_km2",
                "water_body_pct",
            ),
            (
                "Salt Pan / Evaporation Flats",
                "salt_pan_area_km2",
                "salt_pan_pct",
            ),
            (
                "Bare Soil / Sediment",
                "bare_soil_area_km2",
                "bare_soil_pct",
            ),
            (
                "Detected Surface Change",
                "detected_change_km2",
                "detected_change_pct",
            ),
            (
                "Detected Surface Change",
                "detected_change_ha",
                "detected_change_pct",
            ),
            (
                "Mean NDVI",
                "mean_ndvi",
                None,
            ),
            (
                "Detected Structures",
                "structures_detected_count",
                None,
            ),
            (
                "Detected Water Features",
                "water_features_count",
                None,
            ),
        ]

        metric_rows: list[
            tuple[str, str, str, str]
        ] = []

        seen_labels: set[str] = set()

        for label, value_key, percentage_key in metric_specs:

            if label in seen_labels:
                continue

            value_a = measurements_a.get(value_key)
            value_b = measurements_b.get(value_key)

            percentage_a = (
                measurements_a.get(percentage_key)
                if percentage_key
                else None
            )

            percentage_b = (
                measurements_b.get(percentage_key)
                if percentage_key
                else None
            )

            if value_a is None and value_b is None:
                continue

            seen_labels.add(label)

            value_text_a = cls._metric_value_with_percentage(
                value_a,
                percentage_a,
                value_key,
            )

            value_text_b = cls._metric_value_with_percentage(
                value_b,
                percentage_b,
                value_key,
            )

            difference = cls._numeric_difference(
                value_a,
                value_b,
            )

            if difference is None:
                comparison = (
                    "Not comparable from the supplied evidence."
                )
            else:
                comparison = cls._format_difference(
                    difference=difference,
                    name_a=name_a,
                    name_b=name_b,
                    unit=cls._metric_unit(value_key),
                )

            metric_rows.append(
                (
                    label,
                    value_text_a,
                    value_text_b,
                    comparison,
                )
            )

        if metric_rows:
            sections.append(
                cls._comparison_metric_table(
                    title="#### Evidence-Derived Measurements",
                    name_a=name_a,
                    name_b=name_b,
                    rows=metric_rows,
                )
            )
        else:
            sections.append(
                "#### Evidence-Derived Measurements\n"
                "No directly comparable quantitative measurements "
                "were supplied for these observations."
            )

        # --------------------------------------------------------------
        # Explicit interpretations
        # --------------------------------------------------------------

        interpretations = cls._collect_comparison_interpretations(
            measurements_a,
            measurements_b,
        )

        if interpretations:
            sections.append(
                "#### Interpretation\n"
                + "\n".join(
                    f"• {item}"
                    for item in interpretations
                )
            )

        # --------------------------------------------------------------
        # Provenance
        # --------------------------------------------------------------

        provenance = cls._comparison_provenance(
            measurements_a,
            measurements_b,
        )

        if provenance:
            sections.append(provenance)

        # --------------------------------------------------------------
        # Confidence
        # --------------------------------------------------------------

        confidence = cls._comparison_confidence(
            measurements_a,
            measurements_b,
        )

        if confidence:
            sections.append(confidence)

        # --------------------------------------------------------------
        # Limitations
        # --------------------------------------------------------------

        limitations = cls._comparison_limitations(
            measurements_a,
            measurements_b,
        )

        if limitations:
            sections.append(limitations)

        return "\n\n".join(
            section
            for section in sections
            if section
        ).strip()

    # ------------------------------------------------------------------

    @classmethod
    def generate_contextual_follow_ups(
        cls,
        intent_name: str,
        location_name: str | None,
        metrics: Mapping[str, Any] | None,
    ) -> list[str]:
        """
        Generate follow-up suggestions based only on available evidence.

        No suggestion claims that a result exists when the evidence is
        absent.
        """

        measurements = dict(metrics or {})

        location = cls._first_present(
            location_name,
            "this area",
        )

        suggestions: list[str] = []

        # --------------------------------------------------------------
        # Change evidence
        # --------------------------------------------------------------

        if cls._contains_any(
            measurements,
            (
                "detected_change_km2",
                "detected_change_ha",
                "detected_change_pct",
                "change_mask",
                "change_features",
                "change_events",
            ),
        ):
            suggestions.extend(
                [
                    (
                        f"Show the detected change boundaries for "
                        f"{location} on the map."
                    ),
                    (
                        f"Explain the detected changes between the "
                        f"available observations of {location}."
                    ),
                ]
            )

        # --------------------------------------------------------------
        # Vegetation evidence
        # --------------------------------------------------------------

        if cls._contains_any(
            measurements,
            (
                "mean_ndvi",
                "vegetation_area_km2",
                "vegetation_pct",
                "dense_vegetation_km2",
                "sparse_vegetation_km2",
            ),
        ):
            suggestions.extend(
                [
                    (
                        f"Show the vegetation evidence for {location} "
                        "on the map."
                    ),
                    (
                        f"Compare the supplied vegetation indicators "
                        f"for {location}."
                    ),
                ]
            )

        # --------------------------------------------------------------
        # Water evidence
        # --------------------------------------------------------------

        if cls._contains_any(
            measurements,
            (
                "water_body_area_km2",
                "open_water_area_km2",
                "water_features_count",
            ),
        ):
            suggestions.extend(
                [
                    (
                        f"Show the detected water extent in "
                        f"{location}."
                    ),
                    (
                        f"Compare the supplied water observations "
                        f"for {location}."
                    ),
                ]
            )

        # --------------------------------------------------------------
        # Urban / structure evidence
        # --------------------------------------------------------------

        if cls._contains_any(
            measurements,
            (
                "built_up_area_km2",
                "built_up_pct",
                "structures_detected_count",
            ),
        ):
            suggestions.extend(
                [
                    (
                        f"Show the detected infrastructure or "
                        f"structures in {location}."
                    ),
                    (
                        f"Compare the supplied built-up indicators "
                        f"for {location}."
                    ),
                ]
            )

        # --------------------------------------------------------------
        # Generic evidence-backed suggestions
        # --------------------------------------------------------------

        if not suggestions:

            if intent_name:
                suggestions.append(
                    (
                        f"Show the available evidence for "
                        f"{location} on the map."
                    )
                )

            suggestions.append(
                (
                    f"Describe the available analysis evidence "
                    f"for {location}."
                )
            )

        # Preserve order while removing duplicates.
        result: list[str] = []

        for suggestion in suggestions:
            if suggestion not in result:
                result.append(suggestion)

        return result[:4]

    # ------------------------------------------------------------------
    # Observation formatting
    # ------------------------------------------------------------------

    @classmethod
    def _format_observations(
        cls,
        evidence: Mapping[str, Any],
    ) -> str | None:

        observations = cls._first_present(
            evidence.get("observations"),
            evidence.get("observation"),
            evidence.get("findings"),
        )

        if observations is None:
            return None

        if isinstance(observations, str):
            text = cls._clean_text(observations)

            if not text:
                return None

            return (
                "#### Evidence-Based Observation\n"
                f"{text}"
            )

        if isinstance(observations, Mapping):
            observations = [observations]

        if not isinstance(observations, Sequence):
            return None

        bullets: list[str] = []

        for item in observations:

            if isinstance(item, str):
                text = cls._clean_text(item)

                if text:
                    bullets.append(f"• {text}")

                continue

            if not isinstance(item, Mapping):
                continue

            text = cls._observation_text(item)

            if text:
                bullets.append(f"• {text}")

        if not bullets:
            return None

        return (
            "#### Evidence-Based Observations\n"
            + "\n".join(bullets)
        )

    # ------------------------------------------------------------------

    @classmethod
    def _format_interpretations(
        cls,
        evidence: Mapping[str, Any],
    ) -> str | None:

        interpretations = evidence.get("interpretations")

        if interpretations is None:
            interpretations = evidence.get("interpretation")

        if interpretations is None:
            return None

        if isinstance(interpretations, str):
            text = cls._clean_text(interpretations)

            if not text:
                return None

            return (
                "#### Interpretation\n"
                f"• {text}"
            )

        if isinstance(interpretations, Mapping):
            interpretations = [interpretations]

        if not isinstance(interpretations, Sequence):
            return None

        bullets: list[str] = []

        for item in interpretations:

            if isinstance(item, Mapping):
                text = cls._first_present(
                    item.get("interpretation"),
                    item.get("description"),
                    item.get("text"),
                    item.get("finding"),
                )
            else:
                text = item

            text = cls._clean_text(text)

            if text:
                bullets.append(f"• {text}")

        if not bullets:
            return None

        return (
            "#### Interpretation\n"
            + "\n".join(bullets)
        )

    # ------------------------------------------------------------------
    # Measurement formatting
    # ------------------------------------------------------------------

    @classmethod
    def _format_measurements(
        cls,
        evidence: Mapping[str, Any],
    ) -> str | None:

        measurements = evidence.get("measurements")

        if not isinstance(measurements, Mapping):
            measurements = evidence.get("gis_measurements")

        if not isinstance(measurements, Mapping):
            return None

        rows: list[tuple[str, str]] = []

        ignored_keys = {
            "aoi_telemetry",
            "data_quality",
            "confidence_factors",
            "provenance",
            "satellite_facts",
            "limitations",
        }

        for key, value in measurements.items():

            if key in ignored_keys:
                continue

            if value is None:
                continue

            label = cls._measurement_label(
                str(key)
            )

            formatted = cls._format_generic_measurement(
                str(key),
                value,
            )

            if formatted is None:
                continue

            rows.append(
                (
                    label,
                    formatted,
                )
            )

        if not rows:
            return None

        lines = [
            "#### Quantitative Measurements",
            "| Measurement | Value |",
            "| :--- | :--- |",
        ]

        for label, value in rows:
            lines.append(
                f"| {cls._escape_table(label)} | "
                f"{cls._escape_table(value)} |"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @classmethod
    def _measurement_label(
        cls,
        key: str,
    ) -> str:

        display_names = {
            "detected_change_km2": "Surface change extent",
            "detected_change_ha": "Surface change extent",
            "detected_change_pct": "Detected change proportion",
            "built_up_area_km2": "Built-up / infrastructure area",
            "built_up_pct": "Built-up / infrastructure proportion",
            "structures_detected_count": "Detected structure candidates",
            "vegetation_area_km2": "Vegetation area",
            "vegetation_pct": "Vegetation proportion",
            "dense_vegetation_km2": "Dense vegetation area",
            "sparse_vegetation_km2": "Sparse vegetation area",
            "mean_ndvi": "Mean NDVI",
            "water_body_area_km2": "Water-body area",
            "open_water_area_km2": "Open surface-water area",
            "water_features_count": "Detected water features",
            "salt_pan_area_km2": "Salt-pan / evaporation-flat area",
            "bare_soil_area_km2": "Bare-soil / sediment area",
            "aoi_total_area_km2": "AOI area",
            "valid_cloud_free_area_km2": "Valid analytical area",
        }

        return display_names.get(
            key,
            cls._humanize_key(key),
        )

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    @classmethod
    def _format_provenance(
        cls,
        evidence: Mapping[str, Any],
    ) -> str | None:

        facts = cls._first_present(
            evidence.get("satellite_facts"),
            evidence.get("provenance"),
            evidence.get("observations_metadata"),
        )

        if isinstance(facts, Mapping):
            facts = [facts]

        if not isinstance(facts, Sequence):
            return None

        rows: list[str] = []

        for fact in facts:

            if not isinstance(fact, Mapping):
                continue

            fields: list[str] = []

            role = fact.get("observation_role")
            sensor = fact.get("sensor")
            platform = fact.get("platform")

            date = cls._first_present(
                fact.get("acquisition_date"),
                fact.get("date"),
                fact.get("timestamp"),
            )

            cloud = fact.get("cloud_cover_pct")

            resolution = cls._first_present(
                fact.get("resolution_m"),
                fact.get("gsd_m"),
            )

            crs = fact.get("crs")

            source = cls._first_present(
                fact.get("source"),
                fact.get("provider"),
                fact.get("filename"),
            )

            if role is not None:
                fields.append(
                    f"Role: {role}"
                )

            if sensor is not None:
                fields.append(
                    f"Sensor: {sensor}"
                )

            if platform is not None:
                fields.append(
                    f"Platform: {platform}"
                )

            if date is not None:
                fields.append(
                    f"Acquisition: {date}"
                )

            if cloud is not None:
                fields.append(
                    f"Cloud cover: {cls._format_number(cloud)}%"
                )

            if resolution is not None:
                fields.append(
                    f"GSD: {cls._format_number(resolution)} m"
                )

            if crs is not None:
                fields.append(
                    f"CRS: {crs}"
                )

            if source is not None:
                fields.append(
                    f"Source: {source}"
                )

            if fields:
                rows.append(
                    "• " + " | ".join(fields)
                )

        if not rows:
            return None

        return (
            "#### Observation Provenance\n"
            + "\n".join(rows)
        )

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    @classmethod
    def _format_confidence(
        cls,
        evidence: Mapping[str, Any],
    ) -> str | None:

        confidence = cls._first_present(
            evidence.get("calibrated_confidence"),
            evidence.get("confidence"),
            evidence.get("calibrated_confidence_pct"),
        )

        factors = evidence.get(
            "confidence_factors"
        )

        if confidence is None and not isinstance(
            factors,
            Mapping,
        ):
            return None

        lines = [
            "#### Reliability"
        ]

        if confidence is not None:

            formatted = cls._format_confidence_value(
                confidence,
                key_hint=(
                    "calibrated_confidence_pct"
                    if evidence.get("calibrated_confidence_pct")
                    == confidence
                    else None
                ),
            )

            if formatted:
                lines.append(
                    f"• **Reported confidence:** {formatted}"
                )

        if isinstance(factors, Mapping):

            factor_labels = {
                "model_confidence": "Model confidence",
                "cloud_factor": "Atmospheric/data-quality factor",
                "coregistration_score": "Coregistration score",
                "evidence_score": "Evidence score",
                "validation_score": "Validation score",
            }

            factor_lines: list[str] = []

            for key, label in factor_labels.items():

                value = factors.get(key)

                if value is None:
                    continue

                factor_lines.append(
                    f"{label}: {cls._format_factor(value)}"
                )

            if factor_lines:
                lines.append(
                    "• **Reported factors:** "
                    + "; ".join(factor_lines)
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Spatial context
    # ------------------------------------------------------------------

    @classmethod
    def _format_spatial_context(
        cls,
        context: Mapping[str, Any],
    ) -> str | None:

        spatial = cls._first_present(
            context.get("spatial_context"),
            context.get("active_map_context"),
            context.get("map_context"),
        )

        if not isinstance(spatial, Mapping):
            return None

        fields: list[str] = []

        location_name = cls._first_present(
            spatial.get("location_name"),
            spatial.get("resolved_location"),
            spatial.get("canonical_name"),
        )

        if location_name:
            fields.append(
                f"Resolved location: {location_name}"
            )

        pin = cls._first_present(
            spatial.get("map_pin"),
            spatial.get("pin"),
            spatial.get("active_pin"),
        )

        if isinstance(pin, Mapping):

            coordinates = cls._first_present(
                pin.get("coordinates"),
                pin.get("coords"),
                pin.get("latlon"),
            )

            if coordinates is not None:
                fields.append(
                    "Active map pin: "
                    + cls._format_coordinate_value(
                        coordinates
                    )
                )

        elif pin is not None:

            fields.append(
                "Active map pin: "
                + cls._format_coordinate_value(pin)
            )

        aoi = cls._first_present(
            spatial.get("aoi"),
            spatial.get("active_aoi"),
            spatial.get("selected_aoi"),
        )

        if isinstance(aoi, Mapping):

            geometry_type = aoi.get("type")

            if geometry_type:
                fields.append(
                    f"Active AOI geometry: {geometry_type}"
                )

            crs = aoi.get("crs")

            if crs:
                fields.append(
                    f"AOI CRS: {crs}"
                )

        if not fields:
            return None

        return (
            "#### Spatial Context\n"
            + "\n".join(
                f"• {field}"
                for field in fields
            )
        )

    # ------------------------------------------------------------------
    # Limitations
    # ------------------------------------------------------------------

    @classmethod
    def _format_limitations(
        cls,
        evidence: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str | None:

        limitations = cls._first_present(
            evidence.get("limitations"),
            evidence.get("limitations_notes"),
            context.get("limitations"),
        )

        if limitations is None:
            return None

        if isinstance(limitations, str):

            text = cls._clean_text(limitations)

            if not text:
                return None

            return (
                "#### Analysis Limitations\n"
                f"• {text}"
            )

        if isinstance(limitations, Mapping):
            limitations = list(
                limitations.values()
            )

        if not isinstance(limitations, Sequence):
            return None

        bullets: list[str] = []

        for item in limitations:

            if isinstance(item, Mapping):
                text = cls._first_present(
                    item.get("message"),
                    item.get("reason"),
                    item.get("description"),
                )
            else:
                text = item

            text = cls._clean_text(text)

            if text:
                bullets.append(
                    f"• {text}"
                )

        if not bullets:
            return None

        return (
            "#### Analysis Limitations\n"
            + "\n".join(bullets)
        )

    # ------------------------------------------------------------------
    # Execution trace
    # ------------------------------------------------------------------

    @classmethod
    def _format_execution_trace(
        cls,
        trace: Sequence[Mapping[str, Any]] | None,
    ) -> str | None:
        """
        Show only concise auditable actions.

        Internal reasoning, hidden planning details, prompts, model chains,
        and chain-of-thought are intentionally excluded.
        """

        if not trace:
            return None

        lines: list[str] = []

        for item in trace:

            if not isinstance(item, Mapping):
                continue

            tool = cls._first_present(
                item.get("tool_name"),
                item.get("tool"),
                item.get("name"),
            )

            status = item.get("status")

            if not tool:
                continue

            if status:
                lines.append(
                    f"• {tool}: {status}"
                )
            else:
                lines.append(
                    f"• {tool}"
                )

        if not lines:
            return None

        return (
            "#### Analysis Trace\n"
            + "\n".join(lines)
        )

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    @classmethod
    def _comparison_table(
        cls,
        title: str,
        name_a: str,
        name_b: str,
        rows: Sequence[
            tuple[str, Any, Any]
        ],
    ) -> str:

        lines = [
            title,
            "| Attribute | "
            f"{cls._escape_table(name_a)} | "
            f"{cls._escape_table(name_b)} |",
            "| :--- | :--- | :--- |",
        ]

        for label, value_a, value_b in rows:

            lines.append(
                f"| {cls._escape_table(label)} | "
                f"{cls._escape_table(str(value_a))} | "
                f"{cls._escape_table(str(value_b))} |"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @classmethod
    def _comparison_metric_table(
        cls,
        title: str,
        name_a: str,
        name_b: str,
        rows: Sequence[
            tuple[str, str, str, str]
        ],
    ) -> str:

        lines = [
            title,
            "| Metric | "
            f"{cls._escape_table(name_a)} | "
            f"{cls._escape_table(name_b)} | "
            "Difference |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for label, value_a, value_b, difference in rows:

            lines.append(
                f"| {cls._escape_table(label)} | "
                f"{cls._escape_table(value_a)} | "
                f"{cls._escape_table(value_b)} | "
                f"{cls._escape_table(difference)} |"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @classmethod
    def _comparison_provenance(
        cls,
        metrics_a: Mapping[str, Any],
        metrics_b: Mapping[str, Any],
    ) -> str | None:

        provenance_a = cls._first_present(
            metrics_a.get("provenance"),
            metrics_a.get("satellite_facts"),
        )

        provenance_b = cls._first_present(
            metrics_b.get("provenance"),
            metrics_b.get("satellite_facts"),
        )

        if provenance_a is None and provenance_b is None:
            return None

        lines = [
            "#### Observation Provenance"
        ]

        if provenance_a is not None:
            lines.append(
                "• **Region A:** "
                + cls._compact_provenance(
                    provenance_a
                )
            )

        if provenance_b is not None:
            lines.append(
                "• **Region B:** "
                + cls._compact_provenance(
                    provenance_b
                )
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @classmethod
    def _comparison_confidence(
        cls,
        metrics_a: Mapping[str, Any],
        metrics_b: Mapping[str, Any],
    ) -> str | None:

        confidence_a = cls._first_present(
            metrics_a.get("confidence"),
            metrics_a.get("calibrated_confidence"),
            metrics_a.get("calibrated_confidence_pct"),
        )

        confidence_b = cls._first_present(
            metrics_b.get("confidence"),
            metrics_b.get("calibrated_confidence"),
            metrics_b.get("calibrated_confidence_pct"),
        )

        if confidence_a is None and confidence_b is None:
            return None

        lines = [
            "#### Reliability"
        ]

        if confidence_a is not None:
            lines.append(
                "• **Region A:** "
                + cls._format_confidence_value(
                    confidence_a
                )
            )

        if confidence_b is not None:
            lines.append(
                "• **Region B:** "
                + cls._format_confidence_value(
                    confidence_b
                )
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @classmethod
    def _comparison_limitations(
        cls,
        metrics_a: Mapping[str, Any],
        metrics_b: Mapping[str, Any],
    ) -> str | None:

        limitations: list[str] = []

        for metrics in (
            metrics_a,
            metrics_b,
        ):

            value = metrics.get(
                "limitations"
            )

            if isinstance(value, str):

                text = cls._clean_text(value)

                if text and text not in limitations:
                    limitations.append(text)

            elif isinstance(value, Sequence):

                for item in value:

                    if isinstance(item, Mapping):
                        text = cls._first_present(
                            item.get("message"),
                            item.get("reason"),
                            item.get("description"),
                        )
                    else:
                        text = item

                    text = cls._clean_text(text)

                    if (
                        text
                        and text not in limitations
                    ):
                        limitations.append(text)

        if not limitations:
            return None

        return (
            "#### Comparison Limitations\n"
            + "\n".join(
                f"• {item}"
                for item in limitations
            )
        )

    # ------------------------------------------------------------------

    @classmethod
    def _collect_comparison_interpretations(
        cls,
        metrics_a: Mapping[str, Any],
        metrics_b: Mapping[str, Any],
    ) -> list[str]:

        results: list[str] = []

        for metrics in (
            metrics_a,
            metrics_b,
        ):

            values = cls._first_present(
                metrics.get("interpretations"),
                metrics.get("interpretation"),
            )

            if values is None:
                continue

            if isinstance(values, str):
                text = cls._clean_text(values)

                if text and text not in results:
                    results.append(text)

                continue

            if isinstance(values, Mapping):
                values = [values]

            if not isinstance(values, Sequence):
                continue

            for item in values:

                if isinstance(item, Mapping):
                    text = cls._first_present(
                        item.get("interpretation"),
                        item.get("description"),
                        item.get("text"),
                    )
                else:
                    text = item

                text = cls._clean_text(text)

                if (
                    text
                    and text not in results
                ):
                    results.append(text)

        return results

    # ------------------------------------------------------------------
    # Report conversion
    # ------------------------------------------------------------------

    @classmethod
    def _report_to_dict(
        cls,
        report: Any,
    ) -> dict[str, Any]:

        if report is None:
            return {}

        if isinstance(report, Mapping):
            return dict(report)

        result: dict[str, Any] = {}

        candidate_fields = (
            "observations",
            "observation",
            "findings",
            "interpretations",
            "interpretation",
            "measurements",
            "gis_measurements",
            "aoi_telemetry",
            "data_quality",
            "satellite_facts",
            "provenance",
            "confidence",
            "calibrated_confidence",
            "calibrated_confidence_pct",
            "confidence_factors",
            "limitations",
            "limitations_notes",
            "validation",
            "evidence_items",
            "evidence_graph",
            "status",
            "message",
            "query_text",
            "engine_version",
        )

        for field in candidate_fields:

            if not hasattr(report, field):
                continue

            value = getattr(
                report,
                field,
            )

            if value is not None:
                result[field] = value

        gis = result.get(
            "gis_measurements"
        )

        if isinstance(gis, Mapping):

            if "aoi_telemetry" not in result:

                aoi = gis.get(
                    "aoi_telemetry"
                )

                if isinstance(aoi, Mapping):
                    result["aoi_telemetry"] = aoi

            if "data_quality" not in result:

                quality = gis.get(
                    "data_quality"
                )

                if isinstance(quality, Mapping):
                    result["data_quality"] = quality

        return result

    # ------------------------------------------------------------------
    # Observation helpers
    # ------------------------------------------------------------------

    @classmethod
    def _observation_text(
        cls,
        observation: Mapping[str, Any],
    ) -> str | None:

        text = cls._first_present(
            observation.get("observation"),
            observation.get("description"),
            observation.get("finding"),
            observation.get("answer"),
            observation.get("caption"),
            observation.get("text"),
        )

        if text is None:
            return None

        text = cls._clean_text(text)

        if not text:
            return None

        source = cls._first_present(
            observation.get("source"),
            observation.get("evidence_source"),
            observation.get("tool"),
        )

        if source:
            return (
                f"{text} "
                f"[Source: {source}]"
            )

        return text

    # ------------------------------------------------------------------
    # Measurement helpers
    # ------------------------------------------------------------------

    @classmethod
    def _format_generic_measurement(
        cls,
        key: str,
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        if isinstance(value, bool):
            return (
                "Yes"
                if value
                else "No"
            )

        numeric = cls._as_float(value)

        if numeric is not None:

            unit = cls._metric_unit(
                key
            )

            if unit:
                return (
                    f"{cls._format_number(numeric)} "
                    f"{unit}"
                )

            return cls._format_number(
                numeric
            )

        if isinstance(value, Mapping):
            return cls._compact_mapping(
                value
            )

        if isinstance(value, Sequence):
            return ", ".join(
                str(item)
                for item in value
            )

        text = cls._clean_text(value)

        return text or None

    # ------------------------------------------------------------------

    @classmethod
    def _metric_value_with_percentage(
        cls,
        value: Any,
        percentage: Any,
        key: str,
    ) -> str:

        value_text = cls._format_generic_measurement(
            key,
            value,
        )

        if value_text is None:
            value_text = "Not available"

        if percentage is not None:

            percentage_numeric = cls._as_float(
                percentage
            )

            if percentage_numeric is not None:
                value_text += (
                    f" ({cls._format_number(percentage_numeric)}%)"
                )
            else:
                value_text += (
                    f" ({percentage})"
                )

        return value_text

    # ------------------------------------------------------------------

    @classmethod
    def _numeric_difference(
        cls,
        value_a: Any,
        value_b: Any,
    ) -> float | None:

        a = cls._as_float(value_a)
        b = cls._as_float(value_b)

        if a is None or b is None:
            return None

        return a - b

    # ------------------------------------------------------------------

    @classmethod
    def _format_difference(
        cls,
        difference: float,
        name_a: str,
        name_b: str,
        unit: str | None,
    ) -> str:

        formatted = cls._format_number(
            abs(difference)
        )

        suffix = (
            f" {unit}"
            if unit
            else ""
        )

        if difference > 0:
            return (
                f"+{formatted}{suffix} "
                f"(higher in {name_a})"
            )

        if difference < 0:
            return (
                f"-{formatted}{suffix} "
                f"(higher in {name_b})"
            )

        return (
            f"0{suffix} "
            "(equal based on the supplied values)"
        )

    # ------------------------------------------------------------------

    @classmethod
    def _metric_unit(
        cls,
        key: str,
    ) -> str | None:

        if key.endswith("_km2"):
            return "km²"

        if key.endswith("_ha"):
            return "ha"

        if key.endswith("_pct"):
            return "%"

        return None

    # ------------------------------------------------------------------

    @classmethod
    def _comparison_mode_title(
        cls,
        comparison_mode: str,
    ) -> str:

        known_modes = {
            "MODE_B_TEMPORAL": (
                "Bi-Temporal Change Dynamics Comparison"
            ),
            "MODE_A_DESCRIPTIVE": (
                "Descriptive Evidence Comparison"
            ),
        }

        if comparison_mode in known_modes:
            return known_modes[
                comparison_mode
            ]

        if comparison_mode:
            return (
                str(comparison_mode)
                .replace("_", " ")
                .title()
            )

        return "Evidence Comparison"

    # ------------------------------------------------------------------

    @classmethod
    def _compact_provenance(
        cls,
        provenance: Any,
    ) -> str:

        if isinstance(provenance, Mapping):

            fields: list[str] = []

            for key in (
                "sensor",
                "platform",
                "observation_role",
                "acquisition_date",
                "date",
                "timestamp",
                "crs",
                "resolution_m",
                "gsd_m",
                "source",
                "provider",
                "filename",
            ):

                value = provenance.get(
                    key
                )

                if value is not None:
                    fields.append(
                        f"{cls._humanize_key(key)}: {value}"
                    )

            if fields:
                return "; ".join(
                    fields
                )

        if isinstance(provenance, Sequence):

            compact = [
                cls._compact_provenance(item)
                for item in provenance
                if item is not None
            ]

            compact = [
                item
                for item in compact
                if item
            ]

            if compact:
                return " | ".join(
                    compact
                )

        return str(provenance)

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @classmethod
    def _explicitly_identical(
        cls,
        location_a: Mapping[str, Any],
        location_b: Mapping[str, Any],
        metrics_a: Mapping[str, Any],
        metrics_b: Mapping[str, Any],
    ) -> bool:

        keys = (
            "identical",
            "identical_inputs",
            "identical_observations",
            "same_observation",
            "exact_duplicate",
        )

        for mapping in (
            location_a,
            location_b,
            metrics_a,
            metrics_b,
        ):

            for key in keys:

                value = mapping.get(key)

                if value is True:
                    return True

        comparison_a = metrics_a.get(
            "comparison"
        )

        comparison_b = metrics_b.get(
            "comparison"
        )

        for comparison in (
            comparison_a,
            comparison_b,
        ):

            if not isinstance(
                comparison,
                Mapping,
            ):
                continue

            for key in keys:

                if comparison.get(key) is True:
                    return True

        return False

    # ------------------------------------------------------------------

    @classmethod
    def _location_name(
        cls,
        location: Mapping[str, Any],
        fallback: str,
    ) -> str:

        value = cls._first_present(
            location.get("name"),
            location.get("canonical_name"),
            location.get("location_name"),
        )

        if value is None:
            return fallback

        return str(value)

    # ------------------------------------------------------------------
    # Confidence helpers
    # ------------------------------------------------------------------

    @classmethod
    def _format_confidence_value(
        cls,
        value: Any,
        key_hint: str | None = None,
    ) -> str:

        numeric = cls._as_float(value)

        if numeric is None:
            return str(value)

        if key_hint == "calibrated_confidence_pct":
            return (
                f"{cls._format_number(numeric)}%"
            )

        if 0.0 <= numeric <= 1.0:
            return (
                f"{numeric * 100.0:.1f}%"
            )

        if 1.0 < numeric <= 100.0:
            return (
                f"{cls._format_number(numeric)}%"
            )

        return cls._format_number(
            numeric
        )

    # ------------------------------------------------------------------

    @classmethod
    def _format_factor(
        cls,
        value: Any,
    ) -> str:

        numeric = cls._as_float(value)

        if numeric is None:
            return str(value)

        if 0.0 <= numeric <= 1.0:
            return f"{numeric:.3f}"

        return cls._format_number(
            numeric
        )

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    @classmethod
    def _format_coordinate_value(
        cls,
        value: Any,
    ) -> str:

        if value is None:
            return "Not available"

        if isinstance(value, Mapping):

            lat = cls._first_present(
                value.get("lat"),
                value.get("latitude"),
            )

            lon = cls._first_present(
                value.get("lon"),
                value.get("lng"),
                value.get("longitude"),
            )

            if (
                lat is not None
                and lon is not None
            ):
                return (
                    f"({lat}, {lon})"
                )

            return cls._compact_mapping(
                value
            )

        if isinstance(value, Sequence):

            return (
                "("
                + ", ".join(
                    str(item)
                    for item in value
                )
                + ")"
            )

        return str(value)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        return str(value).strip()

    # ------------------------------------------------------------------

    @staticmethod
    def _first_present(
        *values: Any,
    ) -> Any:

        for value in values:

            if value is None:
                continue

            if (
                isinstance(value, str)
                and not value.strip()
            ):
                continue

            return value

        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _as_float(
        value: Any,
    ) -> float | None:

        if isinstance(value, bool):
            return None

        if isinstance(
            value,
            (int, float),
        ):
            return float(value)

        if isinstance(value, str):

            try:
                return float(
                    value.strip()
                )
            except ValueError:
                return None

        return None

    # ------------------------------------------------------------------

    @classmethod
    def _format_number(
        cls,
        value: Any,
    ) -> str:

        numeric = cls._as_float(
            value
        )

        if numeric is None:
            return str(value)

        if numeric.is_integer():
            return (
                f"{int(numeric):,}"
            )

        return (
            f"{numeric:,.3f}"
            .rstrip("0")
            .rstrip(".")
        )

    # ------------------------------------------------------------------

    @classmethod
    def _format_measurement(
        cls,
        value: Any,
        unit: str,
    ) -> str:

        if value is None:
            return "Not available"

        numeric = cls._as_float(
            value
        )

        if numeric is None:
            return (
                f"{value} {unit}"
            )

        return (
            f"{cls._format_number(numeric)} "
            f"{unit}"
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _display_optional(
        value: Any,
    ) -> str:

        if value is None:
            return "Not available"

        text = str(value).strip()

        return (
            text
            if text
            else "Not available"
        )

    # ------------------------------------------------------------------

    @classmethod
    def _compact_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> str:

        parts: list[str] = []

        for key, item in value.items():

            if item is None:
                continue

            parts.append(
                f"{cls._humanize_key(str(key))}: {item}"
            )

        return (
            "; ".join(parts)
            if parts
            else str(dict(value))
        )

    # ------------------------------------------------------------------

    @classmethod
    def _humanize_key(
        cls,
        key: str,
    ) -> str:

        return (
            key.replace(
                "_",
                " ",
            )
            .strip()
            .title()
        )

    # ------------------------------------------------------------------

    @classmethod
    def _escape_table(
        cls,
        value: str,
    ) -> str:

        return (
            str(value)
            .replace(
                "|",
                "\\|",
            )
            .replace(
                "\n",
                " ",
            )
        )

    # ------------------------------------------------------------------

    @classmethod
    def _contains_any(
        cls,
        mapping: Mapping[str, Any],
        keys: Sequence[str],
    ) -> bool:

        return any(
            key in mapping
            and mapping[key] is not None
            for key in keys
        )


# ----------------------------------------------------------------------
# Module-level compatibility wrappers
# ----------------------------------------------------------------------


def compose_response(
    query_text: str,
    base_answer: str | None = None,
    evidence: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    execution_trace: list[dict[str, Any]] | None = None,
) -> str:
    """
    Module-level compatibility wrapper.
    """

    return ResponseEngine.compose(
        query_text=query_text,
        base_answer=base_answer,
        evidence=evidence,
        context=context,
        execution_trace=execution_trace,
    )


# ----------------------------------------------------------------------


def compose_from_report(
    query_text: str,
    report: Any,
    base_answer: str | None = None,
    context: dict[str, Any] | None = None,
    execution_trace: list[dict[str, Any]] | None = None,
) -> str:
    """
    Module-level wrapper for StructuredEvidenceReport-like objects.
    """

    return ResponseEngine.compose_from_report(
        query_text=query_text,
        report=report,
        base_answer=base_answer,
        context=context,
        execution_trace=execution_trace,
    )


# ----------------------------------------------------------------------


def format_grounded_answer(
    base_answer: str,
    report: Any,
    location_name: str | None = None,
    intent_target: str | None = None,
    is_temporal: bool = False,
) -> str:
    """
    Module-level compatibility wrapper.
    """

    return ResponseEngine.format_grounded_answer(
        base_answer=base_answer,
        report=report,
        location_name=location_name,
        intent_target=intent_target,
        is_temporal=is_temporal,
    )


# ----------------------------------------------------------------------


def format_comparison_answer(
    loc_a: dict[str, Any] | None,
    loc_b: dict[str, Any] | None,
    metrics_a: dict[str, Any] | None = None,
    metrics_b: dict[str, Any] | None = None,
    target: str = "general",
    comparison_mode: str = "MODE_A_DESCRIPTIVE",
) -> str:
    """
    Module-level compatibility wrapper.
    """

    return ResponseEngine.format_comparison_answer(
        loc_a=loc_a,
        loc_b=loc_b,
        metrics_a=metrics_a,
        metrics_b=metrics_b,
        target=target,
        comparison_mode=comparison_mode,
    )


# ----------------------------------------------------------------------


def generate_contextual_follow_ups(
    intent_name: str,
    location_name: str | None,
    metrics: dict[str, Any] | None,
) -> list[str]:
    """
    Module-level compatibility wrapper.
    """

    return ResponseEngine.generate_contextual_follow_ups(
        intent_name=intent_name,
        location_name=location_name,
        metrics=metrics,
    )