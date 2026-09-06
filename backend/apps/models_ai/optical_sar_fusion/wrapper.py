"""
OPTICAL_SAR_FUSION specialist model wrapper.

Purpose
-------
Fuse optical and SAR observations when both modalities are actually
available.

Pipeline
--------
OPTICAL
    ↓
Optical normalization
    ↓
Optical evidence

SAR
    ↓
SAR preprocessing
    ↓
SAR evidence

OPTICAL + SAR
    ↓
Cross-modal agreement
    ↓
Grounded evidence regions
    ↓
Structured result

Scientific constraints
----------------------
- No fabricated SAR data.
- No fabricated optical data.
- No hardcoded geographic coordinates.
- No Sentinel-specific resolution assumptions.
- SAR backscatter is not treated as optical reflectance.
- Physical area is reported only when valid ground-resolution metadata
  is supplied.
- Semantic labels are evidence categories, not guaranteed land-cover
  truth.
- If modality metadata is unavailable, the model does not silently
  assume that the first image is optical and the second is SAR.
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from apps.agent.contracts import ModelInput, ModelOutput
from apps.geospatial.sensor_profiles import (
    preprocess_optical_raster,
    preprocess_sar_raster,
)

logger = logging.getLogger(__name__)


class OpticalSARFusionModel:
    """
    Cross-modal optical + SAR evidence fusion.

    The model expects exactly two observations and modality metadata.

    Supported modality metadata can be supplied through:

        inputs.params["optical_index"]
        inputs.params["sar_index"]

    or:

        inputs.params["modalities"] = [
            "optical",
            "sar",
        ]

    If modality metadata is absent, the model returns an explicit error
    instead of guessing which image is optical or SAR.
    """

    model_id = "OPTICAL_SAR_FUSION"
    version = "3.0-cross-modal-grounded"
    task = "cross_modal_fusion_analysis"

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
                "Optical-SAR fusion failed."
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
    # Main pipeline
    # ------------------------------------------------------------------

    def _predict_internal(
        self,
        inputs: ModelInput,
        start_time: float,
    ) -> ModelOutput:
        modality_indices = (
            self._resolve_modality_indices(
                inputs
            )
        )

        if modality_indices is None:
            return self._error(
                inputs,
                start_time,
                (
                    "Optical-SAR fusion requires explicit modality "
                    "metadata identifying one optical image and one "
                    "SAR image. The system will not guess modalities "
                    "from file order."
                ),
            )

        optical_index, sar_index = (
            modality_indices
        )

        optical_source = (
            self._load_image_source(
                inputs,
                optical_index,
            )
        )

        sar_source = (
            self._load_image_source(
                inputs,
                sar_index,
            )
        )

        if optical_source is None:
            return self._error(
                inputs,
                start_time,
                (
                    "The optical input could not be loaded."
                ),
            )

        if sar_source is None:
            return self._error(
                inputs,
                start_time,
                (
                    "The SAR input could not be loaded."
                ),
            )

        optical_image = (
            optical_source["image"]
        )

        sar_image = sar_source[
            "image"
        ]

        # --------------------------------------------------------------
        # Spatial compatibility
        # --------------------------------------------------------------

        optical_size = (
            optical_image.size
        )

        sar_size = sar_image.size

        if optical_size != sar_size:
            sar_image = sar_image.resize(
                optical_size,
                Image.Resampling.BILINEAR,
            )

        width, height = optical_size

        # --------------------------------------------------------------
        # Preprocessing
        # --------------------------------------------------------------

        raw_optical = np.asarray(
            optical_image.convert("RGB"),
            dtype=np.float32,
        )

        raw_sar = np.asarray(
            sar_image.convert("L"),
            dtype=np.float32,
        )

        optical_normalized = (
            self._preprocess_optical(
                raw_optical
            )
        )

        sar_normalized = (
            self._preprocess_sar(
                raw_sar
            )
        )

        # --------------------------------------------------------------
        # Evidence masks
        # --------------------------------------------------------------

        optical_features = (
            self._derive_optical_features(
                optical_normalized
            )
        )

        sar_features = (
            self._derive_sar_features(
                sar_normalized
            )
        )

        fused_features = (
            self._fuse_modalities(
                optical_features,
                sar_features,
            )
        )

        # --------------------------------------------------------------
        # Region extraction
        # --------------------------------------------------------------

        boxes = (
            self._extract_regions(
                fused_features,
                inputs,
            )
        )

        # --------------------------------------------------------------
        # Quantification
        # --------------------------------------------------------------

        total_pixels = (
            float(width * height)
        )

        water_pixels = int(
            np.count_nonzero(
                fused_features[
                    "water"
                ]
            )
        )

        urban_pixels = int(
            np.count_nonzero(
                fused_features[
                    "built_up"
                ]
            )
        )

        vegetation_pixels = int(
            np.count_nonzero(
                fused_features[
                    "vegetation"
                ]
            )
        )

        water_pct = (
            water_pixels
            / total_pixels
            * 100.0
            if total_pixels > 0
            else 0.0
        )

        urban_pct = (
            urban_pixels
            / total_pixels
            * 100.0
            if total_pixels > 0
            else 0.0
        )

        vegetation_pct = (
            vegetation_pixels
            / total_pixels
            * 100.0
            if total_pixels > 0
            else 0.0
        )

        # --------------------------------------------------------------
        # Cross-modal agreement
        # --------------------------------------------------------------

        agreement = (
            self._calculate_cross_modal_agreement(
                optical_features,
                sar_features,
            )
        )

        # --------------------------------------------------------------
        # Physical area
        # --------------------------------------------------------------

        pixel_area_m2 = (
            self._resolve_pixel_area_m2(
                inputs
            )
        )

        area_values = (
            self._calculate_physical_areas(
                fused_features,
                pixel_area_m2,
            )
        )

        # --------------------------------------------------------------
        # Visualization
        # --------------------------------------------------------------

        overlay_bytes = (
            self._create_overlay(
                optical_image,
                fused_features,
                boxes,
            )
        )

        # --------------------------------------------------------------
        # Answer
        # --------------------------------------------------------------

        answer = (
            self._compose_answer(
                water_pct=water_pct,
                urban_pct=urban_pct,
                vegetation_pct=vegetation_pct,
                boxes_count=len(boxes),
                agreement=agreement,
                physical_area_available=(
                    pixel_area_m2 is not None
                ),
            )
        )

        latency = int(
            (
                time.perf_counter()
                - start_time
            )
            * 1000
        )

        raw = {
            "adaptation": "grounded",
            "base_model": (
                "optical-sar-cross-modal-evidence-fusion"
            ),
            "model_version": self.version,
            "optical_input_index": optical_index,
            "sar_input_index": sar_index,
            "optical_preprocessed": True,
            "sar_preprocessed": True,
            "sar_preprocessing": (
                "speckle-filter+log-transform"
            ),
            "spatial_alignment": {
                "optical_size": [
                    int(optical_size[0]),
                    int(optical_size[1]),
                ],
                "sar_original_size": [
                    int(sar_size[0]),
                    int(sar_size[1]),
                ],
                "resampled_sar": (
                    optical_size != sar_size
                ),
            },
            "cross_modal_agreement": round(
                agreement,
                4,
            ),
            "built_up_percent": round(
                urban_pct,
                4,
            ),
            "water_percent": round(
                water_pct,
                4,
            ),
            "vegetation_percent": round(
                vegetation_pct,
                4,
            ),
            "built_up_pixels": urban_pixels,
            "water_pixels": water_pixels,
            "vegetation_pixels": vegetation_pixels,
            "boxes_extracted": len(boxes),
            "physical_area_available": (
                pixel_area_m2 is not None
            ),
            "area_m2": area_values.get(
                "total_m2"
            ),
            "area_ha": area_values.get(
                "total_ha"
            ),
            "area_km2": area_values.get(
                "total_km2"
            ),
            "category_areas": area_values.get(
                "categories"
            ),
            "evidence_regions": boxes,
        }

        source_crs = self._get_param(
            inputs,
            "source_crs",
        )

        if source_crs:
            raw["source_crs"] = str(
                source_crs
            )

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=answer,
            confidence=round(
                agreement,
                3,
            ),
            boxes=boxes,
            overlay=overlay_bytes,
            latency_ms=latency,
            status="ok",
            raw=raw,
        )

    # ------------------------------------------------------------------
    # Modality resolution
    # ------------------------------------------------------------------

    def _resolve_modality_indices(
        self,
        inputs: ModelInput,
    ) -> tuple[int, int] | None:
        params = getattr(
            inputs,
            "params",
            None,
        )

        if not isinstance(
            params,
            dict,
        ):
            return None

        optical_index = params.get(
            "optical_index"
        )

        sar_index = params.get(
            "sar_index"
        )

        if (
            optical_index is not None
            and sar_index is not None
        ):
            try:
                optical_index = int(
                    optical_index
                )
                sar_index = int(
                    sar_index
                )
            except (
                TypeError,
                ValueError,
            ):
                return None

            if (
                optical_index != sar_index
                and optical_index >= 0
                and sar_index >= 0
            ):
                return (
                    optical_index,
                    sar_index,
                )

            return None

        modalities = params.get(
            "modalities"
        )

        if isinstance(
            modalities,
            (list, tuple),
        ):
            optical_candidates = [
                index
                for index, modality
                in enumerate(modalities)
                if str(modality).lower()
                in {
                    "optical",
                    "multispectral",
                    "rgb",
                }
            ]

            sar_candidates = [
                index
                for index, modality
                in enumerate(modalities)
                if str(modality).lower()
                in {
                    "sar",
                    "radar",
                }
            ]

            if (
                len(optical_candidates) == 1
                and len(sar_candidates) == 1
            ):
                return (
                    optical_candidates[0],
                    sar_candidates[0],
                )

        return None

    # ------------------------------------------------------------------
    # Input loading
    # ------------------------------------------------------------------

    def _load_image_source(
        self,
        inputs: ModelInput,
        index: int,
    ) -> dict[str, Any] | None:
        image_bytes = getattr(
            inputs,
            "image_bytes",
            None,
        )

        if (
            isinstance(
                image_bytes,
                (list, tuple),
            )
            and 0 <= index < len(image_bytes)
        ):
            payload = image_bytes[
                index
            ]

            if not isinstance(
                payload,
                (bytes, bytearray),
            ):
                return None

            try:
                image = Image.open(
                    io.BytesIO(
                        payload
                    )
                ).convert("RGB")

                return {
                    "image": image,
                    "source": "bytes",
                }

            except Exception:
                logger.exception(
                    "Unable to decode image bytes."
                )
                return None

        image_paths = getattr(
            inputs,
            "image_paths",
            None,
        )

        if (
            isinstance(
                image_paths,
                (list, tuple),
            )
            and 0 <= index < len(image_paths)
        ):
            path = Path(
                str(
                    image_paths[index]
                )
            )

            if not path.exists():
                return None

            try:
                image = Image.open(
                    path
                ).convert("RGB")

                return {
                    "image": image,
                    "source": str(path),
                }

            except Exception:
                logger.exception(
                    "Unable to decode image path."
                )
                return None

        return None

    # ------------------------------------------------------------------
    # Optical preprocessing
    # ------------------------------------------------------------------

    def _preprocess_optical(
        self,
        array: np.ndarray,
    ) -> np.ndarray:
        try:
            normalized = (
                preprocess_optical_raster(
                    array
                )
            )

            normalized = np.asarray(
                normalized,
                dtype=np.float32,
            )

            return np.clip(
                normalized,
                0.0,
                1.0,
            )

        except Exception:
            logger.exception(
                "Optical preprocessing failed; "
                "using numerically safe image normalization."
            )

            minimum = float(
                np.nanmin(array)
            )

            maximum = float(
                np.nanmax(array)
            )

            if maximum <= minimum:
                return np.zeros_like(
                    array,
                    dtype=np.float32,
                )

            normalized = (
                array - minimum
            ) / (
                maximum - minimum
            )

            return np.clip(
                normalized,
                0.0,
                1.0,
            ).astype(
                np.float32
            )

    # ------------------------------------------------------------------
    # SAR preprocessing
    # ------------------------------------------------------------------

    def _preprocess_sar(
        self,
        array: np.ndarray,
    ) -> np.ndarray:
        try:
            normalized = (
                preprocess_sar_raster(
                    array,
                    speckle_filter_size=3,
                    apply_log_transform=True,
                )
            )

            normalized = np.asarray(
                normalized,
                dtype=np.float32,
            )

            return np.clip(
                normalized,
                0.0,
                1.0,
            )

        except Exception:
            logger.exception(
                "SAR preprocessing failed."
            )

            # This fallback only normalizes an already supplied SAR
            # observation. It does not fabricate SAR data.
            safe = np.nan_to_num(
                array,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )

            minimum = float(
                np.min(safe)
            )

            maximum = float(
                np.max(safe)
            )

            if maximum <= minimum:
                return np.zeros_like(
                    safe,
                    dtype=np.float32,
                )

            normalized = (
                safe - minimum
            ) / (
                maximum - minimum
            )

            return np.clip(
                normalized,
                0.0,
                1.0,
            ).astype(
                np.float32
            )

    # ------------------------------------------------------------------
    # Optical evidence
    # ------------------------------------------------------------------

    def _derive_optical_features(
        self,
        optical: np.ndarray,
    ) -> dict[str, np.ndarray]:
        red = optical[
            :, :, 0
        ]

        green = optical[
            :, :, 1
        ]

        blue = optical[
            :, :, 2
        ]

        # These are candidate evidence masks, not trained land-cover
        # classification probabilities.
        water = (
            (blue < 0.35)
            & (red < 0.30)
            & (green < 0.40)
        )

        vegetation = (
            (green > red * 1.05)
            & (green > blue)
        )

        built_up = (
            (np.abs(red - green) < 0.15)
            & (np.abs(green - blue) < 0.20)
            & (red > 0.30)
        )

        return {
            "water": water,
            "vegetation": vegetation,
            "built_up": built_up,
        }

    # ------------------------------------------------------------------
    # SAR evidence
    # ------------------------------------------------------------------

    def _derive_sar_features(
        self,
        sar: np.ndarray,
    ) -> dict[str, np.ndarray]:
        # The normalized SAR signal is used only for cross-modal
        # consistency. It is not interpreted as RGB reflectance.
        water = (
            sar < 0.25
        )

        built_up = (
            sar > 0.60
        )

        vegetation = (
            (sar >= 0.25)
            & (sar <= 0.60)
        )

        return {
            "water": water,
            "vegetation": vegetation,
            "built_up": built_up,
        }

    # ------------------------------------------------------------------
    # Cross-modal fusion
    # ------------------------------------------------------------------

    def _fuse_modalities(
        self,
        optical: dict[str, np.ndarray],
        sar: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """
        Fuse only where both modalities support the same category.

        This intentionally favors agreement over simply OR-ing the
        modalities together.
        """
        water = (
            optical["water"]
            & sar["water"]
        )

        built_up = (
            optical["built_up"]
            & sar["built_up"]
        )

        vegetation = (
            optical["vegetation"]
            & sar["vegetation"]
        )

        return {
            "water": water,
            "built_up": built_up,
            "vegetation": vegetation,
        }

    # ------------------------------------------------------------------
    # Agreement
    # ------------------------------------------------------------------

    def _calculate_cross_modal_agreement(
        self,
        optical: dict[str, np.ndarray],
        sar: dict[str, np.ndarray],
    ) -> float:
        all_agreements: list[float] = []

        for category in (
            "water",
            "built_up",
            "vegetation",
        ):
            optical_mask = optical[
                category
            ]

            sar_mask = sar[
                category
            ]

            total = optical_mask.size

            if total == 0:
                continue

            disagreement = np.count_nonzero(
                optical_mask
                ^ sar_mask
            )

            agreement = (
                1.0
                - (
                    disagreement
                    / total
                )
            )

            all_agreements.append(
                agreement
            )

        if not all_agreements:
            return 0.0

        agreement = float(
            np.mean(
                all_agreements
            )
        )

        return float(
            np.clip(
                agreement,
                0.0,
                1.0,
            )
        )

    # ------------------------------------------------------------------
    # Region extraction
    # ------------------------------------------------------------------

    def _extract_regions(
        self,
        fused: dict[str, np.ndarray],
        inputs: ModelInput,
    ) -> list[dict[str, Any]]:
        regions: list[
            dict[str, Any]
        ] = []

        minimum_pixels = (
            self._get_positive_int_param(
                inputs,
                "minimum_region_pixels",
                default=25,
            )
        )

        max_regions = (
            self._get_positive_int_param(
                inputs,
                "max_regions",
                default=50,
            )
        )

        labels = (
            (
                "built_up",
                "built_up_infrastructure",
            ),
            (
                "water",
                "water_body",
            ),
            (
                "vegetation",
                "vegetation",
            ),
        )

        for feature_name, label in labels:
            mask = fused[
                feature_name
            ]

            structure = np.ones(
                (
                    3,
                    3,
                ),
                dtype=bool,
            )

            cleaned = ndimage.binary_opening(
                mask,
                structure=structure,
            )

            cleaned = ndimage.binary_closing(
                cleaned,
                structure=structure,
            )

            labeled, count = (
                ndimage.label(
                    cleaned
                )
            )

            component_records: list[
                dict[str, Any]
            ] = []

            for component_id in range(
                1,
                count + 1,
            ):
                ys, xs = np.where(
                    labeled
                    == component_id
                )

                pixel_count = len(
                    xs
                )

                if (
                    pixel_count
                    < minimum_pixels
                ):
                    continue

                component_records.append(
                    {
                        "component_id": int(
                            component_id
                        ),
                        "pixel_count": int(
                            pixel_count
                        ),
                        "bbox": [
                            float(
                                xs.min()
                            ),
                            float(
                                ys.min()
                            ),
                            float(
                                xs.max()
                            ),
                            float(
                                ys.max()
                            ),
                        ],
                        "label": label,
                    }
                )

            component_records.sort(
                key=lambda item: item[
                    "pixel_count"
                ],
                reverse=True,
            )

            regions.extend(
                component_records[
                    :max_regions
                ]
            )

        regions.sort(
            key=lambda item: item[
                "pixel_count"
            ],
            reverse=True,
        )

        return regions[
            :max_regions
        ]

    # ------------------------------------------------------------------
    # Physical area
    # ------------------------------------------------------------------

    def _resolve_pixel_area_m2(
        self,
        inputs: ModelInput,
    ) -> float | None:
        params = getattr(
            inputs,
            "params",
            None,
        )

        if not isinstance(
            params,
            dict,
        ):
            return None

        explicit = params.get(
            "pixel_area_m2"
        )

        if explicit is not None:
            value = self._positive_number(
                explicit
            )

            if value is not None:
                return value

        resolution = params.get(
            "resolution_m"
        )

        resolution_value = (
            self._positive_number(
                resolution
            )
        )

        if resolution_value is not None:
            return (
                resolution_value
                * resolution_value
            )

        return None

    def _calculate_physical_areas(
        self,
        fused: dict[str, np.ndarray],
        pixel_area_m2: float | None,
    ) -> dict[str, Any]:
        result = {
            "total_m2": None,
            "total_ha": None,
            "total_km2": None,
            "categories": {},
        }

        if pixel_area_m2 is None:
            return result

        total_pixels = 0

        for category, mask in fused.items():
            count = int(
                np.count_nonzero(
                    mask
                )
            )

            total_pixels += count

            area_m2 = (
                count
                * pixel_area_m2
            )

            result[
                "categories"
            ][category] = {
                "pixels": count,
                "area_m2": round(
                    area_m2,
                    4,
                ),
                "area_ha": round(
                    area_m2
                    / 10000.0,
                    6,
                ),
            }

        total_m2 = (
            total_pixels
            * pixel_area_m2
        )

        result[
            "total_m2"
        ] = round(
            total_m2,
            4,
        )

        result[
            "total_ha"
        ] = round(
            total_m2
            / 10000.0,
            6,
        )

        result[
            "total_km2"
        ] = round(
            total_m2
            / 1_000_000.0,
            8,
        )

        return result

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------

    def _create_overlay(
        self,
        optical_image: Image.Image,
        fused: dict[str, np.ndarray],
        boxes: list[dict[str, Any]],
    ) -> bytes:
        overlay = (
            optical_image
            .convert("RGBA")
        )

        draw = ImageDraw.Draw(
            overlay
        )

        for region in boxes:
            bbox = region.get(
                "bbox"
            )

            if not bbox:
                continue

            label = str(
                region.get(
                    "label",
                    "",
                )
            )

            if label == "water_body":
                outline = "#3b82f6"

            elif label == (
                "built_up_infrastructure"
            ):
                outline = "#f59e0b"

            else:
                outline = "#22c55e"

            draw.rectangle(
                bbox,
                outline=outline,
                width=2,
            )

        # Draw transparent category pixels.
        overlay_array = np.asarray(
            overlay
        ).copy()

        masks = (
            (
                fused["water"],
                (59, 130, 246, 80),
            ),
            (
                fused["built_up"],
                (245, 158, 11, 80),
            ),
            (
                fused["vegetation"],
                (34, 197, 94, 70),
            ),
        )

        for mask, rgba in masks:
            if (
                mask.shape[0]
                != overlay_array.shape[0]
                or mask.shape[1]
                != overlay_array.shape[1]
            ):
                continue

            overlay_array[
                mask
            ] = self._alpha_blend_pixel(
                overlay_array[
                    mask
                ],
                rgba,
            )

        result = Image.fromarray(
            overlay_array,
            mode="RGBA",
        )

        buffer = io.BytesIO()

        result.convert(
            "RGB"
        ).save(
            buffer,
            format="PNG",
        )

        return buffer.getvalue()

    @staticmethod
    def _alpha_blend_pixel(
        pixels: np.ndarray,
        rgba: tuple[int, int, int, int],
    ) -> np.ndarray:
        if len(
            pixels
        ) == 0:
            return pixels

        alpha = (
            rgba[3]
            / 255.0
        )

        color = np.array(
            rgba[:3],
            dtype=np.float32,
        )

        original = pixels[
            :, :3
        ].astype(
            np.float32
        )

        blended = (
            original
            * (1.0 - alpha)
            + color
            * alpha
        )

        result = pixels.copy()

        result[
            :, :3
        ] = np.clip(
            blended,
            0,
            255,
        ).astype(
            np.uint8
        )

        return result

    # ------------------------------------------------------------------
    # Answer composition
    # ------------------------------------------------------------------

    def _compose_answer(
        self,
        water_pct: float,
        urban_pct: float,
        vegetation_pct: float,
        boxes_count: int,
        agreement: float,
        physical_area_available: bool,
    ) -> str:
        answer = (
            "Optical-SAR fusion found cross-modal "
            "agreement for the supplied observations. "
            f"The fused evidence covers approximately "
            f"{urban_pct:.2f}% candidate built-up surface, "
            f"{water_pct:.2f}% candidate water surface, "
            f"and {vegetation_pct:.2f}% candidate vegetation."
        )

        answer += (
            f" {boxes_count} spatial evidence region(s) "
            "were extracted."
        )

        answer += (
            f" Cross-modal agreement score: "
            f"{agreement:.3f}."
        )

        if physical_area_available:
            answer += (
                " Physical-area estimates are available "
                "from supplied ground-resolution metadata."
            )
        else:
            answer += (
                " Physical area is not reported because "
                "valid ground-resolution metadata was not supplied."
            )

        return answer

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_param(
        inputs: ModelInput,
        key: str,
        default: Any = None,
    ) -> Any:
        params = getattr(
            inputs,
            "params",
            None,
        )

        if not isinstance(
            params,
            dict,
        ):
            return default

        return params.get(
            key,
            default,
        )

    def _get_positive_int_param(
        self,
        inputs: ModelInput,
        key: str,
        default: int,
    ) -> int:
        value = self._get_param(
            inputs,
            key,
            default,
        )

        try:
            value = int(
                value
            )

            if value <= 0:
                return default

            return value

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _positive_number(
        value: Any,
    ) -> float | None:
        try:
            number = float(
                value
            )

            if (
                not np.isfinite(
                    number
                )
                or number <= 0
            ):
                return None

            return number

        except (
            TypeError,
            ValueError,
        ):
            return None

    # ------------------------------------------------------------------
    # Error helper
    # ------------------------------------------------------------------

    def _error(
        self,
        inputs: ModelInput,
        start_time: float,
        message: str,
    ) -> ModelOutput:
        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            status="error",
            error=message,
            latency_ms=int(
                (
                    time.perf_counter()
                    - start_time
                )
                * 1000
            ),
        )


__all__ = [
    "OpticalSARFusionModel",
]