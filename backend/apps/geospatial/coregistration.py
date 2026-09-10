"""Geospatial raster alignment for multimodal remote-sensing analysis.

The functions in this module perform CRS-aware reprojection and resampling.
They never manufacture CRS, transform, resolution, or spatial overlap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RasterGrid:
    crs: Any
    transform: Any
    width: int
    height: int
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]


def inspect_grid(path: str) -> RasterGrid:
    import rasterio

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"Raster has no CRS: {path}")
        if src.transform is None:
            raise ValueError(f"Raster has no affine transform: {path}")
        if src.width <= 0 or src.height <= 0:
            raise ValueError(f"Raster dimensions are invalid: {path}")
        return RasterGrid(
            crs=src.crs,
            transform=src.transform,
            width=src.width,
            height=src.height,
            bounds=(src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top),
            resolution=(abs(src.transform.a), abs(src.transform.e)),
        )


def _bounds_intersect(a: RasterGrid, b: RasterGrid) -> bool:
    from rasterio.warp import transform_bounds

    if a.crs == b.crs:
        ab = a.bounds
        bb = b.bounds
    else:
        ab = transform_bounds(a.crs, b.crs, *a.bounds, densify_pts=21)
        bb = b.bounds
    return not (ab[2] <= bb[0] or ab[0] >= bb[2] or ab[3] <= bb[1] or ab[1] >= bb[3])


def grids_are_aligned(a: RasterGrid, b: RasterGrid, tolerance: float = 1e-6) -> bool:
    """Return True only for the same CRS/grid geometry within tolerance."""
    if a.crs != b.crs or a.width != b.width or a.height != b.height:
        return False
    ta = a.transform
    tb = b.transform
    return all(abs(x - y) <= tolerance for x, y in zip(ta[:6], tb[:6]))


def align_to_reference(
    source_path: str,
    reference_path: str,
    *,
    indexes: list[int] | None = None,
    resampling: str = "bilinear",
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reproject source raster onto the exact reference raster grid.

    The reference CRS/transform/shape are used as-is. Source CRS and
    geotransform must exist and the two scenes must overlap spatially.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    if resampling not in {"nearest", "bilinear", "cubic", "average"}:
        raise ValueError("Unsupported resampling method.")

    ref = inspect_grid(reference_path)
    src = inspect_grid(source_path)
    if not _bounds_intersect(src, ref):
        raise ValueError("Source and reference rasters do not overlap spatially.")

    with rasterio.open(source_path) as s, rasterio.open(reference_path) as r:
        bands = indexes or list(range(1, s.count + 1))
        if not bands or any(i < 1 or i > s.count for i in bands):
            raise ValueError("Requested source band index is invalid.")

        out = np.zeros((len(bands), r.height, r.width), dtype=np.float32)
        rs = getattr(Resampling, resampling)
        for out_i, band in enumerate(bands):
            reproject(
                source=rasterio.band(s, band),
                destination=out[out_i],
                src_transform=s.transform,
                src_crs=s.crs,
                dst_transform=r.transform,
                dst_crs=r.crs,
                src_nodata=s.nodata,
                dst_nodata=np.nan,
                resampling=rs,
            )

        return out, {
            "reference": reference_path,
            "source": source_path,
            "crs": r.crs.to_string(),
            "transform": list(r.transform[:6]),
            "width": r.width,
            "height": r.height,
            "resolution": [abs(r.transform.a), abs(r.transform.e)],
            "resampling": resampling,
            "source_bands": bands,
            "coregistered": True,
        }


def align_optical_sar(
    optical_path: str,
    sar_path: str,
    *,
    optical_bands: list[int] | None = None,
    sar_bands: list[int] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Align SAR to the optical grid and return float32 arrays."""
    optical, optical_meta = align_to_reference(
        optical_path,
        optical_path,
        indexes=optical_bands,
        resampling="bilinear",
    )
    sar, sar_meta = align_to_reference(
        sar_path,
        optical_path,
        indexes=sar_bands or [1],
        resampling="bilinear",
    )
    if optical.shape[1:] != sar.shape[1:]:
        raise RuntimeError("Coregistration failed to produce matching grids.")
    return optical, sar, {
        "coregistered": True,
        "reference_modality": "optical",
        "optical": optical_meta,
        "sar": sar_meta,
    }
