"""Dataset contract for geospatially co-registered optical/SAR training."""
from __future__ import annotations

import json
from pathlib import Path

from torch.utils.data import Dataset

from apps.geospatial.coregistration import align_optical_sar


class GeospatialOpticalSARDataset(Dataset):
    """Manifest rows: {optical, sar, mask} with real GeoTIFF paths."""
    def __init__(self, manifest: str):
        self.rows = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if not isinstance(self.rows, list) or not self.rows:
            raise ValueError("Manifest must be a non-empty JSON list.")
        for i, row in enumerate(self.rows):
            if not all(k in row for k in ("optical", "sar", "mask")):
                raise ValueError(f"Manifest row {i} must contain optical, sar and mask.")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        import numpy as np
        import rasterio
        import torch

        row = self.rows[idx]
        optical, sar, meta = align_optical_sar(row["optical"], row["sar"])
        with rasterio.open(row["mask"]) as src:
            mask = src.read(1)
            if src.crs is None or src.transform is None:
                raise ValueError(f"Mask is not georeferenced: {row['mask']}")
            with rasterio.open(row["optical"]) as ref:
                if src.crs != ref.crs or src.transform != ref.transform or src.shape != ref.shape:
                    from rasterio.warp import reproject
                    from rasterio.enums import Resampling
                    aligned = np.zeros(optical.shape[1:], dtype=mask.dtype)
                    reproject(mask, aligned, src_transform=src.transform, src_crs=src.crs,
                              dst_transform=ref.transform, dst_crs=ref.crs,
                              resampling=Resampling.nearest, src_nodata=src.nodata, dst_nodata=0)
                    mask = aligned
        if mask.shape != optical.shape[1:]:
            raise ValueError("Mask does not match the reference optical grid.")
        optical = np.nan_to_num(optical, nan=0.0, posinf=0.0, neginf=0.0)
        sar = np.nan_to_num(sar, nan=0.0, posinf=0.0, neginf=0.0)
        return torch.from_numpy(optical).float(), torch.from_numpy(sar).float(), torch.from_numpy(mask).long(), meta
