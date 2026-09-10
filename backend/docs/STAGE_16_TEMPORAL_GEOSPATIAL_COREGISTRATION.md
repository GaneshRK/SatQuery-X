# Stage 16 — Temporal Pairing + Geospatial Coregistration

Stage 16 makes the four-stream Optical/SAR pipeline consume spatially aligned,
temporally paired observations.

## Runtime contract

Input observations must contain:
- real local raster paths;
- explicit Optical/SAR modality metadata (or metadata already normalized by the router);
- parseable acquisition dates/timestamps;
- CRS and affine transforms in each geospatial raster;
- spatial overlap between each SAR scene and its paired optical scene.

The pipeline pairs each optical observation with the nearest unused SAR
observation within `max_pair_delta_hours` (default 72 hours). Two temporal
pairs are required. SAR is then reprojected/resampled onto the corresponding
optical grid using Rasterio bilinear resampling.

The resulting stream order is strictly:

`optical_t1, sar_t1, optical_t2, sar_t2`

## Scientific safeguards

- Missing modality is an error, not a guess.
- Missing/invalid dates are an error.
- Missing CRS/transform is an error.
- Non-overlapping scenes are rejected.
- The input optical grid is used as the reference; its metadata is not invented.
- Temporal pairing uses actual acquisition timestamps rather than list order.
- The derived SAR rasters are explicit GeoTIFF artifacts and retain source/reference provenance in the execution result.

## Agent integration

For `TEMPORAL_CROSS_MODAL`, the planner now runs:

1. metadata resolution;
2. modality routing;
3. temporal Optical/SAR pairing + coregistration;
4. native four-stream temporal Optical/SAR VQA;
5. evidence fusion.

If the required evidence cannot be formed, the pipeline stops with an
insufficient/failed result instead of feeding mismatched imagery to the model.

## Configuration

The temporal pairing tolerance is currently passed as a plan parameter:
`max_pair_delta_hours=72.0`.

No satellite-specific revisit interval or pixel size is assumed.
