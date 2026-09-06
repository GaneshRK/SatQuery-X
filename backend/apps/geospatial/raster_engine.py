"""
Production raster processing engine for SatQuery-X.

Responsibilities:
- raster inspection
- validation
- windowed reads
- geometry clipping
- spectral-index generation
- statistics
- XYZ tile rendering

Scientific principle:
The engine never invents geospatial metadata or sensor band mappings.
"""

from __future__ import annotations

import math
import os
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from apps.geospatial.indices import (
    compute_mndwi,
    compute_nbr,
    compute_ndbi,
    compute_ndvi,
    compute_ndwi,
)
from apps.geospatial.sensor_profiles import (
    get_sensor_profile,
)


class RasterEngine:
    """
    Raster processing service.

    All methods are static to preserve compatibility with existing
    callers in the Django application.
    """

    @staticmethod
    def inspect(
        filepath: str,
    ) -> dict[str, Any]:
        import rasterio

        if not os.path.isfile(filepath):
            raise FileNotFoundError(
                f"Raster file does not exist: {filepath}"
            )

        with rasterio.open(
            filepath
        ) as src:

            bounds = src.bounds

            return {
                "filepath": filepath,
                "width": int(src.width),
                "height": int(src.height),
                "band_count": int(src.count),
                "dtypes": [
                    str(dtype)
                    for dtype in src.dtypes
                ],
                "crs": (
                    src.crs.to_string()
                    if src.crs
                    else None
                ),
                "transform": list(
                    src.transform[:6]
                ),
                "bounds": {
                    "west": float(
                        bounds.left
                    ),
                    "south": float(
                        bounds.bottom
                    ),
                    "east": float(
                        bounds.right
                    ),
                    "north": float(
                        bounds.top
                    ),
                },
                "nodata": (
                    float(src.nodata)
                    if src.nodata is not None
                    else None
                ),
                "is_tiled": bool(
                    src.profile.get(
                        "tiled",
                        False,
                    )
                ),
                "is_cog": (
                    bool(
                        src.profile.get(
                            "tiled",
                            False,
                        )
                    )
                    and any(
                        src.overviews(
                            band
                        )
                        for band in range(
                            1,
                            src.count + 1,
                        )
                    )
                ),
                "overviews": {
                    str(band): src.overviews(
                        band
                    )
                    for band in range(
                        1,
                        src.count + 1,
                    )
                },
                "block_shapes": [
                    list(shape)
                    if shape
                    else None
                    for shape in src.block_shapes
                ],
            }

    @staticmethod
    def validate_raster(
        filepath: str,
    ) -> tuple[bool, str]:
        import rasterio
        from rasterio.windows import Window

        if not os.path.isfile(filepath):
            return (
                False,
                f"File does not exist: {filepath}",
            )

        try:
            with rasterio.open(
                filepath
            ) as src:

                if src.width <= 0:
                    return (
                        False,
                        "Raster width is invalid.",
                    )

                if src.height <= 0:
                    return (
                        False,
                        "Raster height is invalid.",
                    )

                if src.count <= 0:
                    return (
                        False,
                        "Raster contains no bands.",
                    )

                window_width = min(
                    16,
                    src.width,
                )

                window_height = min(
                    16,
                    src.height,
                )

                src.read(
                    1,
                    window=Window(
                        0,
                        0,
                        window_width,
                        window_height,
                    ),
                )

                return (
                    True,
                    "Raster is valid and readable.",
                )

        except Exception as exc:
            return (
                False,
                f"Raster validation failed: {exc}",
            )

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

        if width <= 0 or height <= 0:
            raise ValueError(
                "Window width and height must be positive."
            )

        with rasterio.open(
            filepath
        ) as src:

            if col_off < 0 or row_off < 0:
                raise ValueError(
                    "Window offsets cannot be negative."
                )

            if col_off >= src.width:
                raise ValueError(
                    "Window starts outside raster width."
                )

            if row_off >= src.height:
                raise ValueError(
                    "Window starts outside raster height."
                )

            actual_width = min(
                width,
                src.width - col_off,
            )

            actual_height = min(
                height,
                src.height - row_off,
            )

            if bands is None:
                indexes = list(
                    range(
                        1,
                        src.count + 1,
                    )
                )
            else:
                indexes = bands

                invalid = [
                    band
                    for band in indexes
                    if band < 1
                    or band > src.count
                ]

                if invalid:
                    raise ValueError(
                        f"Invalid raster band(s): {invalid}"
                    )

            return src.read(
                indexes,
                window=Window(
                    col_off,
                    row_off,
                    actual_width,
                    actual_height,
                ),
            )

    @staticmethod
    def clip_by_geometry(
        src_filepath: str,
        dst_filepath: str,
        geometry: dict[str, Any],
        crop: bool = True,
    ) -> dict[str, Any]:

        import rasterio
        from rasterio.mask import mask
        from shapely.geometry import shape

        if not geometry:
            raise ValueError(
                "Geometry is required."
            )

        output_dir = os.path.dirname(
            os.path.abspath(
                dst_filepath
            )
        )

        os.makedirs(
            output_dir,
            exist_ok=True,
        )

        geom = shape(
            geometry
        )

        if geom.is_empty:
            raise ValueError(
                "Input geometry is empty."
            )

        if not geom.is_valid:
            geom = geom.buffer(0)

        with rasterio.open(
            src_filepath
        ) as src:

            if src.crs is None:
                raise ValueError(
                    "Cannot clip a raster without CRS metadata."
                )

            out_image, out_transform = mask(
                src,
                [
                    geom
                ],
                crop=crop,
                filled=True,
            )

            out_meta = src.meta.copy()

            out_meta.update(
                {
                    "driver": "GTiff",
                    "height": int(
                        out_image.shape[1]
                    ),
                    "width": int(
                        out_image.shape[2]
                    ),
                    "transform": out_transform,
                }
            )

            with rasterio.open(
                dst_filepath,
                "w",
                **out_meta,
            ) as dst:

                dst.write(
                    out_image
                )

        return RasterEngine.inspect(
            dst_filepath
        )

    @staticmethod
    def compute_index(
        filepath: str,
        index_name: str,
        out_filepath: str | None = None,
        sensor_name: str | None = None,
        modality: str = "MULTISPECTRAL",
    ) -> dict[str, Any]:

        import rasterio

        index = (
            index_name
            .strip()
            .upper()
        )

        supported = {
            "NDVI",
            "NDWI",
            "MNDWI",
            "NDBI",
            "NBR",
        }

        if index not in supported:
            raise ValueError(
                f"Unsupported index '{index_name}'. "
                f"Supported: {sorted(supported)}"
            )

        with rasterio.open(
            filepath
        ) as src:

            data = src.read()

            if sensor_name is None:
                tags = src.tags()

                sensor_name = (
                    tags.get(
                        "SENSOR"
                    )
                    or tags.get(
                        "sensor"
                    )
                )

            profile = get_sensor_profile(
                sensor_name,
                modality,
            )

            if not profile.bands:
                raise ValueError(
                    "A verified sensor profile is required for "
                    f"{index} when the raster's band semantics are unknown."
                )

            band_count = src.count

            def band(
                semantic: str,
            ) -> np.ndarray:

                index_zero = (
                    profile.get_band_index(
                        semantic,
                        band_count,
                    )
                )

                if index_zero is None:
                    raise ValueError(
                        f"Sensor '{profile.sensor_id}' does not provide "
                        f"a verified '{semantic}' band for this raster."
                    )

                return data[
                    index_zero
                ].astype(
                    np.float32
                )

            if index == "NDVI":
                result = compute_ndvi(
                    band("red"),
                    band("nir"),
                )

            elif index == "NDWI":
                result = compute_ndwi(
                    band("green"),
                    band("nir"),
                )

            elif index == "MNDWI":
                result = compute_mndwi(
                    band("green"),
                    band("swir"),
                )

            elif index == "NDBI":
                result = compute_ndbi(
                    band("swir"),
                    band("nir"),
                )

            elif index == "NBR":
                result = compute_nbr(
                    band("nir"),
                    band("swir2"),
                )

            else:
                raise RuntimeError(
                    f"Unhandled index: {index}"
                )

            valid_mask = np.isfinite(
                result
            )

            nodata_mask = None

            if src.nodata is not None:
                nodata_mask = np.all(
                    data == src.nodata,
                    axis=0,
                )

                valid_mask &= ~nodata_mask

            valid_values = result[
                valid_mask
            ]

            statistics = {
                "index": index,
                "min": (
                    float(
                        np.min(
                            valid_values
                        )
                    )
                    if valid_values.size
                    else None
                ),
                "max": (
                    float(
                        np.max(
                            valid_values
                        )
                    )
                    if valid_values.size
                    else None
                ),
                "mean": (
                    float(
                        np.mean(
                            valid_values
                        )
                    )
                    if valid_values.size
                    else None
                ),
                "median": (
                    float(
                        np.median(
                            valid_values
                        )
                    )
                    if valid_values.size
                    else None
                ),
                "std": (
                    float(
                        np.std(
                            valid_values
                        )
                    )
                    if valid_values.size
                    else None
                ),
                "valid_pixels": int(
                    valid_values.size
                ),
                "total_pixels": int(
                    result.size
                ),
                "valid_pct": round(
                    (
                        valid_values.size
                        / result.size
                        * 100.0
                    )
                    if result.size
                    else 0.0,
                    4,
                ),
                "sensor": profile.sensor_id,
                "modality": profile.modality,
            }

            if out_filepath:
                output_dir = os.path.dirname(
                    os.path.abspath(
                        out_filepath
                    )
                )

                os.makedirs(
                    output_dir,
                    exist_ok=True,
                )

                output = result.astype(
                    np.float32
                ).copy()

                output[
                    ~valid_mask
                ] = np.nan

                metadata = src.meta.copy()

                metadata.update(
                    {
                        "driver": "GTiff",
                        "dtype": "float32",
                        "count": 1,
                        "nodata": np.nan,
                    }
                )

                with rasterio.open(
                    out_filepath,
                    "w",
                    **metadata,
                ) as dst:

                    dst.write(
                        output,
                        1,
                    )

                statistics[
                    "output_file"
                ] = out_filepath

            return statistics

    @staticmethod
    def render_tile_png(
        filepath: str,
        z: int,
        x: int,
        y: int,
        layer: str = "rgb",
    ) -> bytes:

        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import Window, from_bounds
        from rasterio.warp import transform_bounds

        if z < 0:
            raise ValueError(
                "Zoom level cannot be negative."
            )

        n = 2.0 ** z

        lon_west = (
            x / n * 360.0
            - 180.0
        )

        lon_east = (
            (x + 1)
            / n
            * 360.0
            - 180.0
        )

        lat_north = math.degrees(
            math.atan(
                math.sinh(
                    math.pi
                    * (
                        1
                        - 2 * y / n
                    )
                )
            )
        )

        lat_south = math.degrees(
            math.atan(
                math.sinh(
                    math.pi
                    * (
                        1
                        - 2 * (y + 1) / n
                    )
                )
            )
        )

        layer_name = (
            layer
            .strip()
            .lower()
        )

        supported_layers = {
            "rgb",
            "ndvi",
            "ndwi",
            "mndwi",
            "ndbi",
        }

        if layer_name not in supported_layers:
            raise ValueError(
                f"Unsupported tile layer '{layer}'. "
                f"Supported: {sorted(supported_layers)}"
            )

        with rasterio.open(
            filepath
        ) as src:

            if src.crs is None:
                return _transparent_tile()

            try:
                native_bounds = transform_bounds(
                    "EPSG:4326",
                    src.crs,
                    lon_west,
                    lat_south,
                    lon_east,
                    lat_north,
                )
            except Exception:
                return _transparent_tile()

            left, bottom, right, top = (
                native_bounds
            )

            if (
                right < src.bounds.left
                or left > src.bounds.right
                or top < src.bounds.bottom
                or bottom > src.bounds.top
            ):
                return _transparent_tile()

            window = from_bounds(
                left,
                bottom,
                right,
                top,
                src.transform,
            )

            window = window.intersection(
                Window(
                    0,
                    0,
                    src.width,
                    src.height,
                )
            )

            if (
                window.width <= 0
                or window.height <= 0
            ):
                return _transparent_tile()

            data = src.read(
                window=window,
                out_shape=(
                    src.count,
                    256,
                    256,
                ),
                resampling=Resampling.bilinear,
                masked=True,
            )

            if layer_name == "rgb":
                return _render_rgb_tile(
                    data
                )

            return _render_index_tile(
                data,
                layer_name,
            )


