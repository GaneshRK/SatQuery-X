"""Temporal pairing and geospatial coregistration for four-stream Optical/SAR analysis.

This module pairs real observations by acquisition time and aligns each SAR
observation to the optical grid for the same temporal pair. It never invents
missing observations, CRS, transforms, or spatial overlap.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any
import uuid


@dataclass(frozen=True)
class Observation:
    index: int
    path: str
    modality: str
    acquisition: datetime
    record: dict[str, Any]


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            d = date.fromisoformat(text[:10])
            dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normal_modality(record: dict[str, Any]) -> str:
    value = str(record.get("modality") or "").strip().lower()
    if value in {"multispectral", "optical"}:
        return "optical"
    if value in {"sar", "radar"}:
        return "sar"
    return "unknown"


def _pair_by_time(optical: list[Observation], sar: list[Observation], max_delta_hours: float) -> list[tuple[Observation, Observation]]:
    if not optical or not sar:
        return []
    remaining = set(x.index for x in sar)
    pairs: list[tuple[Observation, Observation]] = []
    for opt in sorted(optical, key=lambda x: x.acquisition):
        candidates = [x for x in sar if x.index in remaining]
        if not candidates:
            break
        best = min(candidates, key=lambda x: abs((x.acquisition - opt.acquisition).total_seconds()))
        delta_hours = abs((best.acquisition - opt.acquisition).total_seconds()) / 3600.0
        if delta_hours <= max_delta_hours:
            pairs.append((opt, best))
            remaining.remove(best.index)
    return pairs


def _align_sar_to_optical(sar_path: str, optical_path: str, output_path: str) -> dict[str, Any]:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    with rasterio.open(optical_path) as opt, rasterio.open(sar_path) as sar:
        if opt.crs is None or sar.crs is None:
            raise ValueError("Both optical and SAR rasters must contain CRS metadata.")
        if opt.transform is None or sar.transform is None:
            raise ValueError("Both optical and SAR rasters must contain affine transforms.")
        from apps.geospatial.coregistration import _bounds_intersect, inspect_grid
        if not _bounds_intersect(inspect_grid(sar_path), inspect_grid(optical_path)):
            raise ValueError("Optical and SAR observations do not overlap spatially.")

        profile = sar.profile.copy()
        profile.update(
            driver="GTiff",
            height=opt.height,
            width=opt.width,
            transform=opt.transform,
            crs=opt.crs,
            count=1,
            dtype="float32",
            nodata=np.nan,
            compress="deflate",
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        destination = np.full((opt.height, opt.width), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(sar, 1),
            destination=destination,
            src_transform=sar.transform,
            src_crs=sar.crs,
            dst_transform=opt.transform,
            dst_crs=opt.crs,
            src_nodata=sar.nodata,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(destination, 1)
        return {
            "path": output_path,
            "crs": opt.crs.to_string(),
            "transform": list(opt.transform[:6]),
            "width": opt.width,
            "height": opt.height,
            "resampling": "bilinear",
            "source_sar": sar_path,
            "reference_optical": optical_path,
        }


def prepare_temporal_optical_sar(
    records: list[dict[str, Any]],
    paths: list[str],
    *,
    max_pair_delta_hours: float = 72.0,
    output_root: str | None = None,
) -> dict[str, Any]:
    """Return an ordered [Optical T1, SAR T1, Optical T2, SAR T2] set.

    SAR files are physically reprojected/resampled to the corresponding
    optical grid. The optical files are retained as the reference rasters.
    Exactly two distinct temporal pairs are required.
    """
    if len(records) != len(paths):
        raise ValueError("Temporal coregistration requires one metadata record per image path.")
    if len(records) < 4:
        raise ValueError("Temporal Optical/SAR coregistration requires at least four observations.")

    observations: list[Observation] = []
    for idx, (record, path) in enumerate(zip(records, paths)):
        modality = _normal_modality(record)
        acquisition = _parse_datetime(record.get("acquisition_date"))
        if modality == "unknown":
            raise ValueError(f"Observation {idx} has unknown modality; coregistration will not guess it.")
        if acquisition is None:
            raise ValueError(f"Observation {idx} has no parseable acquisition timestamp/date.")
        if not Path(path).is_file():
            raise ValueError(f"Observation path does not exist: {path}")
        observations.append(Observation(idx, path, modality, acquisition, record))

    optical = [x for x in observations if x.modality == "optical"]
    sar = [x for x in observations if x.modality == "sar"]
    if len(optical) < 2 or len(sar) < 2:
        raise ValueError("Two optical and two SAR observations are required.")

    pairs = _pair_by_time(optical, sar, float(max_pair_delta_hours))
    if len(pairs) < 2:
        raise ValueError("Could not form two optical/SAR temporal pairs within the configured time tolerance.")
    pairs = sorted(pairs, key=lambda p: p[0].acquisition)[:2]
    if pairs[0][0].acquisition == pairs[1][0].acquisition:
        raise ValueError("Temporal pairs must contain two distinct acquisition times.")

    root = Path(output_root or "")
    if not root:
        raise ValueError("output_root is required for persistent derived coregistered rasters.")
    run_dir = root / "temporal_coregistration" / str(uuid.uuid4())

    ordered_paths: list[str] = []
    pair_reports: list[dict[str, Any]] = []
    for temporal_index, (opt, sar_obs) in enumerate(pairs, start=1):
        aligned_sar = run_dir / f"t{temporal_index}_sar_aligned.tif"
        report = _align_sar_to_optical(sar_obs.path, opt.path, str(aligned_sar))
        ordered_paths.extend([opt.path, str(aligned_sar)])
        pair_reports.append({
            "temporal_index": temporal_index,
            "optical_source_index": opt.index,
            "sar_source_index": sar_obs.index,
            "optical_acquisition": opt.acquisition.isoformat(),
            "sar_acquisition": sar_obs.acquisition.isoformat(),
            "pair_delta_hours": abs((sar_obs.acquisition - opt.acquisition).total_seconds()) / 3600.0,
            "aligned_sar": report,
        })

    return {
        "status": "completed",
        "ordered_paths": ordered_paths,
        "stream_order": ["optical_t1", "sar_t1", "optical_t2", "sar_t2"],
        "pairs": pair_reports,
        "max_pair_delta_hours": float(max_pair_delta_hours),
        "coregistration": "SAR reprojected/resampled to optical grid for each temporal pair",
        "scientific_guard": "No modality, timestamp, CRS, transform, or spatial overlap is fabricated.",
    }
