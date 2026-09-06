from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNKNOWN = "UNKNOWN"

STATUS_AGREEMENT = "AGREEMENT"
STATUS_DISAGREEMENT = "DISAGREEMENT"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

EPSILON = 1e-9


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class QualityMetrics:
    """
    Evidence-quality assessment for an actual raster/observation.

    Important:
        None means the property was not available.

    The engine must never replace missing metadata with an assumed value.
    """

    data_quality_score: float | None
    cloud_penalty: float | None
    resolution_penalty: float | None
    nodata_penalty: float | None
    crs_valid: bool | None
    overall_confidence: float | None
    confidence_level: str
    uncertainty_reasons: list[str] = field(default_factory=list)

    # Additional evidence metadata.
    available_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_quality_score": self.data_quality_score,
            "cloud_penalty": self.cloud_penalty,
            "resolution_penalty": self.resolution_penalty,
            "nodata_penalty": self.nodata_penalty,
            "crs_valid": self.crs_valid,
            "overall_confidence": self.overall_confidence,
            "confidence_level": self.confidence_level,
            "uncertainty_reasons": list(self.uncertainty_reasons),
            "available_fields": list(self.available_fields),
            "missing_fields": list(self.missing_fields),
        }


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _finite_float(value: Any) -> float | None:
    """
    Convert a value to a finite float.

    Invalid, NaN, and infinite values are treated as unavailable.
    """
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _confidence_level(confidence: float | None) -> str:
    """
    Convert an actual confidence value to a qualitative level.

    These thresholds describe the returned value; they do not claim
    statistical calibration unless the underlying model itself is calibrated.
    """
    if confidence is None:
        return CONFIDENCE_UNKNOWN

    if confidence >= 0.85:
        return CONFIDENCE_HIGH

    if confidence >= 0.65:
        return CONFIDENCE_MEDIUM

    return CONFIDENCE_LOW


def _normalise_percentage(
    value: Any,
    field_name: str,
) -> tuple[float | None, str | None]:
    """
    Validate a percentage without inventing a missing value.
    """
    parsed = _finite_float(value)

    if parsed is None:
        return None, f"{field_name} is unavailable."

    if parsed < 0.0 or parsed > 100.0:
        return None, f"{field_name} is outside the valid 0-100% range."

    return parsed, None


def _normalise_positive(value: Any, field_name: str) -> tuple[float | None, str | None]:
    """
    Validate a positive physical measurement.
    """
    parsed = _finite_float(value)

    if parsed is None:
        return None, f"{field_name} is unavailable."

    if parsed <= 0.0:
        return None, f"{field_name} must be greater than zero."

    return parsed, None


def _is_valid_crs(crs: Any) -> bool | None:
    """
    Perform a conservative CRS presence check.

    This intentionally does not claim that a CRS string is semantically
    correct for the raster. Full CRS validation belongs to the raster/GDAL
    layer.
    """
    if crs is None:
        return None

    if not isinstance(crs, str):
        return False

    value = crs.strip()

    if not value:
        return None

    # Accept common representations such as:
    # EPSG:4326
    # EPSG:32643
    # WKT strings
    # PROJ strings
    # URNs
    upper = value.upper()

    if (
        upper.startswith("EPSG:")
        or "GEOGCS[" in upper
        or "PROJCS[" in upper
        or "+PROJ=" in upper
        or "URN:OGC:DEF:CRS" in upper
        or "HTTP://WWW.OPENGIS.NET/DEF/CRS" in upper
    ):
        return True

    # A non-empty CRS identifier is evidence that a CRS was supplied,
    # but we cannot validate it here.
    return False


def _extract_detected(result: Mapping[str, Any]) -> bool | None:
    """
    Extract an explicit detection verdict.

    Missing detection information remains None rather than becoming False.
    """

    if "detected" in result and result.get("detected") is not None:
        value = result.get("detected")

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            lowered = value.strip().lower()

            if lowered in {"true", "yes", "detected", "present", "positive"}:
                return True

            if lowered in {"false", "no", "not_detected", "absent", "negative"}:
                return False

    if "count" in result and result.get("count") is not None:
        count = _finite_float(result.get("count"))

        if count is not None:
            return count > 0

    if "presence" in result and result.get("presence") is not None:
        value = result.get("presence")

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            lowered = value.strip().lower()

            if lowered in {"present", "detected", "yes", "true"}:
                return True

            if lowered in {"absent", "not_detected", "no", "false"}:
                return False

    return None


