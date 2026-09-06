"""
Reality Check Layer for SatQuery-X.

This module performs pre-response validation of evidence produced by the
agentic remote-sensing pipeline.

Design principles
-----------------
1. Never manufacture scientific values.
2. Never assume a sensor, CRS, resolution, acquisition date, or AOI.
3. Never calculate geographic area from latitude/longitude degrees when an
   actual raster transform/CRS is available.
4. Distinguish missing evidence from invalid evidence.
5. Treat zero as a valid measurement unless the source explicitly identifies
   it as NoData.
6. Validate measurements against the actual evidence footprint when possible.
7. Validate temporal comparisons using actual observation metadata.
8. Validate cross-modal comparisons using actual modality/provenance metadata.
9. Return actionable validation results so the orchestrator can block or
   downgrade unsupported answers.
10. This layer validates evidence; it does not generate scientific evidence.

No language-model reasoning or chain-of-thought is exposed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


@dataclass
class RealityCheckResult:
    """
    Result returned by the reality-check layer.

    `is_valid` means the supplied evidence is internally acceptable for the
    validation requested. It does NOT mean that the scientific conclusion is
    universally true.

    `blocked_reason` should be used by upstream orchestration when the
    evidence is insufficient for the requested operation.
    """

    is_valid: bool

    issues: List[str] = field(default_factory=list)

    data_ok: bool = True
    geometry_ok: bool = True
    metrics_ok: bool = True
    model_ok: bool = True
    comparison_contract_ok: bool = True

    blocked_reason: Optional[str] = None

    suggested_actions: List[str] = field(default_factory=list)

    # Additional structured information for the orchestrator/UI.
    warnings: List[str] = field(default_factory=list)
    evidence_status: str = "VALIDATED"
    validated_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "is_valid": self.is_valid,
            "issues": list(self.issues),
            "data_ok": self.data_ok,
            "geometry_ok": self.geometry_ok,
            "metrics_ok": self.metrics_ok,
            "model_ok": self.model_ok,
            "comparison_contract_ok": self.comparison_contract_ok,
            "blocked_reason": self.blocked_reason,
            "suggested_actions": list(self.suggested_actions),
            "warnings": list(self.warnings),
            "evidence_status": self.evidence_status,
            "validated_fields": list(self.validated_fields),
        }


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


class RealityCheck:
    """
    Evidence-integrity validator for SatQuery-X.

    This class intentionally avoids domain assumptions such as:

        sensor = Sentinel-2
        CRS = EPSG:4326
        resolution = 10 m
        cloud cover = 0
        confidence = 0.9

    Those values must originate from actual metadata or actual processing
    outputs.
    """

    # Metrics which represent an area. The value is expected to be expressed
    # in square kilometres unless the producer explicitly stores another unit
    # alongside the metric.
    AREA_METRIC_KEYS = (
        "aoi_total_area_km2",
        "analysis_aoi_bbox_km2",
        "actual_raster_footprint_km2",
        "valid_cloud_free_area_km2",
        "valid_analysis_area_km2",
        "detected_change_km2",
        "water_body_area_km2",
        "open_water_area_km2",
        "vegetation_area_km2",
        "total_veg_km2",
        "built_up_area_km2",
        "salt_pan_area_km2",
        "bare_soil_area_km2",
        "dense_vegetation_km2",
        "sparse_vegetation_km2",
    )

    PERCENTAGE_METRIC_KEYS = (
        "detected_change_pct",
        "change_percentage",
        "built_up_pct",
        "vegetation_pct",
        "open_water_pct",
        "water_body_pct",
        "salt_pan_pct",
        "usable_analytical_area_pct",
        "usable_clear_data_pct",
        "cloud_cover_pct",
        "scene_cloud_cover_pct",
        "aoi_cloud_cover_pct",
        "shadow_cover_pct",
        "haze_pct",
        "nodata_pct",
    )

    INDEX_RANGES = {
        # Normalized Difference Vegetation Index.
        "mean_ndvi": (-1.0, 1.0),
        "ndvi_mean": (-1.0, 1.0),
        "min_ndvi": (-1.0, 1.0),
        "max_ndvi": (-1.0, 1.0),

        # Normalized Difference Water Index.
        "mean_ndwi": (-1.0, 1.0),
        "ndwi_mean": (-1.0, 1.0),
        "min_ndwi": (-1.0, 1.0),
        "max_ndwi": (-1.0, 1.0),

        # Normalized Difference Built-up Index.
        "mean_ndbi": (-1.0, 1.0),
        "ndbi_mean": (-1.0, 1.0),

        # Normalized Burn Ratio.
        "mean_nbr": (-1.0, 1.0),
        "nbr_mean": (-1.0, 1.0),
    }

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_finite_number(value: Any) -> bool:
        """Return True only for finite real numeric values."""
        if isinstance(value, bool):
            return False

        try:
            number = float(value)
        except (TypeError, ValueError):
            return False

        return math.isfinite(number)

    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        """Safely convert a value to float."""
        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    @staticmethod
    def _normalise_bbox(
        bbox: Any,
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Normalize a bbox into:

            west, south, east, north

        Supported inputs:
        - [west, south, east, north]
        - (west, south, east, north)
        - {"west": ..., "south": ..., "east": ..., "north": ...}
        - {"minx": ..., "miny": ..., "maxx": ..., "maxy": ...}
        """
        if bbox is None:
            return None

        try:
            if isinstance(bbox, dict):
                if all(
                    key in bbox
                    for key in ("west", "south", "east", "north")
                ):
                    values = (
                        bbox["west"],
                        bbox["south"],
                        bbox["east"],
                        bbox["north"],
                    )
                elif all(
                    key in bbox
                    for key in ("minx", "miny", "maxx", "maxy")
                ):
                    values = (
                        bbox["minx"],
                        bbox["miny"],
                        bbox["maxx"],
                        bbox["maxy"],
                    )
                else:
                    return None

            elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                values = (
                    bbox[0],
                    bbox[1],
                    bbox[2],
                    bbox[3],
                )
            else:
                return None

            result = tuple(float(value) for value in values)

        except (TypeError, ValueError):
            return None

        if not all(math.isfinite(value) for value in result):
            return None

        return result  # type: ignore[return-value]

    @staticmethod
    def _bbox_has_valid_orientation(
        bbox: Tuple[float, float, float, float],
    ) -> bool:
        west, south, east, north = bbox
        return west < east and south < north

    @staticmethod
    def _looks_like_geographic_bbox(
        bbox: Tuple[float, float, float, float],
    ) -> bool:
        """
        Determine whether a bbox can plausibly be expressed in lon/lat.

        This is only a sanity check. It does NOT prove that the CRS is WGS84.
        """
        west, south, east, north = bbox

        return (
            -180.0 <= west <= 180.0
            and -180.0 <= east <= 180.0
            and -90.0 <= south <= 90.0
            and -90.0 <= north <= 90.0
        )

    @staticmethod
    def _bbox_intersection(
        bbox_a: Tuple[float, float, float, float],
        bbox_b: Tuple[float, float, float, float],
    ) -> Optional[Tuple[float, float, float, float]]:
        """Return bbox intersection in the same coordinate system."""
        west_a, south_a, east_a, north_a = bbox_a
        west_b, south_b, east_b, north_b = bbox_b

        west = max(west_a, west_b)
        south = max(south_a, south_b)
        east = min(east_a, east_b)
        north = min(north_a, north_b)

        if west >= east or south >= north:
            return None

        return west, south, east, north

    @staticmethod
    def _bbox_area_in_coordinate_units(
        bbox: Tuple[float, float, float, float],
    ) -> float:
        """
        Calculate rectangular area in the coordinate units of the bbox.

        This deliberately does NOT convert degrees into kilometres.

        The method is only useful for relative geometry checks where the
        coordinate units are known to be linear.
        """
        west, south, east, north = bbox
        return abs((east - west) * (north - south))

    @staticmethod
    def _extract_crs(metadata: Optional[Dict[str, Any]]) -> Any:
        """Extract CRS from common metadata locations."""
        if not metadata:
            return None

        for key in (
            "crs",
            "coordinate_reference_system",
            "spatial_reference",
        ):
            if metadata.get(key) is not None:
                return metadata.get(key)

        raster_meta = metadata.get("raster_metadata")
        if isinstance(raster_meta, dict):
            for key in (
                "crs",
                "coordinate_reference_system",
                "spatial_reference",
            ):
                if raster_meta.get(key) is not None:
                    return raster_meta.get(key)

        return None

    @staticmethod
    def _extract_transform(metadata: Optional[Dict[str, Any]]) -> Any:
        """Extract raster affine/geotransform metadata."""
        if not metadata:
            return None

        for key in (
            "transform",
            "affine",
            "geotransform",
        ):
            if metadata.get(key) is not None:
                return metadata.get(key)

        raster_meta = metadata.get("raster_metadata")
        if isinstance(raster_meta, dict):
            for key in (
                "transform",
                "affine",
                "geotransform",
            ):
                if raster_meta.get(key) is not None:
                    return raster_meta.get(key)

        return None

    @staticmethod
    def _extract_shape(metadata: Optional[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
        """Extract raster height/width if available."""
        if not metadata:
            return None

        height = metadata.get("height")
        width = metadata.get("width")

        if height is None or width is None:
            raster_meta = metadata.get("raster_metadata")
            if isinstance(raster_meta, dict):
                height = raster_meta.get("height", height)
                width = raster_meta.get("width", width)

        try:
            height_i = int(height)
            width_i = int(width)
        except (TypeError, ValueError):
            return None

        if height_i <= 0 or width_i <= 0:
            return None

        return height_i, width_i

    # ------------------------------------------------------------------
    # Data validation
    # ------------------------------------------------------------------

    @classmethod
    def check_data(
        cls,
        raster: Optional[np.ndarray],
        sensor: Optional[str] = None,
        modality: Optional[str] = None,
        *,
        nodata_value: Any = None,
        allow_integer: bool = True,
        allow_nan: bool = True,
        min_spatial_dimension: int = 16,
    ) -> Tuple[bool, List[str]]:
        """
        Validate an actual raster array.

        Important:
        - Zero is NOT automatically treated as NoData.
        - Sensor and modality are metadata, not defaults.
        - NaN is not automatically invalid because masked/derived arrays can
          legitimately contain NaN values. An all-NaN array is invalid.
        """
        issues: List[str] = []

        if raster is None:
            return False, ["Raster array is missing"]

        if not isinstance(raster, np.ndarray):
            return False, [f"Invalid raster type: {type(raster).__name__}"]

        if raster.ndim < 2:
            return False, [
                f"Insufficient raster dimensions: ndim={raster.ndim}"
            ]

        if not allow_integer and np.issubdtype(raster.dtype, np.integer):
            issues.append(
                f"Integer raster dtype is not permitted for this validation: "
                f"{raster.dtype}"
            )

        # Spatial dimensions.
        if raster.ndim == 2:
            height, width = raster.shape
        else:
            height, width = raster.shape[-2:]

        if height < min_spatial_dimension or width < min_spatial_dimension:
            issues.append(
                "Raster spatial extent is too small "
                f"({width}x{height}); minimum supported validation extent is "
                f"{min_spatial_dimension}x{min_spatial_dimension}"
            )

        if raster.size == 0:
            issues.append("Raster contains no elements")
            return False, issues

        # Floating point finite-value inspection.
        if np.issubdtype(raster.dtype, np.floating):
            finite_mask = np.isfinite(raster)

            if not np.any(finite_mask):
                issues.append(
                    "Raster contains no finite numeric observations"
                )
            elif not allow_nan and np.any(~finite_mask):
                issues.append(
                    "Raster contains NaN or infinite values"
                )
            elif np.all(np.isnan(raster)):
                issues.append(
                    "Raster contains exclusively NaN values"
                )

        # Explicit NoData validation.
        #
        # We only calculate a NoData ratio if the producer actually supplied
        # a NoData value. Zero is otherwise a valid pixel value.
        if nodata_value is not None:
            try:
                if isinstance(nodata_value, float) and math.isnan(nodata_value):
                    nodata_mask = np.isnan(raster)
                else:
                    nodata_mask = raster == nodata_value

                nodata_ratio = float(np.count_nonzero(nodata_mask)) / float(
                    raster.size
                )

                if nodata_ratio >= 1.0:
                    issues.append(
                        "Raster contains exclusively the declared NoData value"
                    )
                elif nodata_ratio > 0.95:
                    issues.append(
                        "Raster contains more than 95% declared NoData pixels"
                    )

            except (TypeError, ValueError):
                issues.append(
                    f"Unable to evaluate declared NoData value: {nodata_value!r}"
                )

        # All-zero arrays are not automatically invalid. They can occur in
        # legitimate masks, but for a reflectance/radiometric raster they
        # should be surfaced as a warning by the caller rather than treated
        # universally as NoData.
        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Raster metadata validation
    # ------------------------------------------------------------------

    @classmethod
    def check_raster_metadata(
        cls,
        metadata: Optional[Dict[str, Any]],
        *,
        require_crs: bool = False,
        require_transform: bool = False,
        require_bounds: bool = False,
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate geospatial raster metadata.

        Returns:
            (ok, issues, validated_fields)
        """
        issues: List[str] = []
        validated: List[str] = []

        if not metadata:
            if require_crs or require_transform or require_bounds:
                return False, ["Raster metadata is missing"], validated
            return True, [], validated

        crs = cls._extract_crs(metadata)
        transform = cls._extract_transform(metadata)
        bounds = metadata.get("bounds")

        if crs is None:
            if require_crs:
                issues.append(
                    "Raster CRS is required but was not supplied"
                )
        else:
            validated.append("crs")

        if transform is None:
            if require_transform:
                issues.append(
                    "Raster affine/geotransform is required but was not supplied"
                )
        else:
            validated.append("transform")

        if bounds is None:
            bounds = metadata.get("bbox")

        normalized_bounds = cls._normalise_bbox(bounds)

        if normalized_bounds is None:
            if require_bounds:
                issues.append(
                    "Raster spatial bounds are required but were not supplied"
                )
        else:
            if not cls._bbox_has_valid_orientation(normalized_bounds):
                issues.append(
                    "Raster bounds have invalid orientation"
                )
            else:
                validated.append("bounds")

        shape = cls._extract_shape(metadata)
        if shape is not None:
            validated.append("shape")

        return len(issues) == 0, issues, validated

    # ------------------------------------------------------------------
    # Geometry validation
    # ------------------------------------------------------------------

    @classmethod
    def check_geometry(
        cls,
        bbox: Any,
        coords: Optional[Sequence[float]] = None,
        *,
        crs: Any = None,
        require_geographic_coordinates: bool = True,
    ) -> Tuple[bool, List[str], Optional[float]]:
        """
        Validate geographic geometry.

        IMPORTANT:
        This function does not convert degree-based coordinates into km².

        The returned area is only a coordinate-unit rectangle area and should
        NOT be presented to the user as km² unless the caller separately
        proves that the coordinates use a linear kilometre-based CRS.
        """
        issues: List[str] = []

        normalized = cls._normalise_bbox(bbox)

        if normalized is None:
            return (
                False,
                ["Geospatial bounding box is missing or invalid"],
                None,
            )

        west, south, east, north = normalized

        if not cls._bbox_has_valid_orientation(normalized):
            issues.append(
                "Bounding box must satisfy west < east and south < north"
            )

        if require_geographic_coordinates:
            if not cls._looks_like_geographic_bbox(normalized):
                issues.append(
                    "Bounding box is outside valid longitude/latitude ranges"
                )

        if coords is not None:
            try:
                if len(coords) < 2:
                    issues.append(
                        "Coordinate reference must contain longitude and latitude"
                    )
                else:
                    lon = float(coords[0])
                    lat = float(coords[1])

                    if not math.isfinite(lon) or not math.isfinite(lat):
                        issues.append(
                            "Coordinate reference contains non-finite values"
                        )
                    elif require_geographic_coordinates and not (
                        -180.0 <= lon <= 180.0
                        and -90.0 <= lat <= 90.0
                    ):
                        issues.append(
                            "Coordinate reference lies outside longitude/"
                            "latitude bounds"
                        )
                    elif (
                        cls._bbox_has_valid_orientation(normalized)
                        and not (
                            west <= lon <= east
                            and south <= lat <= north
                        )
                    ):
                        issues.append(
                            "Coordinate reference lies outside the supplied "
                            "bounding box"
                        )

            except (TypeError, ValueError):
                issues.append(
                    "Coordinate reference is not numeric"
                )

        coordinate_area = None

        if not issues:
            coordinate_area = cls._bbox_area_in_coordinate_units(normalized)

            if coordinate_area <= 0:
                issues.append(
                    "Bounding box has non-positive coordinate-space area"
                )

        return len(issues) == 0, issues, coordinate_area

    # ------------------------------------------------------------------
    # Raster footprint checks
    # ------------------------------------------------------------------

    @classmethod
    def check_raster_footprint(
        cls,
        raster_metadata: Optional[Dict[str, Any]],
        requested_bbox: Any,
    ) -> Tuple[bool, List[str]]:
        """
        Check that an actual raster footprint intersects the requested AOI.

        This method does not reproject coordinates. The CRS of both geometries
        must therefore already be known to be compatible.
        """
        issues: List[str] = []

        if not raster_metadata:
            return False, [
                "Raster metadata is missing; footprint intersection cannot "
                "be verified"
            ]

        raster_bbox = raster_metadata.get("bounds")
        if raster_bbox is None:
            raster_bbox = raster_metadata.get("bbox")

        raster_normalized = cls._normalise_bbox(raster_bbox)
        requested_normalized = cls._normalise_bbox(requested_bbox)

        if raster_normalized is None:
            return False, [
                "Actual raster footprint is unavailable or invalid"
            ]

        if requested_normalized is None:
            return False, [
                "Requested AOI geometry is unavailable or invalid"
            ]

        raster_crs = cls._extract_crs(raster_metadata)

        requested_crs = (
            raster_metadata.get("requested_crs")
            or raster_metadata.get("aoi_crs")
        )

        if raster_crs is not None and requested_crs is not None:
            if str(raster_crs) != str(requested_crs):
                return False, [
                    "Raster footprint and requested AOI use different CRS "
                    "identifiers; reprojection is required before overlap "
                    "validation"
                ]

        intersection = cls._bbox_intersection(
            raster_normalized,
            requested_normalized,
        )

        if intersection is None:
            issues.append(
                "Actual raster footprint does not intersect the requested AOI"
            )

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Metrics validation
    # ------------------------------------------------------------------

    @classmethod
    def check_metrics(
        cls,
        metrics: Optional[Dict[str, Any]],
        aoi_area_km2: Optional[float] = None,
        *,
        valid_area_km2: Optional[float] = None,
        strict: bool = True,
    ) -> Tuple[bool, List[str]]:
        """
        Validate derived measurements.

        No missing metric is converted to zero.

        Area metrics are checked against a supplied actual area only when
        that area is explicitly available.
        """
        issues: List[str] = []

        if metrics is None:
            return True, []

        if not isinstance(metrics, dict):
            return False, [
                f"Metrics must be a dictionary, received "
                f"{type(metrics).__name__}"
            ]

        comparison_area = (
            valid_area_km2
            if valid_area_km2 is not None
            else aoi_area_km2
        )

        if comparison_area is not None:
            if not cls._is_finite_number(comparison_area):
                issues.append(
                    "Reference AOI area is not finite"
                )
            elif float(comparison_area) < 0:
                issues.append(
                    "Reference AOI area cannot be negative"
                )

        # --------------------------------------------------------------
        # Area metrics
        # --------------------------------------------------------------

        for key in cls.AREA_METRIC_KEYS:
            if key not in metrics:
                continue

            value = metrics.get(key)

            if value is None:
                issues.append(
                    f"Metric '{key}' is explicitly null"
                )
                continue

            numeric = cls._as_float(value)

            if numeric is None:
                issues.append(
                    f"Metric '{key}' is not a finite numeric value: {value!r}"
                )
                continue

            if numeric < 0:
                issues.append(
                    f"Metric '{key}' cannot be negative: {numeric}"
                )
                continue

            if (
                comparison_area is not None
                and cls._is_finite_number(comparison_area)
                and numeric > float(comparison_area)
            ):
                issues.append(
                    f"Metric '{key}' ({numeric}) exceeds the supplied "
                    f"reference area ({float(comparison_area)})"
                )

        # --------------------------------------------------------------
        # Percentage metrics
        # --------------------------------------------------------------

        for key in cls.PERCENTAGE_METRIC_KEYS:
            if key not in metrics:
                continue

            value = metrics.get(key)

            if value is None:
                continue

            numeric = cls._as_float(value)

            if numeric is None:
                issues.append(
                    f"Percentage metric '{key}' is not finite: {value!r}"
                )
                continue

            if numeric < 0.0 or numeric > 100.0:
                issues.append(
                    f"Percentage metric '{key}'={numeric} lies outside "
                    "the valid [0, 100] interval"
                )

        # --------------------------------------------------------------
        # Normalized index ranges
        # --------------------------------------------------------------

        for key, (lower, upper) in cls.INDEX_RANGES.items():
            if key not in metrics:
                continue

            value = metrics.get(key)

            if value is None:
                continue

            numeric = cls._as_float(value)

            if numeric is None:
                issues.append(
                    f"Index metric '{key}' is not finite: {value!r}"
                )
                continue

            if numeric < lower or numeric > upper:
                issues.append(
                    f"Index metric '{key}'={numeric} lies outside "
                    f"[{lower}, {upper}]"
                )

        # --------------------------------------------------------------
        # Count metrics
        # --------------------------------------------------------------

        count_keys = (
            "structures_detected_count",
            "water_features_count",
            "feature_count",
            "object_count",
        )

        for key in count_keys:
            if key not in metrics:
                continue

            value = metrics.get(key)

            if value is None:
                continue

            numeric = cls._as_float(value)

            if numeric is None:
                issues.append(
                    f"Count metric '{key}' is not numeric: {value!r}"
                )
                continue

            if numeric < 0:
                issues.append(
                    f"Count metric '{key}' cannot be negative"
                )
            elif strict and not numeric.is_integer():
                issues.append(
                    f"Count metric '{key}' must be an integer"
                )

        # --------------------------------------------------------------
        # Logical consistency checks
        # --------------------------------------------------------------

        total_area = metrics.get("aoi_total_area_km2")
        valid_area = metrics.get("valid_analysis_area_km2")

        if total_area is not None and valid_area is not None:
            total_numeric = cls._as_float(total_area)
            valid_numeric = cls._as_float(valid_area)

            if (
                total_numeric is not None
                and valid_numeric is not None
                and valid_numeric > total_numeric
            ):
                issues.append(
                    "Valid analytical area exceeds total AOI area"
                )

        # If both absolute change and change percentage are supplied, the
        # percentage must be physically compatible with a supplied reference
        # area. We do not manufacture either side when missing.
        change_area = metrics.get("detected_change_km2")
        change_pct = metrics.get("detected_change_pct")

        reference_for_change = (
            valid_area
            if valid_area is not None
            else total_area
        )

        if (
            change_area is not None
            and change_pct is not None
            and reference_for_change is not None
        ):
            change_numeric = cls._as_float(change_area)
            pct_numeric = cls._as_float(change_pct)
            ref_numeric = cls._as_float(reference_for_change)

            if (
                change_numeric is not None
                and pct_numeric is not None
                and ref_numeric is not None
                and ref_numeric > 0
            ):
                expected_pct = (
                    change_numeric / ref_numeric
                ) * 100.0

                # This is only a consistency warning, not a scientific
                # recomputation of the original measurement.
                if abs(expected_pct - pct_numeric) > max(
                    1.0,
                    abs(pct_numeric) * 0.10,
                ):
                    issues.append(
                        "Detected change area and detected change percentage "
                        "are internally inconsistent with the supplied "
                        "reference area"
                    )

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Provenance validation
    # ------------------------------------------------------------------

    @classmethod
    def check_provenance(
        cls,
        scenes: Optional[Iterable[Dict[str, Any]]],
        *,
        require_acquisition_date: bool = False,
        require_sensor: bool = False,
        require_crs: bool = False,
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate scene provenance without assigning defaults.

        The purpose is to make missing provenance explicit.
        """
        issues: List[str] = []
        validated: List[str] = []

        scene_list = list(scenes or [])

        if not scene_list:
            return True, [], validated

        for index, scene in enumerate(scene_list, start=1):
            if not isinstance(scene, dict):
                issues.append(
                    f"Scene {index} provenance is not an object"
                )
                continue

            scene_label = (
                scene.get("external_id")
                or scene.get("scene_id")
                or f"scene {index}"
            )

            acquisition_date = (
                scene.get("acquisition_date")
                or scene.get("datetime")
                or scene.get("timestamp")
            )

            sensor = (
                scene.get("sensor")
                or scene.get("instrument")
                or scene.get("platform")
            )

            crs = scene.get("crs")

            if acquisition_date is None:
                if require_acquisition_date:
                    issues.append(
                        f"{scene_label}: acquisition date/time is missing"
                    )
            else:
                validated.append(
                    f"{scene_label}:acquisition_datetime"
                )

            if sensor is None:
                if require_sensor:
                    issues.append(
                        f"{scene_label}: sensor/platform provenance is missing"
                    )
            else:
                validated.append(
                    f"{scene_label}:sensor"
                )

            if crs is None:
                if require_crs:
                    issues.append(
                        f"{scene_label}: CRS provenance is missing"
                    )
            else:
                validated.append(
                    f"{scene_label}:crs"
                )

            # Cloud cover may legitimately be absent. If supplied, validate
            # its range rather than replacing it with zero.
            cloud_value = (
                scene.get("cloud_cover_pct")
                if "cloud_cover_pct" in scene
                else scene.get("cloud_cover")
            )

            if cloud_value is not None:
                cloud_numeric = cls._as_float(cloud_value)

                if cloud_numeric is None:
                    issues.append(
                        f"{scene_label}: cloud-cover value is not numeric"
                    )
                elif cloud_numeric < 0 or cloud_numeric > 100:
                    issues.append(
                        f"{scene_label}: cloud-cover value is outside "
                        "[0, 100]"
                    )

        return len(issues) == 0, issues, validated

    # ------------------------------------------------------------------
    # Change-analysis validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_change_evidence(
        cls,
        before_scene: Optional[Dict[str, Any]],
        after_scene: Optional[Dict[str, Any]],
        *,
        coregistration_valid: Optional[bool] = None,
        change_mask_available: bool = False,
    ) -> RealityCheckResult:
        """
        Validate prerequisites for bi-temporal change analysis.
        """
        issues: List[str] = []
        warnings: List[str] = []
        suggested: List[str] = []
        validated: List[str] = []

        if before_scene is None:
            issues.append(
                "The baseline observation is missing"
            )
            suggested.append(
                "Provide or retrieve an actual baseline satellite observation"
            )

        if after_scene is None:
            issues.append(
                "The target observation is missing"
            )
            suggested.append(
                "Provide or retrieve an actual target satellite observation"
            )

        if before_scene is not None and after_scene is not None:
            validated.extend(
                ["before_scene", "after_scene"]
            )

            before_crs = before_scene.get("crs")
            after_crs = after_scene.get("crs")

            if before_crs is None or after_crs is None:
                warnings.append(
                    "CRS provenance is incomplete for one or both observations"
                )
            elif str(before_crs) != str(after_crs):
                warnings.append(
                    "The two observations use different CRS identifiers; "
                    "explicit reprojection/coregistration evidence is required"
                )

            before_shape = cls._extract_shape(before_scene)
            after_shape = cls._extract_shape(after_scene)

            if (
                before_shape is not None
                and after_shape is not None
                and before_shape != after_shape
            ):
                warnings.append(
                    "The observations have different raster dimensions; "
                    "registered comparison evidence is required"
                )

            before_bbox = cls._normalise_bbox(
                before_scene.get("bounds") or before_scene.get("bbox")
            )
            after_bbox = cls._normalise_bbox(
                after_scene.get("bounds") or after_scene.get("bbox")
            )

            if before_bbox is not None and after_bbox is not None:
                if cls._bbox_intersection(before_bbox, after_bbox) is None:
                    issues.append(
                        "The baseline and target observations do not spatially "
                        "overlap"
                    )
                    suggested.append(
                        "Select observations with a verified overlapping AOI"
                    )
                else:
                    validated.append(
                        "temporal_spatial_overlap"
                    )

            before_date = (
                before_scene.get("acquisition_date")
                or before_scene.get("datetime")
                or before_scene.get("timestamp")
            )
            after_date = (
                after_scene.get("acquisition_date")
                or after_scene.get("datetime")
                or after_scene.get("timestamp")
            )

            if before_date is None or after_date is None:
                issues.append(
                    "Both observations require acquisition timestamps for "
                    "a temporal comparison"
                )
                suggested.append(
                    "Provide acquisition dates/times for both observations"
                )
            elif str(before_date) == str(after_date):
                warnings.append(
                    "Both observations carry the same acquisition timestamp; "
                    "verify that they represent distinct observations"
                )

        if coregistration_valid is False:
            issues.append(
                "Coregistration was explicitly reported as invalid"
            )
            suggested.append(
                "Register the observations to a common spatial reference "
                "before interpreting pixel-level change"
            )
        elif coregistration_valid is True:
            validated.append(
                "coregistration"
            )
        else:
            warnings.append(
                "Coregistration status was not supplied"
            )

        if change_mask_available:
            validated.append(
                "change_mask"
            )
        else:
            warnings.append(
                "No derived change mask was supplied"
            )

        is_valid = len(issues) == 0

        blocked_reason = None

        if not is_valid:
            blocked_reason = (
                "Bi-temporal change analysis is blocked because the supplied "
                "evidence does not satisfy the required temporal/spatial "
                "validation checks."
            )

        return RealityCheckResult(
            is_valid=is_valid,
            issues=issues,
            data_ok=True,
            geometry_ok=not any(
                "overlap" in issue.lower()
                for issue in issues
            ),
            metrics_ok=True,
            model_ok=True,
            comparison_contract_ok=is_valid,
            blocked_reason=blocked_reason,
            suggested_actions=suggested,
            warnings=warnings,
            evidence_status=(
                "VALIDATED"
                if is_valid
                else "BLOCKED"
            ),
            validated_fields=validated,
        )

    # ------------------------------------------------------------------
    # Cross-modal validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_cross_modal_evidence(
        cls,
        optical_scene: Optional[Dict[str, Any]],
        sar_scene: Optional[Dict[str, Any]],
    ) -> RealityCheckResult:
        """
        Validate prerequisites for optical/SAR cross-modal analysis.

        Optical and SAR data must not be treated as interchangeable.
        """
        issues: List[str] = []
        warnings: List[str] = []
        suggested: List[str] = []
        validated: List[str] = []

        if optical_scene is None:
            issues.append(
                "Optical observation is missing"
            )
            suggested.append(
                "Provide an actual optical observation"
            )

        if sar_scene is None:
            issues.append(
                "SAR observation is missing"
            )
            suggested.append(
                "Provide an actual SAR observation"
            )

        if optical_scene is not None:
            validated.append("optical_scene")

        if sar_scene is not None:
            validated.append("sar_scene")

        if optical_scene is not None and sar_scene is not None:
            optical_modality = str(
                optical_scene.get("modality", "")
            ).upper()

            sar_modality = str(
                sar_scene.get("modality", "")
            ).upper()

            if optical_modality and optical_modality not in {
                "OPTICAL",
                "MULTISPECTRAL",
                "MSI",
                "VIS",
            }:
                warnings.append(
                    f"Optical input declares modality '{optical_modality}'"
                )

            if sar_modality and sar_modality not in {
                "SAR",
                "RADAR",
            }:
                warnings.append(
                    f"SAR input declares modality '{sar_modality}'"
                )

            optical_bbox = cls._normalise_bbox(
                optical_scene.get("bounds") or optical_scene.get("bbox")
            )
            sar_bbox = cls._normalise_bbox(
                sar_scene.get("bounds") or sar_scene.get("bbox")
            )

            if optical_bbox is not None and sar_bbox is not None:
                if cls._bbox_intersection(
                    optical_bbox,
                    sar_bbox,
                ) is None:
                    issues.append(
                        "Optical and SAR observations have no spatial overlap"
                    )
                    suggested.append(
                        "Select overlapping optical and SAR observations"
                    )
                else:
                    validated.append(
                        "cross_modal_spatial_overlap"
                    )
            else:
                warnings.append(
                    "One or both modal spatial footprints are unavailable"
                )

            optical_crs = optical_scene.get("crs")
            sar_crs = sar_scene.get("crs")

            if optical_crs is None or sar_crs is None:
                warnings.append(
                    "CRS provenance is incomplete for cross-modal alignment"
                )
            elif str(optical_crs) != str(sar_crs):
                warnings.append(
                    "Optical and SAR observations use different CRS "
                    "identifiers; explicit reprojection/alignment evidence "
                    "is required"
                )

            validated.append(
                "modality_pair"
            )

        is_valid = len(issues) == 0

        blocked_reason = None
        if not is_valid:
            blocked_reason = (
                "Cross-modal analysis is blocked because the optical/SAR "
                "evidence does not satisfy spatial and modality validation."
            )

        return RealityCheckResult(
            is_valid=is_valid,
            issues=issues,
            data_ok=is_valid,
            geometry_ok=is_valid,
            metrics_ok=True,
            model_ok=True,
            comparison_contract_ok=is_valid,
            blocked_reason=blocked_reason,
            suggested_actions=suggested,
            warnings=warnings,
            evidence_status=(
                "VALIDATED"
                if is_valid
                else "BLOCKED"
            ),
            validated_fields=validated,
        )

    # ------------------------------------------------------------------
    # Comparison contract
    # ------------------------------------------------------------------

    @classmethod
    def validate_comparison_contract(
        cls,
        loc_a: Dict[str, Any],
        loc_b: Dict[str, Any],
        metrics_a: Optional[Dict[str, Any]] = None,
        metrics_b: Optional[Dict[str, Any]] = None,
        *,
        scene_a: Optional[Dict[str, Any]] = None,
        scene_b: Optional[Dict[str, Any]] = None,
        require_equal_crs: bool = False,
        require_measurements: bool = False,
    ) -> RealityCheckResult:
        """
        Validate a two-region comparison.

        The contract does not silently insert:
            Region A / Region B
            zero areas
            default percentages
            default sensor information
            default CRS

        Missing information remains missing.
        """
        issues: List[str] = []
        warnings: List[str] = []
        suggested: List[str] = []
        validated: List[str] = []

        if not isinstance(loc_a, dict):
            return RealityCheckResult(
                is_valid=False,
                issues=["Location A is not a valid object"],
                geometry_ok=False,
                comparison_contract_ok=False,
                blocked_reason=(
                    "Comparison cannot proceed because Location A is invalid."
                ),
            )

        if not isinstance(loc_b, dict):
            return RealityCheckResult(
                is_valid=False,
                issues=["Location B is not a valid object"],
                geometry_ok=False,
                comparison_contract_ok=False,
                blocked_reason=(
                    "Comparison cannot proceed because Location B is invalid."
                ),
            )

        name_a = (
            loc_a.get("name")
            or loc_a.get("canonical_name")
            or "Location A"
        )

        name_b = (
            loc_b.get("name")
            or loc_b.get("canonical_name")
            or "Location B"
        )

        # --------------------------------------------------------------
        # Geometry
        # --------------------------------------------------------------

        bbox_a = loc_a.get("bbox")
        bbox_b = loc_b.get("bbox")

        ok_a, issues_a, _ = cls.check_geometry(
            bbox_a,
            loc_a.get("coords"),
            crs=loc_a.get("crs"),
            require_geographic_coordinates=False,
        )

        ok_b, issues_b, _ = cls.check_geometry(
            bbox_b,
            loc_b.get("coords"),
            crs=loc_b.get("crs"),
            require_geographic_coordinates=False,
        )

        if not ok_a:
            issues.extend(
                [f"{name_a}: {issue}" for issue in issues_a]
            )
            suggested.append(
                f"Select or resolve a verified geometry for {name_a}"
            )
        else:
            validated.append(
                f"{name_a}:geometry"
            )

        if not ok_b:
            issues.extend(
                [f"{name_b}: {issue}" for issue in issues_b]
            )
            suggested.append(
                f"Select or resolve a verified geometry for {name_b}"
            )
        else:
            validated.append(
                f"{name_b}:geometry"
            )

        # --------------------------------------------------------------
        # Metric validation
        # --------------------------------------------------------------

        metrics_ok = True

        if metrics_a:
            area_a = cls._as_float(
                metrics_a.get("valid_analysis_area_km2")
                if metrics_a.get("valid_analysis_area_km2") is not None
                else metrics_a.get("aoi_total_area_km2")
            )

            m_ok_a, m_issues_a = cls.check_metrics(
                metrics_a,
                aoi_area_km2=area_a,
                valid_area_km2=area_a,
            )

            if not m_ok_a:
                metrics_ok = False
                issues.extend(
                    [
                        f"{name_a} metric error: {issue}"
                        for issue in m_issues_a
                    ]
                )
            else:
                validated.append(
                    f"{name_a}:metrics"
                )

        elif require_measurements:
            metrics_ok = False
            issues.append(
                f"{name_a}: quantitative measurements are required "
                "for this comparison"
            )
            suggested.append(
                f"Run an actual measurement pipeline for {name_a}"
            )

        if metrics_b:
            area_b = cls._as_float(
                metrics_b.get("valid_analysis_area_km2")
                if metrics_b.get("valid_analysis_area_km2") is not None
                else metrics_b.get("aoi_total_area_km2")
            )

            m_ok_b, m_issues_b = cls.check_metrics(
                metrics_b,
                aoi_area_km2=area_b,
                valid_area_km2=area_b,
            )

            if not m_ok_b:
                metrics_ok = False
                issues.extend(
                    [
                        f"{name_b} metric error: {issue}"
                        for issue in m_issues_b
                    ]
                )
            else:
                validated.append(
                    f"{name_b}:metrics"
                )

        elif require_measurements:
            metrics_ok = False
            issues.append(
                f"{name_b}: quantitative measurements are required "
                "for this comparison"
            )
            suggested.append(
                f"Run an actual measurement pipeline for {name_b}"
            )

        # --------------------------------------------------------------
        # Scene provenance
        # --------------------------------------------------------------

        if scene_a is not None:
            scene_a_ok, scene_a_issues, scene_a_fields = (
                cls.check_provenance(
                    [scene_a],
                    require_acquisition_date=False,
                    require_sensor=False,
                    require_crs=require_equal_crs,
                )
            )

            if not scene_a_ok:
                issues.extend(
                    [f"{name_a}: {issue}" for issue in scene_a_issues]
                )

            validated.extend(
                [f"{name_a}:{field}" for field in scene_a_fields]
            )

        if scene_b is not None:
            scene_b_ok, scene_b_issues, scene_b_fields = (
                cls.check_provenance(
                    [scene_b],
                    require_acquisition_date=False,
                    require_sensor=False,
                    require_crs=require_equal_crs,
                )
            )

            if not scene_b_ok:
                issues.extend(
                    [f"{name_b}: {issue}" for issue in scene_b_issues]
                )

            validated.extend(
                [f"{name_b}:{field}" for field in scene_b_fields]
            )

        # --------------------------------------------------------------
        # CRS compatibility
        # --------------------------------------------------------------

        if scene_a is not None and scene_b is not None:
            crs_a = scene_a.get("crs")
            crs_b = scene_b.get("crs")

            if crs_a is not None and crs_b is not None:
                if str(crs_a) != str(crs_b):
                    warnings.append(
                        "The two comparison inputs have different CRS "
                        "identifiers; comparison requires explicit "
                        "reprojection/alignment"
                    )
                else:
                    validated.append(
                        "comparison_crs_compatibility"
                    )
            elif require_equal_crs:
                issues.append(
                    "CRS provenance is required for both comparison inputs"
                )

        # --------------------------------------------------------------
        # Final status
        # --------------------------------------------------------------

        geometry_ok = ok_a and ok_b
        is_valid = (
            geometry_ok
            and metrics_ok
            and len(issues) == 0
        )

        blocked_reason = None

        if not is_valid:
            blocked_reason = (
                f"Comparative analysis between {name_a} and {name_b} "
                "cannot be released because the supplied evidence failed "
                "one or more validation checks."
            )

        return RealityCheckResult(
            is_valid=is_valid,
            issues=issues,
            data_ok=True,
            geometry_ok=geometry_ok,
            metrics_ok=metrics_ok,
            model_ok=True,
            comparison_contract_ok=is_valid,
            blocked_reason=blocked_reason,
            suggested_actions=suggested,
            warnings=warnings,
            evidence_status=(
                "VALIDATED"
                if is_valid
                else "BLOCKED"
            ),
            validated_fields=validated,
        )

    # ------------------------------------------------------------------
    # Complete response-level validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_response_evidence(
        cls,
        *,
        raster: Optional[np.ndarray] = None,
        raster_metadata: Optional[Dict[str, Any]] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        requested_bbox: Any = None,
        confidence: Any = None,
        answer: Optional[str] = None,
        require_raster: bool = False,
        require_geometry: bool = False,
        require_provenance: bool = False,
        require_metrics: bool = False,
    ) -> RealityCheckResult:
        """
        Perform a consolidated response-level evidence check.

        This is intended for the final gate before an answer is exposed to
        the user.
        """
        issues: List[str] = []
        warnings: List[str] = []
        suggested: List[str] = []
        validated: List[str] = []

        data_ok = True
        geometry_ok = True
        metrics_ok = True
        model_ok = True

        # --------------------------------------------------------------
        # Raster
        # --------------------------------------------------------------

        if raster is None:
            if require_raster:
                data_ok = False
                issues.append(
                    "Required raster evidence is missing"
                )
                suggested.append(
                    "Provide an actual satellite raster before making "
                    "image-derived claims"
                )
        else:
            raster_ok, raster_issues = cls.check_data(
                raster
            )

            if not raster_ok:
                data_ok = False
                issues.extend(raster_issues)
            else:
                validated.append(
                    "raster_data"
                )

        # --------------------------------------------------------------
        # Raster metadata
        # --------------------------------------------------------------

        if raster_metadata is not None:
            metadata_ok, metadata_issues, metadata_fields = (
                cls.check_raster_metadata(
                    raster_metadata,
                    require_crs=require_geometry,
                    require_transform=require_geometry,
                    require_bounds=require_geometry,
                )
            )

            if not metadata_ok:
                geometry_ok = False
                issues.extend(metadata_issues)

            validated.extend(
                [f"raster_metadata:{field}" for field in metadata_fields]
            )

        elif require_geometry:
            geometry_ok = False
            issues.append(
                "Required raster geospatial metadata is missing"
            )
            suggested.append(
                "Provide actual CRS, transform, and raster bounds"
            )

        # --------------------------------------------------------------
        # Requested geometry
        # --------------------------------------------------------------

        if requested_bbox is not None:
            geometry_check, geometry_issues, _ = cls.check_geometry(
                requested_bbox,
                require_geographic_coordinates=False,
            )

            if not geometry_check:
                geometry_ok = False
                issues.extend(geometry_issues)
            else:
                validated.append(
                    "requested_geometry"
                )

            if raster_metadata is not None and geometry_check:
                footprint_ok, footprint_issues = (
                    cls.check_raster_footprint(
                        raster_metadata,
                        requested_bbox,
                    )
                )

                if not footprint_ok:
                    geometry_ok = False
                    issues.extend(footprint_issues)
                else:
                    validated.append(
                        "raster_requested_aoi_intersection"
                    )

        elif require_geometry:
            geometry_ok = False
            issues.append(
                "Required requested AOI geometry is missing"
            )

        # --------------------------------------------------------------
        # Scene provenance
        # --------------------------------------------------------------

        provenance_ok, provenance_issues, provenance_fields = (
            cls.check_provenance(
                scenes,
                require_acquisition_date=require_provenance,
                require_sensor=require_provenance,
                require_crs=require_provenance,
            )
        )

        if not provenance_ok:
            data_ok = False
            issues.extend(provenance_issues)

        validated.extend(
            [f"provenance:{field}" for field in provenance_fields]
        )

        # --------------------------------------------------------------
        # Metrics
        # --------------------------------------------------------------

        if metrics is not None:
            reference_area = None

            if raster_metadata:
                reference_area = cls._as_float(
                    raster_metadata.get("valid_analysis_area_km2")
                    or raster_metadata.get("actual_raster_footprint_km2")
                )

            metrics_check, metric_issues = cls.check_metrics(
                metrics,
                aoi_area_km2=reference_area,
                valid_area_km2=reference_area,
            )

            if not metrics_check:
                metrics_ok = False
                issues.extend(metric_issues)
            else:
                validated.append(
                    "metrics"
                )

        elif require_metrics:
            metrics_ok = False
            issues.append(
                "Required quantitative measurements are missing"
            )
            suggested.append(
                "Run the appropriate measurement tool before returning "
                "quantitative claims"
            )

        # --------------------------------------------------------------
        # Confidence
        # --------------------------------------------------------------

        if confidence is not None:
            confidence_numeric = cls._as_float(confidence)

            if confidence_numeric is None:
                model_ok = False
                issues.append(
                    "Model/tool confidence is not a finite numeric value"
                )
            elif confidence_numeric < 0.0 or confidence_numeric > 1.0:
                model_ok = False
                issues.append(
                    "Model/tool confidence must be within [0, 1]"
                )
            else:
                validated.append(
                    "confidence"
                )

        # --------------------------------------------------------------
        # Answer presence
        # --------------------------------------------------------------

        if answer is not None:
            if not isinstance(answer, str):
                model_ok = False
                issues.append(
                    "Final answer must be a string"
                )
            elif not answer.strip():
                model_ok = False
                issues.append(
                    "Final answer is empty"
                )

        # --------------------------------------------------------------
        # Final gate
        # --------------------------------------------------------------

        is_valid = (
            data_ok
            and geometry_ok
            and metrics_ok
            and model_ok
            and len(issues) == 0
        )

        blocked_reason = None

        if not is_valid:
            blocked_reason = (
                "The proposed response did not pass the evidence-integrity "
                "gate. One or more required evidence, geometry, metric, or "
                "model checks failed."
            )

        return RealityCheckResult(
            is_valid=is_valid,
            issues=issues,
            data_ok=data_ok,
            geometry_ok=geometry_ok,
            metrics_ok=metrics_ok,
            model_ok=model_ok,
            comparison_contract_ok=True,
            blocked_reason=blocked_reason,
            suggested_actions=suggested,
            warnings=warnings,
            evidence_status=(
                "VALIDATED"
                if is_valid
                else "BLOCKED"
            ),
            validated_fields=validated,
        )

    # ------------------------------------------------------------------
    # Compatibility aliases
    # ------------------------------------------------------------------

    @classmethod
    def validate(
        cls,
        *,
        raster: Optional[np.ndarray] = None,
        raster_metadata: Optional[Dict[str, Any]] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        requested_bbox: Any = None,
        confidence: Any = None,
        answer: Optional[str] = None,
        **kwargs: Any,
    ) -> RealityCheckResult:
        """
        Backwards-compatible general validation entry point.

        Existing callers can continue to use `RealityCheck.validate(...)`
        while the newer orchestrator can use the explicit methods above.
        """
        return cls.validate_response_evidence(
            raster=raster,
            raster_metadata=raster_metadata,
            scenes=scenes,
            metrics=metrics,
            requested_bbox=requested_bbox,
            confidence=confidence,
            answer=answer,
            **kwargs,
        )

    @classmethod
    def validate_inputs(
        cls,
        **kwargs: Any,
    ) -> RealityCheckResult:
        """Compatibility alias for validate()."""
        return cls.validate(**kwargs)


__all__ = [
    "RealityCheck",
    "RealityCheckResult",
]