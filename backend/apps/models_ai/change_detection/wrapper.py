"""
CHANGE_DETECTION specialist model wrapper.

Production-oriented bi-temporal remote-sensing change detection.

Pipeline
--------
T1 + T2
  ↓
Input validation
  ↓
Image loading
  ↓
Registration / dimension validation
  ↓
Sensor-aware normalization when metadata is available
  ↓
Optional trained neural model
  ↓
Deterministic image-difference evidence fallback
  ↓
Data-driven thresholding
  ↓
Morphological filtering
  ↓
Connected components
  ↓
Geospatial polygons when CRS/geotransform are available
  ↓
Grounded change statistics
  ↓
ModelOutput

Important scientific guarantees
-------------------------------
- Never assumes Sentinel-2 merely from an image having 3/4 bands.
- Never assumes 10 m pixels.
- Never invents CRS, transform, bounds, area, or coordinates.
- An untrained neural network is NEVER used as a scientific model.
- A trained model is used only when explicitly configured and loaded.
- Area is calculated only when real pixel geometry is available.
- Geographic CRS area is calculated geodesically when possible.
- If geospatial metadata is unavailable, the result remains pixel-based.
- The wrapper does not claim semantic classes such as "building" or
  "deforestation" from a generic pixel-difference map.
- VQA/reasoning layers should consume this structured evidence rather than
  independently inventing measurements.

Environment variables
---------------------
CHANGE_DETECTION_MODEL_PATH
    Optional path to a TorchScript model.

CHANGE_DETECTION_CHECKPOINT
    Optional path to a SatQuery SiameseChangeNet checkpoint (.pt/.pth).

CHANGE_DETECTION_MODEL_TYPE
    `siamese` loads the project's trained SiameseChangeNet checkpoint.

CHANGE_DETECTION_DEVICE
    Optional torch device. Defaults to "cuda" when available, otherwise CPU.

CHANGE_DETECTION_THRESHOLD
    Optional fixed threshold in probability space [0, 1] when a trained model
    is used. If absent, Otsu thresholding is applied to the model probability.

CHANGE_DETECTION_MIN_COMPONENT_PIXELS
    Minimum connected-component size. Defaults to 20.

CHANGE_DETECTION_MAX_COMPONENTS
    Maximum number of reported components. Defaults to 100.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from apps.agent.contracts import ModelInput, ModelOutput

logger = logging.getLogger(__name__)

try:
    import torch

    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

try:
    import rasterio
    from rasterio.features import shapes as rasterio_shapes
    from rasterio.transform import Affine

    HAS_RASTERIO = True
except ImportError:
    rasterio = None
    rasterio_shapes = None
    Affine = None
    HAS_RASTERIO = False

try:
    from pyproj import Geod

    HAS_PYPROJ = True
except ImportError:
    Geod = None
    HAS_PYPROJ = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MIN_COMPONENT_PIXELS = 20
DEFAULT_MAX_COMPONENTS = 100

# These values are algorithmic parameters, NOT scientific measurements.
DEFAULT_OTSU_BINS = 256


def _load_calibration_temperature() -> float | None:
    """Load an empirically fitted temperature; never invent one at runtime."""
    path = os.getenv("CHANGE_DETECTION_CALIBRATION", "").strip()
    if not path:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        temperature = float(payload["temperature"])
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("temperature must be finite and > 0")
        return temperature
    except Exception as exc:
        logger.warning("Ignoring invalid change-detection calibration artifact: %s", exc)
        return None

MIN_THRESHOLD = 1e-6
MAX_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        if not math.isfinite(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _get_param(inputs: ModelInput, key: str, default: Any = None) -> Any:
    params = getattr(inputs, "params", None)
    if not isinstance(params, dict):
        return default
    return params.get(key, default)


def _as_numpy_array(image: Image.Image) -> np.ndarray:
    """
    Convert PIL image to float32 HWC RGB array in [0, 1].
    """
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _normalize_image_array(array: np.ndarray) -> np.ndarray:
    """
    Robust per-channel percentile normalization.

    This is intended for display/image-difference normalization only.
    It does not claim to convert arbitrary imagery into physical reflectance.
    """
    arr = np.asarray(array, dtype=np.float32)

    if arr.ndim == 2:
        arr = arr[:, :, None]

    if arr.ndim != 3:
        raise ValueError(f"Expected 2D or 3D image array, got shape {arr.shape}")

    normalized = np.zeros_like(arr, dtype=np.float32)

    for channel in range(arr.shape[2]):
        band = arr[:, :, channel]

        finite = np.isfinite(band)
        if not np.any(finite):
            continue

        values = band[finite]

        low = float(np.percentile(values, 2))
        high = float(np.percentile(values, 98))

        if high <= low:
            minimum = float(np.min(values))
            maximum = float(np.max(values))

            if maximum > minimum:
                low = minimum
                high = maximum
            else:
                normalized[:, :, channel] = 0.0
                continue

        channel_out = (band - low) / (high - low)
        channel_out = np.clip(channel_out, 0.0, 1.0)

        channel_out[~finite] = 0.0
        normalized[:, :, channel] = channel_out

    return normalized


def _ensure_rgb(array: np.ndarray) -> np.ndarray:
    """
    Convert arbitrary image arrays to a 3-channel representation.

    This is a visualization-compatible representation. It must not be
    interpreted as a physically meaningful RGB composition for arbitrary
    multispectral imagery.
    """
    arr = np.asarray(array, dtype=np.float32)

    if arr.ndim == 2:
        arr = arr[:, :, None]

    if arr.ndim != 3:
        raise ValueError(f"Unsupported image shape: {arr.shape}")

    channels = arr.shape[2]

    if channels == 1:
        return np.repeat(arr, 3, axis=2)

    if channels == 2:
        return np.concatenate(
            [
                arr[:, :, 0:1],
                arr[:, :, 1:2],
                arr[:, :, 0:1],
            ],
            axis=2,
        )

    return arr[:, :, :3]


def _resize_array(
    array: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray:
    """
    Resize a numeric image through PIL.

    Used only when explicitly required for model/input compatibility.
    """
    arr = np.asarray(array, dtype=np.float32)

    normalized = _normalize_image_array(arr)
    rgb = _ensure_rgb(normalized)

    image = Image.fromarray(
        np.clip(rgb * 255.0, 0, 255).astype(np.uint8),
        mode="RGB",
    )

    resized = image.resize(
        (width, height),
        Image.Resampling.BILINEAR,
    )

    return np.asarray(resized, dtype=np.float32) / 255.0


def _load_image_bytes(data: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")
    except Exception:
        logger.exception("Failed to decode image bytes")
        return None


def _load_image_path(path: str | Path) -> Image.Image | None:
    file_path = Path(path)

    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        with Image.open(file_path) as image:
            return image.convert("RGB")
    except Exception:
        logger.exception("Failed to decode image path: %s", file_path)
        return None


def _load_pair(
    inputs: ModelInput,
) -> tuple[Image.Image | None, Image.Image | None]:
    """
    Load T1 and T2 from ModelInput.

    The wrapper expects the first two image inputs to represent T1 and T2.
    The planner/orchestrator is responsible for ensuring that they are
    correctly ordered.
    """
    image_bytes = getattr(inputs, "image_bytes", None)

    if image_bytes and len(image_bytes) >= 2:
        return (
            _load_image_bytes(image_bytes[0]),
            _load_image_bytes(image_bytes[1]),
        )

    image_paths = getattr(inputs, "image_paths", None)

    if image_paths and len(image_paths) >= 2:
        return (
            _load_image_path(image_paths[0]),
            _load_image_path(image_paths[1]),
        )

    return None, None


# ---------------------------------------------------------------------------
# Thresholding
# ---------------------------------------------------------------------------


def compute_otsu_threshold(
    values: np.ndarray,
) -> tuple[float, float]:
    """
    Compute an Otsu threshold over normalized difference values.

    Returns
    -------
    threshold:
        Threshold in the same [0, 1] scale as the input.

    separability:
        Between-class variance / total variance, bounded to [0, 1].

    No fixed scientific threshold is injected here.
    """
    values = np.asarray(values, dtype=np.float32)

    values = values[np.isfinite(values)]

    if values.size == 0:
        return 1.0, 0.0

    values = np.clip(values, 0.0, 1.0)

    if np.allclose(values, values[0]):
        return float(values[0]), 0.0

    histogram, bin_edges = np.histogram(
        values,
        bins=DEFAULT_OTSU_BINS,
        range=(0.0, 1.0),
    )

    histogram = histogram.astype(np.float64)

    total = histogram.sum()

    if total <= 0:
        return 1.0, 0.0

    probabilities = histogram / total

    centers = (
        bin_edges[:-1] + bin_edges[1:]
    ) / 2.0

    cumulative_probability = np.cumsum(probabilities)

    cumulative_mean = np.cumsum(
        probabilities * centers
    )

    global_mean = float(cumulative_mean[-1])

    denominator = (
        cumulative_probability
        * (1.0 - cumulative_probability)
    )

    between_class_variance = np.zeros_like(denominator)

    valid = denominator > 1e-12

    between_class_variance[valid] = (
        (
            global_mean * cumulative_probability[valid]
            - cumulative_mean[valid]
        )
        ** 2
        / denominator[valid]
    )

    best_index = int(np.argmax(between_class_variance))

    threshold = float(centers[best_index])

    total_variance = float(
        np.sum(
            probabilities
            * (centers - global_mean) ** 2
        )
    )

    if total_variance > 1e-12:
        separability = float(
            between_class_variance[best_index]
            / total_variance
        )
    else:
        separability = 0.0

    return (
        _clamp(threshold, MIN_THRESHOLD, MAX_THRESHOLD),
        _clamp(separability, 0.0, 1.0),
    )


# ---------------------------------------------------------------------------
# Neural model support
# ---------------------------------------------------------------------------


class TrainedChangeModel:
    """
    Optional trained TorchScript change-detection model.

    The wrapper intentionally does not create a randomly initialized neural
    network. A neural model is considered valid only when an explicit model
    artifact is supplied.

    Expected model interface:

        model(t1_tensor, t2_tensor)

    where each tensor has shape:

        [1, 3, H, W]

    and the returned tensor is either:

        [1, 1, H, W]
        [1, H, W]
        [H, W]

    Values may be logits or probabilities. Values outside [0, 1] are passed
    through sigmoid.
    """

    def __init__(self) -> None:
        self.model = None
        self.device = "cpu"
        self.path: str | None = None
        self.model_type: str | None = None
        self.loaded = False
        self.error: str | None = None

        if not HAS_TORCH:
            self.error = "PyTorch is not installed."
            return

        configured_path = os.getenv("CHANGE_DETECTION_MODEL_PATH", "").strip()
        checkpoint_path = os.getenv("CHANGE_DETECTION_CHECKPOINT", "").strip()
        model_type = os.getenv("CHANGE_DETECTION_MODEL_TYPE", "").strip().lower()

        if checkpoint_path:
            configured_path = checkpoint_path
            model_type = model_type or "siamese"

        if not configured_path:
            self.error = (
                "No trained change-detection model configured."
            )
            return

        model_path = Path(configured_path)

        if not model_path.exists():
            self.error = (
                f"Configured change-detection model does not exist: "
                f"{model_path}"
            )
            return

        configured_device = os.getenv(
            "CHANGE_DETECTION_DEVICE",
            "",
        ).strip()

        if configured_device:
            self.device = configured_device
        else:
            self.device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        try:
            if model_type == "siamese" or model_path.suffix.lower() in {".pth", ".pt", ".ckpt"} and os.getenv("CHANGE_DETECTION_MODEL_TYPE", "").strip().lower() == "siamese":
                from ml.change_detection.model import SiameseChangeNet

                checkpoint = torch.load(str(model_path), map_location=self.device)
                if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
                    raise RuntimeError("Siamese checkpoint must contain model_state_dict.")
                self.model = SiameseChangeNet(
                    in_channels=int(checkpoint.get("in_channels", 3))
                )
                self.model.load_state_dict(checkpoint["model_state_dict"])
                self.model.to(self.device)
                self.model.eval()
            else:
                self.model = torch.jit.load(
                    str(model_path),
                    map_location=self.device,
                )
                self.model.eval()

            self.path = str(model_path)
            self.model_type = model_type or "torchscript"
            self.loaded = True

            logger.info(
                "Loaded trained change-detection model: %s on %s",
                model_path,
                self.device,
            )

        except Exception as exc:
            self.error = str(exc)
            self.model = None
            self.loaded = False

            logger.exception(
                "Unable to load trained change-detection model"
            )

    def predict(
        self,
        t1: np.ndarray,
        t2: np.ndarray,
    ) -> np.ndarray:
        if not self.loaded or self.model is None:
            raise RuntimeError(
                "Trained change-detection model is not available."
            )

        if not HAS_TORCH:
            raise RuntimeError(
                "PyTorch is unavailable."
            )

        t1_rgb = _ensure_rgb(
            _normalize_image_array(t1)
        )

        t2_rgb = _ensure_rgb(
            _normalize_image_array(t2)
        )

        tensor1 = (
            torch.from_numpy(t1_rgb)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .float()
            .to(self.device)
        )

        tensor2 = (
            torch.from_numpy(t2_rgb)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .float()
            .to(self.device)
        )

        with torch.no_grad():
            output = self.model(
                tensor1,
                tensor2,
            )

        if isinstance(output, (tuple, list)):
            if not output:
                raise RuntimeError(
                    "Change model returned an empty output."
                )
            output = output[0]

        if not torch.is_tensor(output):
            raise RuntimeError(
                "Change model did not return a tensor."
            )

        output = output.detach().float().cpu()

        if output.ndim == 4:
            output = output[0]

        if output.ndim == 3:
            if output.shape[0] == 1:
                output = output[0]
            elif output.shape[-1] == 1:
                output = output[:, :, 0]
            else:
                output = output[0]

        if output.ndim != 2:
            raise RuntimeError(
                f"Unsupported change-model output shape: "
                f"{tuple(output.shape)}"
            )

        probability = output.numpy()

        finite = probability[np.isfinite(probability)]

        if finite.size == 0:
            raise RuntimeError(
                "Change model produced no finite values."
            )

        # If output is not already probability-like, treat it as logits.
        if (
            float(np.min(finite)) < 0.0
            or float(np.max(finite)) > 1.0
        ):
            probability = 1.0 / (
                1.0 + np.exp(
                    -np.clip(probability, -50.0, 50.0)
                )
            )

        probability = np.nan_to_num(
            probability,
            nan=0.0,
            posinf=1.0,
            neginf=0.0,
        )

        probability = np.clip(
            probability,
            0.0,
            1.0,
        )

        if probability.shape != t1.shape[:2]:
            probability_image = Image.fromarray(
                np.clip(
                    probability * 255.0,
                    0,
                    255,
                ).astype(np.uint8),
                mode="L",
            )

            probability_image = probability_image.resize(
                (
                    t1.shape[1],
                    t1.shape[0],
                ),
                Image.Resampling.BILINEAR,
            )

            probability = (
                np.asarray(
                    probability_image,
                    dtype=np.float32,
                )
                / 255.0
            )

        return probability.astype(np.float32)


# ---------------------------------------------------------------------------
# Difference map
# ---------------------------------------------------------------------------


def _compute_difference_map(
    t1: np.ndarray,
    t2: np.ndarray,
) -> np.ndarray:
    """
    Calculate normalized multi-channel image difference.

    This is an evidence-producing baseline, not a semantic classifier.

    It measures normalized visual/spectral difference between the provided
    image representations. It does not label the reason for the change.
    """
    normalized_t1 = _normalize_image_array(t1)
    normalized_t2 = _normalize_image_array(t2)

    if normalized_t1.shape != normalized_t2.shape:
        normalized_t2 = _resize_array(
            normalized_t2,
            normalized_t1.shape[1],
            normalized_t1.shape[0],
        )

    t1_rgb = _ensure_rgb(normalized_t1)
    t2_rgb = _ensure_rgb(normalized_t2)

    absolute_difference = np.abs(
        t1_rgb - t2_rgb
    )

    # RMS channel difference.
    difference = np.sqrt(
        np.mean(
            absolute_difference ** 2,
            axis=2,
        )
    )

    difference = np.nan_to_num(
        difference,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    return np.clip(
        difference,
        0.0,
        1.0,
    ).astype(np.float32)


# ---------------------------------------------------------------------------
# Morphological processing
# ---------------------------------------------------------------------------


def _clean_change_mask(
    probability_map: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """
    Convert probability/difference map to a cleaned binary mask.
    """
    raw_mask = probability_map >= threshold

    structure = np.ones(
        (3, 3),
        dtype=bool,
    )

    opened = ndimage.binary_opening(
        raw_mask,
        structure=structure,
    )

    closed = ndimage.binary_closing(
        opened,
        structure=structure,
    )

    return closed.astype(bool)


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------


def _extract_components(
    mask: np.ndarray,
    min_pixels: int,
    max_components: int,
) -> list[dict[str, Any]]:
    """
    Extract image-coordinate connected components.

    Coordinates are pixel coordinates unless geospatial conversion is
    explicitly performed later.
    """
    labeled, count = ndimage.label(
        mask,
        structure=np.ones(
            (3, 3),
            dtype=np.uint8,
        ),
    )

    if count <= 0:
        return []

    objects = ndimage.find_objects(labeled)

    components: list[dict[str, Any]] = []

    for component_id, object_slice in enumerate(
        objects,
        start=1,
    ):
        if object_slice is None:
            continue

        ys, xs = np.where(
            labeled[object_slice] == component_id
        )

        pixel_count = int(len(xs))

        if pixel_count < min_pixels:
            continue

        y_offset = object_slice[0].start
        x_offset = object_slice[1].start

        xs_absolute = xs + x_offset
        ys_absolute = ys + y_offset

        if len(xs_absolute) == 0:
            continue

        x1 = float(np.min(xs_absolute))
        y1 = float(np.min(ys_absolute))
        x2 = float(np.max(xs_absolute))
        y2 = float(np.max(ys_absolute))

        components.append(
            {
                "component_id": component_id,
                "pixel_count": pixel_count,
                "bbox": [
                    x1,
                    y1,
                    x2,
                    y2,
                ],
            }
        )

    # Largest components first.
    components.sort(
        key=lambda item: item["pixel_count"],
        reverse=True,
    )

    return components[:max_components]


# ---------------------------------------------------------------------------
# Geospatial metadata
# ---------------------------------------------------------------------------


def _extract_geospatial_metadata(
    inputs: ModelInput,
) -> dict[str, Any]:
    """
    Extract geospatial metadata supplied by the orchestrator.

    Supported parameter names intentionally include several common forms so
    the wrapper can work with the existing Django imagery layer.

    No coordinate defaults are used.
    """
    params = getattr(inputs, "params", None)

    if not isinstance(params, dict):
        params = {}

    metadata: dict[str, Any] = {
        "crs": params.get("crs"),
        "transform": params.get("transform"),
        "bounds": params.get("bounds"),
        "width": params.get("width"),
        "height": params.get("height"),
        "resolution_x": params.get("resolution_x"),
        "resolution_y": params.get("resolution_y"),
        "pixel_area_m2": params.get("pixel_area_m2"),
        "geospatial_reference_available": False,
    }

    # Alternative resolution representation.
    resolution = params.get("resolution_m")

    if (
        resolution is not None
        and metadata["resolution_x"] is None
    ):
        resolution_value = _safe_float(resolution)

        if resolution_value is not None:
            metadata["resolution_x"] = resolution_value
            metadata["resolution_y"] = resolution_value

    # Alternative CRS representation.
    if metadata["crs"] is None:
        metadata["crs"] = params.get("source_crs")

    # Alternative transform representation.
    if metadata["transform"] is None:
        metadata["transform"] = params.get("geotransform")

    # Calculate pixel area only when actual dimensions are provided.
    pixel_area = _safe_float(
        metadata.get("pixel_area_m2")
    )

    if pixel_area is not None and pixel_area > 0:
        metadata["pixel_area_m2"] = pixel_area

    else:
        rx = _safe_float(
            metadata.get("resolution_x")
        )
        ry = _safe_float(
            metadata.get("resolution_y")
        )

        if (
            rx is not None
            and ry is not None
            and rx > 0
            and ry > 0
        ):
            metadata["pixel_area_m2"] = (
                abs(rx * ry)
            )

    has_crs = metadata.get("crs") is not None
    has_transform = metadata.get("transform") is not None

    metadata["geospatial_reference_available"] = (
        has_crs and has_transform
    )

    return metadata


def _coerce_affine(
    transform: Any,
) -> Any:
    if transform is None or not HAS_RASTERIO:
        return None

    if isinstance(transform, Affine):
        return transform

    if isinstance(transform, (list, tuple)):
        values = list(transform)

        if len(values) == 6:
            try:
                return Affine(*map(float, values))
            except Exception:
                return None

        if len(values) >= 9:
            try:
                return Affine(
                    float(values[0]),
                    float(values[1]),
                    float(values[2]),
                    float(values[3]),
                    float(values[4]),
                    float(values[5]),
                )
            except Exception:
                return None

    if isinstance(transform, dict):
        keys = (
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
        )

        if all(key in transform for key in keys):
            try:
                return Affine(
                    float(transform["a"]),
                    float(transform["b"]),
                    float(transform["c"]),
                    float(transform["d"]),
                    float(transform["e"]),
                    float(transform["f"]),
                )
            except Exception:
                return None

    return None


def _calculate_projected_pixel_area_m2(
    transform: Any,
    crs: Any,
) -> float | None:
    """
    Calculate pixel area from affine transform for projected CRS.

    For geographic CRS, this function returns None because pixel area varies
    with latitude and must be handled geodesically.
    """
    affine = _coerce_affine(transform)

    if affine is None:
        return None

    if crs is None:
        return None

    try:
        crs_string = str(crs).upper()

        if (
            "4326" in crs_string
            or "GEOGCS" in crs_string
            or "LONGITUDE" in crs_string
        ):
            return None
    except Exception:
        return None

    determinant = abs(
        affine.a * affine.e
        - affine.b * affine.d
    )

    if determinant <= 0:
        return None

    # Only treat the value as m² when CRS units are meters.
    if HAS_RASTERIO:
        try:
            raster_crs = rasterio.crs.CRS.from_user_input(
                crs
            )

            if raster_crs.is_projected:
                unit = str(
                    raster_crs.linear_units or ""
                ).lower()

                if (
                    "metre" in unit
                    or "meter" in unit
                    or unit == "m"
                ):
                    return float(determinant)
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Geospatial polygon conversion
# ---------------------------------------------------------------------------


def _pixel_bbox_to_polygon(
    bbox: list[float],
    transform: Any,
) -> list[list[float]]:
    """
    Convert a pixel bounding box into a polygon using the supplied affine
    transform.

    Returns coordinates in the source CRS.

    No WGS84 conversion is attempted unless a CRS transformation is explicitly
    available.
    """
    affine = _coerce_affine(transform)

    if affine is None:
        raise ValueError(
            "A valid raster transform is required."
        )

    x1, y1, x2, y2 = bbox

    points = [
        affine * (x1, y1),
        affine * (x2 + 1.0, y1),
        affine * (x2 + 1.0, y2 + 1.0),
        affine * (x1, y2 + 1.0),
    ]

    return [
        [
            float(x),
            float(y),
        ]
        for x, y in points
    ]


def _calculate_geodesic_polygon_area_m2(
    coordinates: list[list[float]],
    crs: Any,
) -> float | None:
    """
    Calculate polygon area in m² for geographic CRS.

    The coordinates must be longitude/latitude when the CRS is geographic.
    """
    if not HAS_PYPROJ:
        return None

    if not coordinates:
        return None

    if crs is None:
        return None

    try:
        if HAS_RASTERIO:
            source_crs = rasterio.crs.CRS.from_user_input(
                crs
            )

            if not source_crs.is_geographic:
                return None

        else:
            crs_string = str(crs)

            if "4326" not in crs_string:
                return None
    except Exception:
        return None

    try:
        lons = [
            point[0]
            for point in coordinates
        ]

        lats = [
            point[1]
            for point in coordinates
        ]

        if len(lons) < 3:
            return None

        geod = Geod(ellps="WGS84")

        area, _ = geod.polygon_area_perimeter(
            lons,
            lats,
        )

        return abs(float(area))

    except Exception:
        logger.exception(
            "Failed to calculate geodesic polygon area."
        )
        return None


def _build_geojson(
    components: list[dict[str, Any]],
    transform: Any,
    crs: Any,
) -> dict[str, Any] | None:
    """
    Build GeoJSON using the source raster CRS.

    GeoJSON geometry coordinates are intentionally NOT mislabeled as WGS84.
    The returned object includes the source CRS metadata separately.
    """
    if not components:
        return None

    affine = _coerce_affine(transform)

    if affine is None:
        return None

    features: list[dict[str, Any]] = []

    for component in components:
        bbox = component.get("bbox")

        if not bbox:
            continue

        try:
            ring = _pixel_bbox_to_polygon(
                bbox,
                affine,
            )
        except Exception:
            continue

        ring.append(ring[0])

        area_m2 = _calculate_geodesic_polygon_area_m2(
            ring,
            crs,
        )

        properties = {
            "component_id": component[
                "component_id"
            ],
            "pixel_count": component[
                "pixel_count"
            ],
            "bbox_pixels": bbox,
        }

        if area_m2 is not None:
            properties["area_m2"] = round(
                area_m2,
                4,
            )
            properties["area_ha"] = round(
                area_m2 / 10000.0,
                6,
            )

        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            }
        )

    if not features:
        return None

    result: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
    }

    if crs is not None:
        result["source_crs"] = str(crs)

    return result


# ---------------------------------------------------------------------------
# Area calculations
# ---------------------------------------------------------------------------


def _calculate_change_area(
    change_pixels: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate physical area only when supported by actual metadata.
    """
    pixel_area_m2 = _safe_float(
        metadata.get("pixel_area_m2")
    )

    if (
        pixel_area_m2 is None
        or pixel_area_m2 <= 0
    ):
        return {
            "area_available": False,
            "area_reason": (
                "Pixel ground area is unavailable. "
                "The source imagery did not provide sufficient "
                "resolution/geospatial metadata."
            ),
        }

    area_m2 = (
        float(change_pixels)
        * pixel_area_m2
    )

    return {
        "area_available": True,
        "pixel_area_m2": round(
            pixel_area_m2,
            6,
        ),
        "area_m2": round(
            area_m2,
            4,
        ),
        "area_ha": round(
            area_m2 / 10000.0,
            6,
        ),
        "area_km2": round(
            area_m2 / 1_000_000.0,
            8,
        ),
    }


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def _create_overlay(
    image_t2: Image.Image,
    mask: np.ndarray,
    components: list[dict[str, Any]],
) -> bytes:
    """
    Create an evidence overlay.

    Red areas indicate pixels classified as changed by the selected
    difference/probability threshold.
    """
    base = image_t2.convert("RGBA")

    width, height = base.size

    if mask.shape != (
        height,
        width,
    ):
        mask_image = Image.fromarray(
            (mask.astype(np.uint8) * 255),
            mode="L",
        ).resize(
            (width, height),
            Image.Resampling.NEAREST,
        )

        mask = (
            np.asarray(mask_image) > 0
        )

    overlay_array = np.zeros(
        (height, width, 4),
        dtype=np.uint8,
    )

    overlay_array[mask] = [
        239,
        68,
        68,
        130,
    ]

    overlay = Image.fromarray(
        overlay_array,
        mode="RGBA",
    )

    result = Image.alpha_composite(
        base,
        overlay,
    )

    draw = ImageDraw.Draw(result)

    for component in components[:50]:
        bbox = component["bbox"]

        draw.rectangle(
            [
                bbox[0],
                bbox[1],
                bbox[2],
                bbox[3],
            ],
            outline=(239, 68, 68, 255),
            width=2,
        )

    buffer = io.BytesIO()

    result.convert("RGB").save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


