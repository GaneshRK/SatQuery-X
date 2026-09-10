# Stage 7 — Geospatial preprocessing and optical/SAR coregistration

This stage makes multimodal raster preparation geospatially explicit.

## What changed

- Added CRS/transform/grid inspection.
- Added CRS-aware reprojection with rasterio.
- SAR is reprojected onto the optical reference grid rather than resized by pixels.
- Spatial overlap is required.
- Missing CRS/transform is an error; the system does not invent geospatial metadata.
- Added a GeoTIFF dataset contract for optical/SAR training.
- Categorical masks use nearest-neighbour resampling; continuous imagery uses bilinear resampling.

## Why this matters

A 256x256 optical image and a 256x256 SAR image are not necessarily spatially aligned. Matching array dimensions alone does not establish correspondence between pixels. The reference grid, CRS and affine transform must agree after reprojection.

## Dataset manifest

```json
[
  {
    "optical": "data/optical_sar/scene_001_optical.tif",
    "sar": "data/optical_sar/scene_001_sar.tif",
    "mask": "data/optical_sar/scene_001_mask.tif"
  }
]
```

The files must contain real geospatial metadata. No synthetic alignment or fabricated coordinates are accepted.
