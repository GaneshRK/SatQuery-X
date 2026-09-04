from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    data_quality_score: float  # 0 to 100
    cloud_penalty: float
    resolution_penalty: float
    nodata_penalty: float
    crs_valid: bool
    overall_confidence: float  # 0.0 to 1.0
    confidence_level: str  # "HIGH", "MEDIUM", "LOW"
    uncertainty_reasons: list[str] = field(default_factory=list)


class ConfidenceEngine:
    """
    Computes calibrated data quality scores (0-100) and composite confidence (0.0-1.0)
    from empirical satellite raster characteristics, model agreement, and observation conditions.
    Never fabricates confidence.
    """

    @staticmethod
    def evaluate_raster_quality(
        cloud_cover_pct: float | None = 0.0,
        resolution_m: float | None = 10.0,
        nodata_pct: float | None = 0.0,
        crs: str | None = "EPSG:4326",
        band_count: int = 4,
    ) -> QualityMetrics:
        score = 100.0
        uncertainty_reasons = []

        # 1. Cloud Cover Penalty (up to 35 points)
        cloud = cloud_cover_pct or 0.0
        cloud_penalty = 0.0
        if cloud > 5.0:
            cloud_penalty = min(35.0, (cloud - 5.0) * 0.8)
            score -= cloud_penalty
            if cloud > 15.0:
                uncertainty_reasons.append(
                    f"Cloud contamination affects {cloud:.1f}% of the scene, reducing optical surface clarity."
                )

        # 2. Resolution GSD Penalty (e.g. 10m Sentinel vs 30m Landsat vs 250m MODIS)
        res = resolution_m or 10.0
        res_penalty = 0.0
        if res > 10.0:
            res_penalty = min(20.0, (res - 10.0) * 0.5)
            score -= res_penalty
            if res >= 20.0:
                uncertainty_reasons.append(
                    f"Ground Sample Distance of {res:.0f}m limits detection of sub-pixel spatial features."
                )

        # 3. NoData / Corrupt Pixels Penalty
        nodata = nodata_pct or 0.0
        nodata_penalty = 0.0
        if nodata > 1.0:
            nodata_penalty = min(25.0, nodata * 1.2)
            score -= nodata_penalty
            uncertainty_reasons.append(f"NoData mask covers {nodata:.1f}% of the analysis envelope.")

        # 4. CRS check
        crs_valid = bool(crs and "EPSG" in crs.upper())
        if not crs_valid:
            score -= 15.0
            uncertainty_reasons.append("Unreferenced or non-standard Spatial Reference System (SRS).")

        # 5. Missing Bands check
        if band_count < 3:
            score -= 10.0
            uncertainty_reasons.append("Limited spectral band depth restricts full-spectrum verification.")

        final_score = max(10.0, min(100.0, score))

        # Map to 0.0 - 1.0 confidence
        base_confidence = final_score / 100.0
        if base_confidence >= 0.85:
            conf_level = "HIGH"
        elif base_confidence >= 0.70:
            conf_level = "MEDIUM"
        else:
            conf_level = "LOW"

        return QualityMetrics(
            data_quality_score=round(final_score, 1),
            cloud_penalty=round(cloud_penalty, 1),
            resolution_penalty=round(res_penalty, 1),
            nodata_penalty=round(nodata_penalty, 1),
            crs_valid=crs_valid,
            overall_confidence=round(base_confidence, 2),
            confidence_level=conf_level,
            uncertainty_reasons=uncertainty_reasons,
        )

    @staticmethod
    def calibrate_answer_confidence(
        model_confidence: float,
        quality_metrics: QualityMetrics,
        detection_count: int = 0,
    ) -> float:
        """
        Combines model output probability with physical raster quality.
        """
        data_weight = 0.4
        model_weight = 0.6
        calibrated = (quality_metrics.overall_confidence * data_weight) + (model_confidence * model_weight)
        return round(float(min(0.99, max(0.10, calibrated))), 2)