def _create_mask_png(
    mask: np.ndarray,
) -> bytes:
    buffer = io.BytesIO()

    image = Image.fromarray(
        (
            mask.astype(np.uint8)
            * 255
        ),
        mode="L",
    )

    image.save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


class ChangeDetectionModel:
    """
    Bi-temporal change detection specialist.

    This model produces image-change evidence.

    It intentionally does NOT infer semantic causes such as:

    - buildings
    - roads
    - deforestation
    - flooding
    - construction

    Those claims require a dedicated semantic model or downstream reasoning
    agent with appropriate evidence.
    """

    model_id = "CHANGE_DETECTION"
    version = "3.0-grounded"
    task = "bi_temporal_change_map"

    def __init__(self) -> None:
        self._trained_model = TrainedChangeModel()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        inputs: ModelInput,
    ) -> ModelOutput:
        start_time = time.perf_counter()

        try:
            return self._predict_internal(
                inputs,
                start_time,
            )

        except Exception as exc:
            logger.exception(
                "Change detection failed."
            )

            latency = int(
                (
                    time.perf_counter()
                    - start_time
                )
                * 1000
            )

            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error=str(exc),
                latency_ms=latency,
            )

    # ------------------------------------------------------------------
    # Internal prediction
    # ------------------------------------------------------------------

    def _predict_internal(
        self,
        inputs: ModelInput,
        start_time: float,
    ) -> ModelOutput:
        image_t1, image_t2 = _load_pair(
            inputs
        )

        if image_t1 is None or image_t2 is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error=(
                    "Bi-temporal change detection "
                    "requires two valid images: T1 and T2."
                ),
                latency_ms=int(
                    (
                        time.perf_counter()
                        - start_time
                    )
                    * 1000
                ),
            )

        # --------------------------------------------------------------
        # Input dimensions
        # --------------------------------------------------------------

        width_t1, height_t1 = image_t1.size
        width_t2, height_t2 = image_t2.size

        if (
            width_t1 <= 0
            or height_t1 <= 0
            or width_t2 <= 0
            or height_t2 <= 0
        ):
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error=(
                    "T1 and T2 must contain valid image dimensions."
                ),
                latency_ms=int(
                    (
                        time.perf_counter()
                        - start_time
                    )
                    * 1000
                ),
            )

        # --------------------------------------------------------------
        # Alignment policy
        # --------------------------------------------------------------

        allow_resize = bool(
            _get_param(
                inputs,
                "allow_resize",
                True,
            )
        )

        if image_t1.size != image_t2.size:
            if not allow_resize:
                return ModelOutput(
                    model_id=self.model_id,
                    version=self.version,
                    task=self.task,
                    status="error",
                    error=(
                        "T1 and T2 have different dimensions. "
                        "Registration/resampling must be performed "
                        "before change detection."
                    ),
                    latency_ms=int(
                        (
                            time.perf_counter()
                            - start_time
                        )
                        * 1000
                    ),
                )

            logger.warning(
                "T1/T2 dimensions differ; resizing T2 to T1 "
                "dimensions. True geospatial co-registration "
                "should preferably occur upstream."
            )

            image_t2 = image_t2.resize(
                image_t1.size,
                Image.Resampling.BILINEAR,
            )

        width, height = image_t1.size

        # --------------------------------------------------------------
        # Convert to normalized arrays
        # --------------------------------------------------------------

        t1_array = _as_numpy_array(
            image_t1
        )

        t2_array = _as_numpy_array(
            image_t2
        )

        # --------------------------------------------------------------
        # Calculate difference / probability
        # --------------------------------------------------------------

        model_source = "image_difference_baseline"
        model_error = None

        use_trained_model = bool(
            _get_param(
                inputs,
                "use_trained_model",
                True,
            )
        )

        probability_map: np.ndarray

        if (
            use_trained_model
            and self._trained_model.loaded
        ):
            try:
                probability_map = (
                    self._trained_model.predict(
                        t1_array,
                        t2_array,
                    )
                )

                model_source = (
                    "trained_change_detection_model"
                )

                calibration_temperature = _load_calibration_temperature()
                if calibration_temperature is not None:
                    # The trained model returns logits/probabilities. Recalibrate
                    # only when a held-out validation artifact is explicitly supplied.
                    # Trained wrapper exposes probabilities, so invert the
                    # probability to a logit before applying temperature scaling.
                    p = np.clip(probability_map, 1e-6, 1.0 - 1e-6)
                    logits = np.log(p / (1.0 - p))
                    probability_map = 1.0 / (1.0 + np.exp(-np.clip(logits / calibration_temperature, -80.0, 80.0)))

            except Exception as exc:
                model_error = str(exc)

                logger.exception(
                    "Configured trained model failed; "
                    "falling back to evidence-based image difference."
                )

                probability_map = (
                    _compute_difference_map(
                        t1_array,
                        t2_array,
                    )
                )

                model_source = (
                    "image_difference_baseline"
                )

        else:
            probability_map = (
                _compute_difference_map(
                    t1_array,
                    t2_array,
                )
            )

            if (
                use_trained_model
                and self._trained_model.error
            ):
                model_error = (
                    self._trained_model.error
                )

        # --------------------------------------------------------------
        # Threshold
        # --------------------------------------------------------------

        requested_threshold = _safe_float(
            _get_param(
                inputs,
                "threshold",
                None,
            )
        )

        env_threshold = _safe_float(
            os.getenv(
                "CHANGE_DETECTION_THRESHOLD",
                "",
            )
        )

        threshold_source = "otsu"

        if requested_threshold is not None:
            if not 0.0 <= requested_threshold <= 1.0:
                return ModelOutput(
                    model_id=self.model_id,
                    version=self.version,
                    task=self.task,
                    status="error",
                    error=(
                        "threshold must be between 0 and 1."
                    ),
                    latency_ms=int(
                        (
                            time.perf_counter()
                            - start_time
                        )
                        * 1000
                    ),
                )

            threshold = requested_threshold
            separability = 0.0
            threshold_source = "request_parameter"

        elif (
            env_threshold is not None
            and self._trained_model.loaded
        ):
            threshold = _clamp(
                env_threshold,
                0.0,
                1.0,
            )

            separability = 0.0
            threshold_source = (
                "environment_configuration"
            )

        else:
            threshold, separability = (
                compute_otsu_threshold(
                    probability_map
                )
            )

        # --------------------------------------------------------------
        # Mask cleanup
        # --------------------------------------------------------------

        min_component_pixels = int(
            _get_param(
                inputs,
                "min_component_pixels",
                int(
                    os.getenv(
                        "CHANGE_DETECTION_MIN_COMPONENT_PIXELS",
                        DEFAULT_MIN_COMPONENT_PIXELS,
                    )
                ),
            )
        )

        max_components = int(
            _get_param(
                inputs,
                "max_components",
                int(
                    os.getenv(
                        "CHANGE_DETECTION_MAX_COMPONENTS",
                        DEFAULT_MAX_COMPONENTS,
                    )
                ),
            )
        )

        min_component_pixels = max(
            1,
            min_component_pixels,
        )

        max_components = max(
            1,
            max_components,
        )

        cleaned_mask = _clean_change_mask(
            probability_map,
            threshold,
        )

        components = _extract_components(
            cleaned_mask,
            min_component_pixels,
            max_components,
        )

        # --------------------------------------------------------------
        # Basic measurements
        # --------------------------------------------------------------

        total_pixels = int(
            cleaned_mask.size
        )

        change_pixels = int(
            np.count_nonzero(
                cleaned_mask
            )
        )

        change_percent = (
            (
                change_pixels
                / total_pixels
            )
            * 100.0
            if total_pixels > 0
            else 0.0
        )

        # --------------------------------------------------------------
        # Geospatial metadata
        # --------------------------------------------------------------

        geo = _extract_geospatial_metadata(
            inputs
        )

        pixel_area_from_transform = (
            _calculate_projected_pixel_area_m2(
                geo.get("transform"),
                geo.get("crs"),
            )
        )

        if (
            geo.get("pixel_area_m2")
            is None
            and pixel_area_from_transform
            is not None
        ):
            geo["pixel_area_m2"] = (
                pixel_area_from_transform
            )

        area_info = (
            _calculate_change_area(
                change_pixels,
                geo,
            )
        )

        # --------------------------------------------------------------
        # Component physical areas
        # --------------------------------------------------------------

        pixel_area_m2 = _safe_float(
            area_info.get(
                "pixel_area_m2"
            )
        )

        for component in components:
            if (
                pixel_area_m2 is not None
                and pixel_area_m2 > 0
            ):
                component_area_m2 = (
                    component["pixel_count"]
                    * pixel_area_m2
                )

                component[
                    "area_m2"
                ] = round(
                    component_area_m2,
                    4,
                )

                component[
                    "area_ha"
                ] = round(
                    component_area_m2
                    / 10000.0,
                    6,
                )

                component[
                    "area_km2"
                ] = round(
                    component_area_m2
                    / 1_000_000.0,
                    8,
                )

        # --------------------------------------------------------------
        # Image-coordinate boxes
        # --------------------------------------------------------------

        boxes: list[dict[str, Any]] = []

        for component in components:
            box: dict[str, Any] = {
                "x1": component[
                    "bbox"
                ][0],
                "y1": component[
                    "bbox"
                ][1],
                "x2": component[
                    "bbox"
                ][2],
                "y2": component[
                    "bbox"
                ][3],
                "label": "detected_change",
                "confidence": round(
                    float(
                        max(
                            separability,
                            0.0,
                        )
                    ),
                    3,
                ),
                "pixel_count": component[
                    "pixel_count"
                ],
            }

            if "area_m2" in component:
                box[
                    "area_m2"
                ] = component[
                    "area_m2"
                ]

                box[
                    "area_ha"
                ] = component[
                    "area_ha"
                ]

            boxes.append(box)

        # --------------------------------------------------------------
        # GeoJSON
        # --------------------------------------------------------------

        geojson = None

        if (
            geo.get(
                "geospatial_reference_available"
            )
            and geo.get("transform") is not None
            and geo.get("crs") is not None
        ):
            geojson = _build_geojson(
                components,
                geo["transform"],
                geo["crs"],
            )

        # --------------------------------------------------------------
        # Visual artifacts
        # --------------------------------------------------------------

        mask_bytes = _create_mask_png(
            cleaned_mask
        )

        overlay_bytes = _create_overlay(
            image_t2,
            cleaned_mask,
            components,
        )

        # --------------------------------------------------------------
        # Evidence classification
        # --------------------------------------------------------------

        if change_pixels == 0:
            change_state = "no_detected_change"

        elif len(components) == 0:
            change_state = (
                "change_below_component_filter"
            )

        else:
            change_state = (
                "change_detected"
            )

        # --------------------------------------------------------------
        # Confidence
        # --------------------------------------------------------------

        if model_source == (
            "trained_change_detection_model"
        ):
            confidence = float(
                np.mean(
                    probability_map[
                        cleaned_mask
                    ]
                )
            ) if change_pixels > 0 else float(
                1.0
                - np.mean(
                    probability_map
                )
            )

            confidence = _clamp(
                confidence,
                0.0,
                1.0,
            )

        else:
            confidence = _clamp(
                separability,
                0.0,
                1.0,
            )

        # --------------------------------------------------------------
        # Grounded answer
        # --------------------------------------------------------------

        if change_state == (
            "no_detected_change"
        ):
            answer = (
                "No spatially significant change was detected "
                "after thresholding and morphological filtering."
            )

        elif change_state == (
            "change_below_component_filter"
        ):
            answer = (
                "Pixel-level differences were detected, but no "
                "change cluster exceeded the configured minimum "
                "component size."
            )

        else:
            answer = (
                f"Detected spatial change across "
                f"{change_percent:.2f}% of the analyzed pixels "
                f"in {len(components)} significant change cluster(s)."
            )

            if area_info.get(
                "area_available"
            ):
                answer += (
                    " The measured changed area is "
                    f"{area_info['area_ha']:.4f} hectares."
                )
            else:
                answer += (
                    " Physical area was not reported because "
                    "the source imagery did not provide sufficient "
                    "ground-resolution metadata."
                )

        # --------------------------------------------------------------
        # Raw structured evidence
        # --------------------------------------------------------------

        raw: dict[str, Any] = {
            "adaptation": "grounded",
            "base_model": model_source,
            "model_version": self.version,
            "change_detected": (
                change_state
                == "change_detected"
            ),
            "change_state": change_state,
            "change_percent": round(
                change_percent,
                4,
            ),
            "change_pixels": change_pixels,
            "total_pixels": total_pixels,
            "threshold": round(
                threshold,
                6,
            ),
            "threshold_source": (
                threshold_source
            ),
            "threshold_separability": round(
                separability,
                6,
            ),
            "regions_count": len(
                components
            ),
            "min_component_pixels": (
                min_component_pixels
            ),
            "max_components": (
                max_components
            ),
            "geospatial_reference_available": (
                geo.get(
                    "geospatial_reference_available",
                    False,
                )
            ),
            "source_crs": (
                str(geo["crs"])
                if geo.get("crs") is not None
                else None
            ),
            "pixel_area_m2": (
                area_info.get(
                    "pixel_area_m2"
                )
            ),
            "area_m2": (
                area_info.get(
                    "area_m2"
                )
            ),
            "area_ha": (
                area_info.get(
                    "area_ha"
                )
            ),
            "area_km2": (
                area_info.get(
                    "area_km2"
                )
            ),
            "area_available": (
                area_info.get(
                    "area_available",
                    False,
                )
            ),
            "area_reason": (
                area_info.get(
                    "area_reason"
                )
            ),
            "components": components,
            "model_configuration": {
                "trained_model_loaded": (
                    self._trained_model.loaded
                ),
                "trained_model_path": (
                    self._trained_model.path
                ),
            },
        }

        if model_error:
            raw[
                "model_warning"
            ] = model_error

        if geojson is not None:
            raw[
                "geojson"
            ] = geojson

        # --------------------------------------------------------------
        # Latency
        # --------------------------------------------------------------

        latency = int(
            (
                time.perf_counter()
                - start_time
            )
            * 1000
        )

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=answer,
            confidence=round(
                confidence,
                4,
            ),
            boxes=boxes,
            change_mask=mask_bytes,
            overlay=overlay_bytes,
            latency_ms=latency,
            status="ok",
            raw=raw,
        )


__all__ = [
    "ChangeDetectionModel",
    "compute_otsu_threshold",
]