def _extract_confidence(result: Mapping[str, Any]) -> float | None:
    """
    Extract an explicit model confidence.

    Does not fabricate confidence when a model does not provide one.
    """

    for key in (
        "confidence",
        "model_confidence",
        "probability",
        "score",
    ):
        if key not in result:
            continue

        value = _finite_float(result.get(key))

        if value is None:
            continue

        # Most model confidence values are [0, 1].
        # Some systems expose percentages [0, 100].
        if 0.0 <= value <= 1.0:
            return value

        if 0.0 <= value <= 100.0:
            return value / 100.0

    return None


# ---------------------------------------------------------------------------
# Confidence engine
# ---------------------------------------------------------------------------


class ConfidenceEngine:
    """
    Evidence-quality and confidence engine for SatQuery-X.

    Design principles:

    1. Missing metadata is UNKNOWN, never a fabricated default.
    2. Model confidence is kept separate from physical data quality.
    3. Confidence is not presented as statistically calibrated unless the
       underlying model provides a calibrated probability.
    4. Model disagreement is explicitly surfaced.
    5. A missing measurement must not be interpreted as zero.
    6. No scientific values are invented by this class.
    """

    @staticmethod
    def evaluate_raster_quality(
        cloud_cover_pct: float | None = None,
        resolution_m: float | None = None,
        nodata_pct: float | None = None,
        crs: str | None = None,
        band_count: int | None = None,
    ) -> QualityMetrics:
        """
        Evaluate raster-quality evidence from supplied metadata.

        Parameters are optional because remote-sensing metadata is not always
        available at every processing stage.

        No default satellite, resolution, cloud percentage, CRS, or band count
        is assumed.
        """

        uncertainty_reasons: list[str] = []
        available_fields: list[str] = []
        missing_fields: list[str] = []

        score_components: list[float] = []

        # ---------------------------------------------------------------
        # Cloud cover
        # ---------------------------------------------------------------

        cloud, cloud_error = _normalise_percentage(
            cloud_cover_pct,
            "Cloud cover",
        )

        cloud_penalty: float | None = None

        if cloud is None:
            missing_fields.append("cloud_cover_pct")

            if cloud_error:
                uncertainty_reasons.append(cloud_error)
        else:
            available_fields.append("cloud_cover_pct")

            # Cloud penalty is deliberately transparent.
            # It is a quality heuristic, not a statistical calibration.
            if cloud <= 5.0:
                cloud_penalty = 0.0
            else:
                cloud_penalty = min(35.0, (cloud - 5.0) * 0.8)

            cloud_score = max(0.0, 100.0 - cloud_penalty)
            score_components.append(cloud_score)

            if cloud > 15.0:
                uncertainty_reasons.append(
                    f"Reported cloud cover is {cloud:.1f}% and may reduce "
                    "optical surface visibility."
                )

        # ---------------------------------------------------------------
        # Spatial resolution
        # ---------------------------------------------------------------

        resolution, resolution_error = _normalise_positive(
            resolution_m,
            "Spatial resolution",
        )

        resolution_penalty: float | None = None

        if resolution is None:
            missing_fields.append("resolution_m")

            if resolution_error:
                uncertainty_reasons.append(resolution_error)
        else:
            available_fields.append("resolution_m")

            if resolution <= 10.0:
                resolution_penalty = 0.0
            else:
                resolution_penalty = min(20.0, (resolution - 10.0) * 0.5)

            resolution_score = max(0.0, 100.0 - resolution_penalty)
            score_components.append(resolution_score)

            if resolution >= 20.0:
                uncertainty_reasons.append(
                    f"Spatial resolution of {resolution:g} m limits detection "
                    "of smaller spatial features."
                )

        # ---------------------------------------------------------------
        # NoData
        # ---------------------------------------------------------------

        nodata, nodata_error = _normalise_percentage(
            nodata_pct,
            "NoData percentage",
        )

        nodata_penalty: float | None = None

        if nodata is None:
            missing_fields.append("nodata_pct")

            if nodata_error:
                uncertainty_reasons.append(nodata_error)
        else:
            available_fields.append("nodata_pct")

            if nodata <= 1.0:
                nodata_penalty = 0.0
            else:
                nodata_penalty = min(25.0, nodata * 1.2)

            nodata_score = max(0.0, 100.0 - nodata_penalty)
            score_components.append(nodata_score)

            if nodata > 1.0:
                uncertainty_reasons.append(
                    f"NoData affects {nodata:.1f}% of the supplied analysis "
                    "envelope."
                )

        # ---------------------------------------------------------------
        # CRS
        # ---------------------------------------------------------------

        crs_valid = _is_valid_crs(crs)

        if crs_valid is None:
            missing_fields.append("crs")
            uncertainty_reasons.append(
                "Coordinate reference system information is unavailable."
            )
        elif crs_valid is False:
            available_fields.append("crs")
            uncertainty_reasons.append(
                "The supplied CRS identifier could not be validated by the "
                "confidence layer."
            )
            score_components.append(50.0)
        else:
            available_fields.append("crs")
            score_components.append(100.0)

        # ---------------------------------------------------------------
        # Band count
        # ---------------------------------------------------------------

        if band_count is None:
            missing_fields.append("band_count")
            uncertainty_reasons.append(
                "Band-count metadata is unavailable."
            )
        else:
            try:
                bands = int(band_count)
            except (TypeError, ValueError):
                bands = -1

            if bands < 0:
                missing_fields.append("band_count")
                uncertainty_reasons.append(
                    "Band-count metadata is invalid."
                )
            else:
                available_fields.append("band_count")

                if bands < 3:
                    score_components.append(70.0)
                    uncertainty_reasons.append(
                        "The supplied imagery contains limited band "
                        "information for spectral verification."
                    )
                else:
                    score_components.append(100.0)

        # ---------------------------------------------------------------
        # Overall quality
        # ---------------------------------------------------------------

        if not score_components:
            return QualityMetrics(
                data_quality_score=None,
                cloud_penalty=None,
                resolution_penalty=None,
                nodata_penalty=None,
                crs_valid=crs_valid,
                overall_confidence=None,
                confidence_level=CONFIDENCE_UNKNOWN,
                uncertainty_reasons=[
                    "Insufficient raster metadata to compute a quality score."
                ],
                available_fields=available_fields,
                missing_fields=missing_fields,
            )

        quality_score = sum(score_components) / len(score_components)

        quality_score = max(0.0, min(100.0, quality_score))

        # Important:
        # This is an evidence-quality indicator, not a calibrated probability
        # that the analysis result is correct.
        overall_confidence = quality_score / 100.0

        return QualityMetrics(
            data_quality_score=round(quality_score, 1),
            cloud_penalty=(
                round(cloud_penalty, 1)
                if cloud_penalty is not None
                else None
            ),
            resolution_penalty=(
                round(resolution_penalty, 1)
                if resolution_penalty is not None
                else None
            ),
            nodata_penalty=(
                round(nodata_penalty, 1)
                if nodata_penalty is not None
                else None
            ),
            crs_valid=crs_valid,
            overall_confidence=round(overall_confidence, 3),
            confidence_level=_confidence_level(overall_confidence),
            uncertainty_reasons=uncertainty_reasons,
            available_fields=available_fields,
            missing_fields=missing_fields,
        )

    # ------------------------------------------------------------------
    # Answer confidence
    # ------------------------------------------------------------------

    @staticmethod
    def calibrate_answer_confidence(
        model_confidence: float | None,
        quality_metrics: QualityMetrics | None,
        detection_count: int | None = None,
    ) -> float | None:
        """
        Combine model confidence with evidence quality.

        This method intentionally does NOT call the result a statistically
        calibrated probability.

        If either model confidence or physical quality is unavailable, the
        method returns the information that can actually be supported rather
        than fabricating a number.

        Current combination:
            60% model confidence
            40% data-quality indicator

        These weights are engineering heuristics and should be replaced with
        empirically calibrated weights once validation data exists.
        """

        model = _finite_float(model_confidence)

        if model is not None:
            model = _clamp01(model)

        data_quality: float | None = None

        if quality_metrics is not None:
            data_quality = _finite_float(
                quality_metrics.overall_confidence
            )

            if data_quality is not None:
                data_quality = _clamp01(data_quality)

        # No defensible composite can be produced without either signal.
        if model is None and data_quality is None:
            return None

        if model is None:
            logger.debug(
                "Model confidence unavailable; returning evidence-quality "
                "indicator only."
            )
            return round(data_quality, 3) if data_quality is not None else None

        if data_quality is None:
            logger.debug(
                "Raster quality unavailable; returning model confidence only."
            )
            return round(model, 3)

        calibrated = (model * 0.60) + (data_quality * 0.40)

        return round(_clamp01(calibrated), 3)

    # ------------------------------------------------------------------
    # Model agreement
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_model_disagreement(
        model_a_result: Mapping[str, Any],
        model_b_result: Mapping[str, Any],
        target_class: str = "target",
    ) -> dict[str, Any]:
        """
        Compare explicit model verdicts.

        Critical behavior:

            detected=True  + detected=False -> DISAGREEMENT
            detected=True  + missing        -> INSUFFICIENT_EVIDENCE
            detected=False + missing        -> INSUFFICIENT_EVIDENCE
            missing        + missing        -> INSUFFICIENT_EVIDENCE

        Missing information is never interpreted as a negative detection.
        """

        a_detected = _extract_detected(model_a_result)
        b_detected = _extract_detected(model_b_result)

        a_confidence = _extract_confidence(model_a_result)
        b_confidence = _extract_confidence(model_b_result)

        # ---------------------------------------------------------------
        # Missing evidence
        # ---------------------------------------------------------------

        if a_detected is None or b_detected is None:
            return {
                "status": STATUS_INSUFFICIENT_EVIDENCE,
                "message": (
                    f"Insufficient evidence to determine whether the models "
                    f"agree regarding {target_class}."
                ),
                "model_a_verdict": a_detected,
                "model_b_verdict": b_detected,
                "model_a_confidence": a_confidence,
                "model_b_confidence": b_confidence,
                "confidence_level": CONFIDENCE_UNKNOWN,
            }

        # ---------------------------------------------------------------
        # Explicit disagreement
        # ---------------------------------------------------------------

        if a_detected != b_detected:
            return {
                "status": STATUS_DISAGREEMENT,
                "message": (
                    f"The supplied model evidence conflicts regarding "
                    f"{target_class}."
                ),
                "model_a_verdict": a_detected,
                "model_b_verdict": b_detected,
                "model_a_confidence": a_confidence,
                "model_b_confidence": b_confidence,
                "confidence_level": CONFIDENCE_LOW,
            }

        # ---------------------------------------------------------------
        # Explicit agreement
        # ---------------------------------------------------------------

        confidence_values = [
            value
            for value in (a_confidence, b_confidence)
            if value is not None
        ]

        if confidence_values:
            agreement_confidence = sum(confidence_values) / len(
                confidence_values
            )
            agreement_level = _confidence_level(agreement_confidence)
        else:
            agreement_confidence = None

            # Agreement itself is known, but statistical confidence is not.
            agreement_level = CONFIDENCE_UNKNOWN

        verdict = "detected" if a_detected else "not detected"

        return {
            "status": STATUS_AGREEMENT,
            "message": (
                f"The supplied models agree: {target_class} was {verdict}."
            ),
            "model_a_verdict": a_detected,
            "model_b_verdict": b_detected,
            "model_a_confidence": a_confidence,
            "model_b_confidence": b_confidence,
            "agreement_confidence": (
                round(agreement_confidence, 3)
                if agreement_confidence is not None
                else None
            ),
            "confidence_level": agreement_level,
        }

    # ------------------------------------------------------------------
    # Evidence aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_confidence(
        confidence_values: Sequence[float | None],
    ) -> float | None:
        """
        Calculate a simple mean of explicitly available confidence values.

        Missing values are ignored rather than converted to zero.

        This is an aggregation utility, not statistical calibration.
        """

        valid: list[float] = []

        for value in confidence_values:
            parsed = _finite_float(value)

            if parsed is None:
                continue

            valid.append(_clamp01(parsed))

        if not valid:
            return None

        return round(sum(valid) / len(valid), 3)

    # ------------------------------------------------------------------
    # Evidence summary
    # ------------------------------------------------------------------

    @staticmethod
    def build_confidence_summary(
        *,
        model_confidence: float | None = None,
        quality_metrics: QualityMetrics | None = None,
        evidence_confidences: Sequence[float | None] | None = None,
        disagreement: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build a frontend/API-safe confidence summary.

        This produces an auditable summary without exposing hidden reasoning.
        """

        quality_confidence = (
            quality_metrics.overall_confidence
            if quality_metrics is not None
            else None
        )

        evidence_confidence = (
            ConfidenceEngine.aggregate_confidence(
                evidence_confidences
            )
            if evidence_confidences is not None
            else None
        )

        answer_confidence = ConfidenceEngine.calibrate_answer_confidence(
            model_confidence=model_confidence,
            quality_metrics=quality_metrics,
        )

        reasons: list[str] = []

        if quality_metrics is not None:
            reasons.extend(quality_metrics.uncertainty_reasons)

        if disagreement:
            status = disagreement.get("status")

            if status == STATUS_DISAGREEMENT:
                reasons.append(
                    "Multiple supplied analysis results disagree."
                )

            elif status == STATUS_INSUFFICIENT_EVIDENCE:
                reasons.append(
                    "There is insufficient evidence to establish model agreement."
                )

        return {
            "answer_confidence": answer_confidence,
            "answer_confidence_level": _confidence_level(answer_confidence),
            "model_confidence": (
                round(_clamp01(float(model_confidence)), 3)
                if _finite_float(model_confidence) is not None
                else None
            ),
            "data_quality_confidence": quality_confidence,
            "evidence_confidence": evidence_confidence,
            "quality_metrics": (
                quality_metrics.to_dict()
                if quality_metrics is not None
                else None
            ),
            "model_agreement": dict(disagreement)
            if disagreement is not None
            else None,
            "uncertainty_reasons": list(dict.fromkeys(reasons)),
        }