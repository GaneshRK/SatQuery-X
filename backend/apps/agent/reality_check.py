"""Reality Check Layer for SatQuery AI per SIH 26167 Architecture.
Performs pre-response verification across Data, Geometry, Metrics, and Models
to guarantee epistemological integrity and prevent fabricated or ungrounded outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RealityCheckResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    data_ok: bool = True
    geometry_ok: bool = True
    metrics_ok: bool = True
    model_ok: bool = True
    comparison_contract_ok: bool = True
    blocked_reason: Optional[str] = None
    suggested_actions: List[str] = field(default_factory=list)


class RealityCheck:
    """Rigorous pre-response sanity and grounding validator."""

    @staticmethod
    def check_data(
        raster: Optional[np.ndarray],
        sensor: str = "SENTINEL-2",
        modality: str = "OPTICAL",
    ) -> Tuple[bool, List[str]]:
        """Verifies raster array physical integrity."""
        issues = []
        if raster is None:
            return False, ["Raster array is None"]

        if not isinstance(raster, np.ndarray):
            return False, [f"Invalid raster type: {type(raster)}"]

        if raster.ndim < 2:
            return False, [f"Insufficient raster dimensions: ndim={raster.ndim}"]

        h, w = raster.shape[:2] if raster.ndim >= 2 else (0, 0)
        if h < 16 or w < 16:
            issues.append(f"Raster spatial extent is too small ({w}x{h})")

        if np.all(raster == 0):
            issues.append("Raster contains exclusively zero values (blank/empty observation)")

        if np.all(np.isnan(raster)):
            issues.append("Raster contains exclusively NaN values")

        # Check NoData ratio
        total_px = raster.shape[0] * raster.shape[1]
        zero_px = int(np.count_nonzero(raster == 0))
        if total_px > 0 and (zero_px / float(total_px)) > 0.85:
            issues.append(f"Excessive NoData coverage: {round(zero_px / float(total_px) * 100, 1)}%")

        return len(issues) == 0, issues

    @staticmethod
    def check_geometry(
        bbox: Any,
        coords: Optional[List[float]] = None,
    ) -> Tuple[bool, List[str], float]:
        """Verifies geographical bounding box and coordinates."""
        issues = []
        ground_area_km2 = 0.0

        if not bbox:
            return False, ["Geospatial bounding box is missing or null"], 0.0

        west, south, east, north = 0.0, 0.0, 0.0, 0.0
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            west, south, east, north = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        elif isinstance(bbox, dict) and all(k in bbox for k in ("west", "south", "east", "north")):
            west, south, east, north = float(bbox["west"]), float(bbox["south"]), float(bbox["east"]), float(bbox["north"])
        else:
            return False, [f"Unrecognized bounding box format: {bbox}"], 0.0

        # Range verification (WGS-84)
        if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
            issues.append(f"Longitudes out of bounds [-180, 180]: west={west}, east={east}")
        if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
            issues.append(f"Latitudes out of bounds [-90, 90]: south={south}, north={north}")

        # Orientation verification
        if west >= east:
            issues.append(f"Inverted longitude bounds: west ({west}) >= east ({east})")
        if south >= north:
            issues.append(f"Inverted latitude bounds: south ({south}) >= north ({north})")

        # Metric ground area calculation
        if len(issues) == 0:
            lat_mid = (south + north) / 2.0
            deg_lat_km = 111.132
            deg_lon_km = 111.320 * math.cos(math.radians(lat_mid))
            w_km = abs(east - west) * deg_lon_km
            h_km = abs(north - south) * deg_lat_km
            ground_area_km2 = round(w_km * h_km, 3)

            if ground_area_km2 <= 0.0:
                issues.append("Calculated ground area is zero or non-positive")

        return len(issues) == 0, issues, ground_area_km2

    @staticmethod
    def check_metrics(
        metrics: Dict[str, Any],
        aoi_area_km2: Optional[float] = None,
    ) -> Tuple[bool, List[str]]:
        """Verifies physical plausibility of GIS metrics."""
        issues = []
        if not metrics:
            return True, []

        area_keys = [
            "detected_change_km2", "water_body_area_km2", "vegetation_area_km2",
            "built_up_area_km2", "salt_pan_area_km2", "bare_soil_area_km2",
        ]

        for k in area_keys:
            if k in metrics:
                val = metrics[k]
                if val is None or math.isnan(float(val)) or math.isinf(float(val)):
                    issues.append(f"Metric '{k}' has non-finite value: {val}")
                elif float(val) < 0.0:
                    issues.append(f"Metric '{k}' cannot be negative: {val}")
                elif aoi_area_km2 and float(val) > (aoi_area_km2 * 1.20):
                    issues.append(f"Metric '{k}' ({val} km²) exceeds evaluated AOI area ({aoi_area_km2} km²)")

        if "detected_change_pct" in metrics:
            pct = metrics["detected_change_pct"]
            if pct is not None and (pct < 0.0 or pct > 100.0):
                issues.append(f"Change percentage '{pct}' out of bounds [0, 100]")

        return len(issues) == 0, issues

    @classmethod
    def validate_comparison_contract(
        cls,
        loc_a: Dict[str, Any],
        loc_b: Dict[str, Any],
        metrics_a: Optional[Dict[str, Any]] = None,
        metrics_b: Optional[Dict[str, Any]] = None,
    ) -> RealityCheckResult:
        """Enforces strict Comparison Contract between two geographic domains."""
        name_a = loc_a.get("name", "Region A")
        name_b = loc_b.get("name", "Region B")
        issues = []
        suggested = []

        # 1. Geometry verification
        ok_a, issues_a, area_a = cls.check_geometry(loc_a.get("bbox"), loc_a.get("coords"))
        ok_b, issues_b, area_b = cls.check_geometry(loc_b.get("bbox"), loc_b.get("coords"))

        if not ok_a:
            issues.append(f"Invalid geometry for {name_a}: {'; '.join(issues_a)}")
            suggested.append(f"Select a verified boundary for {name_a}")
        if not ok_b:
            issues.append(f"Invalid geometry for {name_b}: {'; '.join(issues_b)}")
            suggested.append(f"Select a verified boundary for {name_b}")

        # 2. Metrics verification if provided
        if metrics_a:
            m_ok_a, m_issues_a = cls.check_metrics(metrics_a, area_a)
            if not m_ok_a:
                issues.extend([f"{name_a} metric error: {i}" for i in m_issues_a])
        if metrics_b:
            m_ok_b, m_issues_b = cls.check_metrics(metrics_b, area_b)
            if not m_ok_b:
                issues.extend([f"{name_b} metric error: {i}" for i in m_issues_b])

        is_valid = len(issues) == 0
        blocked_reason = None
        if not is_valid:
            blocked_reason = (
                f"Comparative analysis between {name_a} and {name_b} could not satisfy the "
                f"SatQuery Comparison Contract: {'; '.join(issues)}."
            )

        return RealityCheckResult(
            is_valid=is_valid,
            issues=issues,
            geometry_ok=ok_a and ok_b,
            metrics_ok=len(issues) == 0,
            blocked_reason=blocked_reason,
            suggested_actions=suggested,
        )
