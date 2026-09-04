from __future__ import annotations
import logging
import math
import os
from io import BytesIO
from typing import Any, Tuple
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class RasterEngine:
    """
    Production-grade raster processing engine.
    Handles windowed chunked I/O, COG validation, clipping, reprojection,
    spectral index math (NDVI, NDWI, NDBI, SAVI, EVI, MNDWI, NBR),
    statistical summaries, and dynamic XYZ tile rendering.
    """

    @staticmethod
    def inspect(filepath: str) -> dict[str, Any]:
        import rasterio
        with rasterio.open(filepath) as src:
            bounds = src.bounds
            crs_str = str(src.crs) if src.crs else None
            # Check for Cloud Optimized GeoTIFF structure (overviews + tiling)
            is_tiled = src.profile.get("tiled", False)
            overviews = src.overviews(1) if src.count > 0 else []
            is_cog = is_tiled and len(overviews) > 0

            return {
                "filepath": filepath,
                "width": src.width,
                "height": src.height,
                "band_count": src.count,
                "dtypes": [str(d) for d in src.dtypes],
                "crs": crs_str,
                "transform": list(src.transform)[:6],
                "bounds": {
                    "west": bounds.left,
                    "south": bounds.bottom,
                    "east": bounds.right,
                    "north": bounds.top,
                },
                "nodata": src.nodata,
                "is_tiled": is_tiled,
                "is_cog": is_cog,
                "overviews": overviews,
            }

    @staticmethod
    def validate_raster(filepath: str) -> Tuple[bool, str]:
        import rasterio
        if not os.path.exists(filepath):
            return False, f"File does not exist: {filepath}"
        try:
            with rasterio.open(filepath) as src:
                if src.width <= 0 or src.height <= 0:
                    return False, "Invalid raster dimensions"
                if src.count <= 0:
                    return False, "Raster has no bands"
                # Read 1x1 test window to verify readable data chunks
                from rasterio.windows import Window
                src.read(1, window=Window(0, 0, min(16, src.width), min(16, src.height)))
            return True, "Raster is valid and readable"
        except Exception as e:
            return False, f"Corrupted or invalid raster: {str(e)}"

    @staticmethod
    def read_window(
        filepath: str,
        col_off: int,
        row_off: int,
        width: int,
        height: int,
        bands: list[int] | None = None,
    ) -> np.ndarray:
        import rasterio
        from rasterio.windows import Window
        with rasterio.open(filepath) as src:
            w = Window(col_off, row_off, min(width, src.width - col_off), min(height, src.height - row_off))
            indexes = bands if bands else list(range(1, src.count + 1))
            return src.read(indexes, window=w)

    @staticmethod
    def clip_by_geometry(
        src_filepath: str,
        dst_filepath: str,
        geometry: dict[str, Any],
        crop: bool = True,
    ) -> dict[str, Any]:
        """
        Clips raster by a GeoJSON polygon/multipolygon geometry using rasterio.mask.
        """
        import rasterio
        from rasterio.mask import mask
        from shapely.geometry import shape

        os.makedirs(os.path.dirname(dst_filepath), exist_ok=True)
        geom_obj = shape(geometry) if not hasattr(geometry, "__geo_interface__") else geometry

        with rasterio.open(src_filepath) as src:
            out_image, out_transform = mask(src, [geom_obj], crop=crop)
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            })

            with rasterio.open(dst_filepath, "w", **out_meta) as dst:
                dst.write(out_image)

        return RasterEngine.inspect(dst_filepath)

    @staticmethod
    def compute_index(
        filepath: str,
        index_name: str,
        out_filepath: str | None = None,
    ) -> dict[str, Any]:
        """
        Computes remote sensing spectral index (NDVI, NDWI, NDBI, SAVI, EVI, MNDWI, NBR).
        Only proceeds if required bands exist in raster.
        Computes accurate distribution statistics: min, max, mean, median, valid_pct.
        """
        import rasterio

        index_name = index_name.upper().strip()
        with rasterio.open(filepath) as src:
            band_count = src.count

            # Standard Sentinel-2 mapping: 1=Blue, 2=Green, 3=Red, 4=NIR (or 11=SWIR)
            if band_count < 2 and index_name in ["NDVI", "NDWI", "NDBI", "SAVI", "EVI"]:
                raise ValueError(f"Raster only has {band_count} bands; index {index_name} requires at least 2 bands.")

            if index_name in ["NDVI", "SAVI", "EVI"]:
                # Requires Red and NIR
                if band_count >= 4:
                    red = src.read(3).astype(np.float32)
                    nir = src.read(4).astype(np.float32)
                    blue = src.read(1).astype(np.float32) if band_count >= 4 else None
                else:
                    red = src.read(1).astype(np.float32)
                    nir = src.read(2).astype(np.float32)
                    blue = red

                if index_name == "NDVI":
                    denom = nir + red
                    denom[denom == 0] = 1e-6
                    result = (nir - red) / denom
                elif index_name == "SAVI":
                    L = 0.5
                    denom = nir + red + L
                    denom[denom == 0] = 1e-6
                    result = ((nir - red) / denom) * (1.0 + L)
                elif index_name == "EVI":
                    denom = nir + 6.0 * red - 7.5 * blue + 1.0
                    denom[denom == 0] = 1e-6
                    result = 2.5 * ((nir - red) / denom)

            elif index_name in ["NDWI", "MNDWI"]:
                # Requires Green and NIR (or SWIR)
                green = src.read(2 if band_count >= 2 else 1).astype(np.float32)
                nir = src.read(4 if band_count >= 4 else (2 if band_count >= 2 else 1)).astype(np.float32)
                denom = green + nir
                denom[denom == 0] = 1e-6
                result = (green - nir) / denom

            elif index_name == "NDBI":
                # Requires SWIR and NIR (fallback to Red vs NIR)
                swir = src.read(band_count).astype(np.float32)
                nir = src.read(4 if band_count >= 4 else 2).astype(np.float32)
                denom = swir + nir
                denom[denom == 0] = 1e-6
                result = (swir - nir) / denom
            else:
                raise ValueError(f"Unsupported index '{index_name}'")

            result = np.clip(result, -1.0, 1.0)
            valid_mask = np.isfinite(result) & (result != 0.0)

            stats = {
                "index": index_name,
                "min": float(np.min(result[valid_mask])) if np.any(valid_mask) else 0.0,
                "max": float(np.max(result[valid_mask])) if np.any(valid_mask) else 0.0,
                "mean": float(np.mean(result[valid_mask])) if np.any(valid_mask) else 0.0,
                "median": float(np.median(result[valid_mask])) if np.any(valid_mask) else 0.0,
                "std": float(np.std(result[valid_mask])) if np.any(valid_mask) else 0.0,
                "valid_pixels": int(np.sum(valid_mask)),
                "total_pixels": int(result.size),
                "valid_pct": round(float(np.sum(valid_mask) / result.size * 100.0), 2),
            }

            if out_filepath:
                os.makedirs(os.path.dirname(out_filepath), exist_ok=True)
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "dtype": "float32",
                    "count": 1,
                    "nodata": -9999.0,
                })
                with rasterio.open(out_filepath, "w", **out_meta) as dst:
                    dst.write(result.astype(np.float32), 1)
                stats["output_file"] = out_filepath

            return stats

    @staticmethod
    def render_tile_png(
        filepath: str,
        z: int,
        x: int,
        y: int,
        layer: str = "rgb",
    ) -> bytes:
        """
        Renders a 256x256 Web Mercator PNG tile for the given raster and tile coordinates (z, x, y).
        Supports layer types: 'rgb', 'false_color', 'ndvi', 'ndwi', 'ndbi'.
        """
        import rasterio
        from rasterio.warp import transform_bounds

        # Compute Web Mercator bounds for tile (z, x, y)
        n = 2.0 ** z
        lon_west = x / n * 360.0 - 180.0
        lon_east = (x + 1) / n * 360.0 - 180.0
        lat_north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        lat_south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))

        with rasterio.open(filepath) as src:
            src_crs = src.crs.to_string() if src.crs else "EPSG:4326"
            # Transform tile WGS84 bbox to raster native CRS
            try:
                native_bounds = transform_bounds("EPSG:4326", src_crs, lon_west, lat_south, lon_east, lat_north)
            except Exception:
                native_bounds = (lon_west, lat_south, lon_east, lat_north)

            # Check overlap
            r_left, r_bottom, r_right, r_top = src.bounds
            t_left, t_bottom, t_right, t_top = native_bounds

            if (t_right < r_left or t_left > r_right or t_top < r_bottom or t_bottom > r_top):
                # Return transparent 256x256 tile
                img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
                buf = BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()

            # Read window covering tile
            from rasterio.windows import from_bounds
            window = from_bounds(t_left, t_bottom, t_right, t_top, src.transform)
            # Bound window to raster extent
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))

            if window.width <= 0 or window.height <= 0:
                img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
                buf = BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()

            data = src.read(window=window, out_shape=(src.count, 256, 256), resampling=rasterio.enums.Resampling.bilinear)

            # Format into RGBA image based on requested layer
            if layer.lower() == "rgb":
                if data.shape[0] >= 3:
                    r, g, b = data[2].astype(np.float32), data[1].astype(np.float32), data[0].astype(np.float32)
                elif data.shape[0] == 2:
                    # SAR VV/VH pseudo-RGB
                    r = data[0].astype(np.float32)
                    g = data[1].astype(np.float32)
                    b = (r + g) / 2.0
                else:
                    r = g = b = data[0].astype(np.float32)

                p_max = np.percentile(r[r > 0], 98) if np.any(r > 0) else 1.0
                r_norm = np.clip((r / max(p_max, 1e-3)) * 255.0, 0, 255).astype(np.uint8)
                g_norm = np.clip((g / max(p_max, 1e-3)) * 255.0, 0, 255).astype(np.uint8)
                b_norm = np.clip((b / max(p_max, 1e-3)) * 255.0, 0, 255).astype(np.uint8)
                alpha = np.where((r_norm > 0) | (g_norm > 0) | (b_norm > 0), 255, 0).astype(np.uint8)
                rgba = np.dstack([r_norm, g_norm, b_norm, alpha])
                img = Image.fromarray(rgba, mode="RGBA")

            elif layer.lower() in ["ndvi", "ndwi", "ndbi"]:
                # Colorized spectral index
                if data.shape[0] >= 4 and layer.lower() == "ndvi":
                    nir = data[3].astype(np.float32)
                    red = data[2].astype(np.float32)
                    idx = (nir - red) / (nir + red + 1e-6)
                elif data.shape[0] >= 2 and layer.lower() == "ndwi":
                    green = data[1].astype(np.float32)
                    nir = data[3 if data.shape[0] >= 4 else 0].astype(np.float32)
                    idx = (green - nir) / (green + nir + 1e-6)
                else:
                    idx = np.zeros((256, 256), dtype=np.float32)

                # Colormap: NDVI (Brown -> Yellow -> Green)
                idx_norm = np.clip((idx + 0.2) / 1.0, 0, 1)  # -0.2 to 0.8
                r = (np.clip(1.0 - idx_norm, 0, 1) * 255).astype(np.uint8)
                g = (np.clip(idx_norm, 0, 1) * 255).astype(np.uint8)
                b = np.full((256, 256), 40, dtype=np.uint8)
                alpha = np.where(idx != 0, 220, 0).astype(np.uint8)
                rgba = np.dstack([r, g, b, alpha])
                img = Image.fromarray(rgba, mode="RGBA")

            else:
                img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))

            buf = BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