def _transparent_tile() -> bytes:
    image = Image.new(
        "RGBA",
        (
            256,
            256,
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )

    output = BytesIO()

    image.save(
        output,
        format="PNG",
    )

    return output.getvalue()


def _normalize_display(
    array: np.ndarray,
) -> np.ndarray:

    if np.ma.isMaskedArray(
        array
    ):
        values = array.compressed()
    else:
        values = array[
            np.isfinite(array)
        ]

    if values.size == 0:
        return np.zeros(
            array.shape,
            dtype=np.uint8,
        )

    low, high = np.percentile(
        values,
        (
            2.0,
            98.0,
        ),
    )

    if high <= low:
        return np.zeros(
            array.shape,
            dtype=np.uint8,
        )

    normalized = (
        (
            array
            - low
        )
        / (
            high
            - low
        )
    )

    normalized = np.clip(
        normalized,
        0.0,
        1.0,
    )

    return (
        normalized
        * 255.0
    ).astype(
        np.uint8
    )


def _render_rgb_tile(
    data,
) -> bytes:

    bands = data.shape[0]

    if bands >= 3:
        red = _normalize_display(
            data[2]
        )

        green = _normalize_display(
            data[1]
        )

        blue = _normalize_display(
            data[0]
        )

    elif bands == 2:
        red = _normalize_display(
            data[0]
        )

        green = _normalize_display(
            data[1]
        )

        blue = (
            (
                red.astype(
                    np.uint16
                )
                + green.astype(
                    np.uint16
                )
            )
            // 2
        ).astype(
            np.uint8
        )

    elif bands == 1:
        gray = _normalize_display(
            data[0]
        )

        red = gray
        green = gray
        blue = gray

    else:
        return _transparent_tile()

    if np.ma.isMaskedArray(
        data
    ):
        mask = np.any(
            np.ma.getmaskarray(
                data
            ),
            axis=0,
        )

        alpha = np.where(
            mask,
            0,
            255,
        ).astype(
            np.uint8
        )
    else:
        alpha = np.full(
            (
                256,
                256,
            ),
            255,
            dtype=np.uint8,
        )

    rgba = np.dstack(
        [
            red,
            green,
            blue,
            alpha,
        ]
    )

    image = Image.fromarray(
        rgba,
        mode="RGBA",
    )

    output = BytesIO()

    image.save(
        output,
        format="PNG",
    )

    return output.getvalue()


def _render_index_tile(
    data,
    layer_name: str,
) -> bytes:

    if data.shape[0] < 2:
        return _transparent_tile()

    try:
        # These tile layers are intended for visualization only.
        # Exact band mapping must be supplied by a caller using a known
        # sensor profile. The generic renderer therefore uses common
        # multispectral layouts only when enough bands are available.
        if layer_name == "ndvi":
            if data.shape[0] < 4:
                return _transparent_tile()

            red = data[2].astype(
                np.float32
            )

            nir = data[3].astype(
                np.float32
            )

            index = np.divide(
                nir - red,
                nir + red,
                out=np.full_like(
                    nir,
                    np.nan,
                ),
                where=np.abs(
                    nir + red
                )
                > np.finfo(
                    np.float32
                ).eps,
            )

        elif layer_name == "ndwi":
            if data.shape[0] < 4:
                return _transparent_tile()

            green = data[1].astype(
                np.float32
            )

            nir = data[3].astype(
                np.float32
            )

            index = np.divide(
                green - nir,
                green + nir,
                out=np.full_like(
                    green,
                    np.nan,
                ),
                where=np.abs(
                    green + nir
                )
                > np.finfo(
                    np.float32
                ).eps,
            )

        elif layer_name == "mndwi":
            if data.shape[0] < 11:
                return _transparent_tile()

            green = data[1].astype(
                np.float32
            )

            swir = data[10].astype(
                np.float32
            )

            index = np.divide(
                green - swir,
                green + swir,
                out=np.full_like(
                    green,
                    np.nan,
                ),
                where=np.abs(
                    green + swir
                )
                > np.finfo(
                    np.float32
                ).eps,
            )

        elif layer_name == "ndbi":
            if data.shape[0] < 4:
                return _transparent_tile()

            nir = data[3].astype(
                np.float32
            )

            swir = data[
                10
                if data.shape[0] >= 11
                else data.shape[0] - 1
            ].astype(
                np.float32
            )

            index = np.divide(
                swir - nir,
                swir + nir,
                out=np.full_like(
                    nir,
                    np.nan,
                ),
                where=np.abs(
                    swir + nir
                )
                > np.finfo(
                    np.float32
                ).eps,
            )

        else:
            return _transparent_tile()

    except Exception:
        return _transparent_tile()

    valid = index[
        np.isfinite(index)
    ]

    if valid.size == 0:
        return _transparent_tile()

    # Visualization range only.
    low, high = np.percentile(
        valid,
        (
            2.0,
            98.0,
        ),
    )

    if high <= low:
        return _transparent_tile()

    normalized = np.clip(
        (
            index
            - low
        )
        / (
            high
            - low
        ),
        0.0,
        1.0,
    )

    red = (
        (1.0 - normalized)
        * 255
    ).astype(
        np.uint8
    )

    green = (
        normalized
        * 255
    ).astype(
        np.uint8
    )

    blue = np.full(
        index.shape,
        80,
        dtype=np.uint8,
    )

    alpha = np.where(
        np.isfinite(index),
        220,
        0,
    ).astype(
        np.uint8
    )

    rgba = np.dstack(
        [
            red,
            green,
            blue,
            alpha,
        ]
    )

    image = Image.fromarray(
        rgba,
        mode="RGBA",
    )

    output = BytesIO()

    image.save(
        output,
        format="PNG",
    )

    return output.getvalue()