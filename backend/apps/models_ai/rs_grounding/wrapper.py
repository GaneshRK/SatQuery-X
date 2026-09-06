"""
RS_GROUNDING specialist model wrapper.

Remote-sensing text-guided visual grounding:

    Text prompt + Image
        ↓
    Target interpretation
        ↓
    Grounding model when configured
        ↓
    Candidate regions
        ↓
    Bounding boxes + evidence

Scientific constraints
----------------------
- Never fabricate bounding boxes.
- Never fabricate geographic coordinates.
- Never claim pixel coordinates are latitude/longitude.
- Never silently treat RGB color heuristics as a trained grounding model.
- A CV fallback is explicitly labeled as a fallback.
- Grounding confidence represents evidence quality, not guaranteed
  semantic truth.
- Physical area is not calculated unless valid ground-resolution
  metadata is supplied.
- No hardcoded satellite sensor assumptions.
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager

logger = logging.getLogger(__name__)


class RSGroundingModel:
    """
    Text-guided visual grounding specialist.

    Preferred execution
    --------------------
    If a compatible grounding model is registered with ModelManager,
    it is used.

    Supported model interfaces:

        model.ground(image, prompt=...)
        model.predict(image, prompt=...)
        model(image, prompt=...)

    Development fallback
    --------------------
    When no grounding model is available, the wrapper can perform
    conservative visual-proposal extraction for a small set of
    visually distinguishable targets.

    The fallback is NOT represented as Grounding DINO or SAM.
    """

    model_id = "RS_GROUNDING"
    version = "3.0-grounded"
    task = "text_guided_grounding"

    SUPPORTED_FALLBACK_TARGETS = {
        "water",
        "river",
        "lake",
        "reservoir",
        "ocean",
        "wetland",
        "vegetation",
        "forest",
        "tree",
        "trees",
        "green",
        "built-up",
        "built up",
        "building",
        "buildings",
        "urban",
        "structure",
        "city",
        "settlement",
        "road",
        "roads",
        "highway",
        "runway",
        "airport",
        "transportation",
    }

    def __init__(self) -> None:
        self.grounding_model_id = os.getenv(
            "GROUNDING_MODEL_ID",
            "",
        ).strip()

        self.allow_cv_fallback = (
            os.getenv(
                "RS_GROUNDING_ALLOW_CV_FALLBACK",
                "true",
            ).lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        inputs: ModelInput,
    ) -> ModelOutput:
        start_time = time.perf_counter()

        try:
            image = self._load_image(
                inputs
            )

            if image is None:
                return self._error(
                    start_time,
                    (
                        "No valid image was provided for "
                        "RS_GROUNDING."
                    ),
                )

            prompt = self._get_prompt(
                inputs
            )

            if not prompt:
                return self._error(
                    start_time,
                    (
                        "RS_GROUNDING requires a non-empty "
                        "text prompt."
                    ),
                )

            # ----------------------------------------------------------
            # Preferred trained grounding model
            # ----------------------------------------------------------

            trained_result = (
                self._try_trained_grounding(
                    image=image,
                    prompt=prompt,
                )
            )

            if trained_result is not None:
                return self._build_output(
                    start_time=start_time,
                    image=image,
                    prompt=prompt,
                    result=trained_result,
                    adaptation="trained_model",
                    fallback=False,
                )

            # ----------------------------------------------------------
            # Explicit fallback
            # ----------------------------------------------------------

            if not self.allow_cv_fallback:
                return self._error(
                    start_time,
                    (
                        "No trained grounding model is configured "
                        "and CV fallback is disabled."
                    ),
                )

            fallback_result = (
                self._visual_proposal_grounding(
                    image=image,
                    prompt=prompt,
                )
            )

            return self._build_output(
                start_time=start_time,
                image=image,
                prompt=prompt,
                result=fallback_result,
                adaptation="deterministic_cv_fallback",
                fallback=True,
            )

        except Exception as exc:
            logger.exception(
                "RS_GROUNDING failed."
            )

            return self._error(
                start_time,
                str(exc),
            )

    # ------------------------------------------------------------------
    # Input loading
    # ------------------------------------------------------------------

    def _load_image(
        self,
        inputs: ModelInput,
    ) -> Image.Image | None:
        image_bytes = getattr(
            inputs,
            "image_bytes",
            None,
        )

        if isinstance(
            image_bytes,
            (list, tuple),
        ):
            if image_bytes:
                payload = image_bytes[0]

                if isinstance(
                    payload,
                    (bytes, bytearray),
                ):
                    try:
                        with Image.open(
                            io.BytesIO(
                                payload
                            )
                        ) as image:
                            return image.convert(
                                "RGB"
                            )

                    except Exception:
                        logger.exception(
                            "Unable to decode grounding image bytes."
                        )

        elif isinstance(
            image_bytes,
            (bytes, bytearray),
        ):
            try:
                with Image.open(
                    io.BytesIO(
                        image_bytes
                    )
                ) as image:
                    return image.convert(
                        "RGB"
                    )

            except Exception:
                logger.exception(
                    "Unable to decode grounding image bytes."
                )

        image_paths = getattr(
            inputs,
            "image_paths",
            None,
        )

        if isinstance(
            image_paths,
            (list, tuple),
        ):
            if image_paths:
                path = Path(
                    str(
                        image_paths[0]
                    )
                )

                if not path.exists():
                    return None

                try:
                    with Image.open(
                        path
                    ) as image:
                        return image.convert(
                            "RGB"
                        )

                except Exception:
                    logger.exception(
                        "Unable to decode grounding image path."
                    )

        elif isinstance(
            image_paths,
            (str, Path),
        ):
            path = Path(
                str(
                    image_paths
                )
            )

            if path.exists():
                try:
                    with Image.open(
                        path
                    ) as image:
                        return image.convert(
                            "RGB"
                        )

                except Exception:
                    logger.exception(
                        "Unable to decode grounding image path."
                    )

        return None

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def _get_prompt(
        self,
        inputs: ModelInput,
    ) -> str:
        text_prompt = getattr(
            inputs,
            "text_prompt",
            None,
        )

        if text_prompt:
            return str(
                text_prompt
            ).strip()

        question = getattr(
            inputs,
            "question",
            None,
        )

        if question:
            return str(
                question
            ).strip()

        params = getattr(
            inputs,
            "params",
            None,
        )

        if isinstance(
            params,
            dict,
        ):
            prompt = params.get(
                "grounding_prompt"
            )

            if prompt:
                return str(
                    prompt
                ).strip()

        return ""

    # ------------------------------------------------------------------
    # Trained grounding model
    # ------------------------------------------------------------------

    def _try_trained_grounding(
        self,
        image: Image.Image,
        prompt: str,
    ) -> dict[str, Any] | None:
        """
        Try a registered grounding implementation.

        The wrapper does not download or pretend to load a model.
        ModelManager must provide the actual implementation.
        """
        if not self.grounding_model_id:
            return None

        try:
            model = model_manager.load_model(
                self.grounding_model_id
            )

            if model is None:
                return None

            result = None

            if hasattr(
                model,
                "ground",
            ):
                result = model.ground(
                    image,
                    prompt=prompt,
                )

            elif hasattr(
                model,
                "predict",
            ):
                result = model.predict(
                    image,
                    prompt=prompt,
                )

            elif callable(
                model
            ):
                result = model(
                    image,
                    prompt=prompt,
                )

            if result is None:
                return None

            boxes = self._normalize_boxes(
                result
            )

            if boxes is None:
                return None

            confidence = self._extract_confidence(
                result,
                boxes,
            )

            return {
                "boxes": boxes,
                "confidence": confidence,
                "model_id": (
                    self.grounding_model_id
                ),
                "raw_result": (
                    self._safe_raw_result(
                        result
                    )
                ),
            }

        except Exception:
            logger.exception(
                "Configured grounding model failed."
            )

            return None

    # ------------------------------------------------------------------
    # CV fallback
    # ------------------------------------------------------------------

    def _visual_proposal_grounding(
        self,
        image: Image.Image,
        prompt: str,
    ) -> dict[str, Any]:
        """
        Produce conservative visual candidate regions.

        This fallback is intended for development environments where a
        trained grounding model is not installed.

        It does not claim that the candidates are confirmed objects.
        """
        array = np.asarray(
            image.convert("RGB"),
            dtype=np.float32,
        )

        target = self._resolve_fallback_target(
            prompt
        )

        if target is None:
            return {
                "boxes": [],
                "confidence": 0.20,
                "label": "unsupported_visual_target",
                "fallback_reason": (
                    "The requested target cannot be grounded "
                    "reliably using the deterministic visual fallback."
                ),
            }

        mask, label = (
            self._create_candidate_mask(
                array,
                target,
            )
        )

        cleaned = self._clean_candidate_mask(
            mask
        )

        boxes = self._extract_candidate_boxes(
            cleaned,
            label,
        )

        confidence = self._calculate_fallback_confidence(
            cleaned,
            boxes,
        )

        return {
            "boxes": boxes,
            "confidence": confidence,
            "label": label,
            "fallback_reason": (
                "No trained grounding model was available; "
                "regions are visual candidates generated from "
                "image appearance."
            ),
        }

    # ------------------------------------------------------------------
    # Target resolution
    # ------------------------------------------------------------------

    def _resolve_fallback_target(
        self,
        prompt: str,
    ) -> str | None:
        normalized = (
            prompt.lower()
            .strip()
            .replace(
                ",",
                " ",
            )
        )

        # Longest / most specific phrases first.
        if (
            "built-up" in normalized
            or "built up" in normalized
        ):
            return "built_up"

        for target in (
            "water",
            "river",
            "lake",
            "reservoir",
            "ocean",
            "wetland",
            "vegetation",
            "forest",
            "tree",
            "trees",
            "green",
            "building",
            "buildings",
            "urban",
            "structure",
            "city",
            "settlement",
            "road",
            "roads",
            "highway",
            "runway",
            "airport",
            "transportation",
        ):
            if target in normalized:
                return target

        return None

    # ------------------------------------------------------------------
    # Candidate mask generation
    # ------------------------------------------------------------------

    def _create_candidate_mask(
        self,
        array: np.ndarray,
        target: str,
    ) -> tuple[
        np.ndarray,
        str,
    ]:
        r = array[
            :, :, 0
        ]

        g = array[
            :, :, 1
        ]

        b = array[
            :, :, 2
        ]

        brightness = (
            0.299 * r
            + 0.587 * g
            + 0.114 * b
        )

        # --------------------------------------------------------------
        # Water
        # --------------------------------------------------------------

        if target in {
            "water",
            "river",
            "lake",
            "reservoir",
            "ocean",
            "wetland",
        }:
            mask = (
                (b > r * 1.05)
                & (b >= g * 0.95)
                & (b < 190.0)
            )

            return (
                mask,
                "water_candidate",
            )

        # --------------------------------------------------------------
        # Vegetation
        # --------------------------------------------------------------

        if target in {
            "vegetation",
            "forest",
            "tree",
            "trees",
            "green",
        }:
            mask = (
                (g > r * 1.05)
                & (g > b * 1.02)
            )

            return (
                mask,
                "vegetation_candidate",
            )

        # --------------------------------------------------------------
        # Built environment
        # --------------------------------------------------------------

        if target in {
            "built_up",
            "building",
            "buildings",
            "urban",
            "structure",
            "city",
            "settlement",
        }:
            chromatic_variation = (
                np.maximum(
                    np.maximum(
                        np.abs(r - g),
                        np.abs(g - b),
                    ),
                    np.abs(r - b),
                )
            )

            mask = (
                (chromatic_variation < 35.0)
                & (brightness > 90.0)
            )

            return (
                mask,
                "built_environment_candidate",
            )

        # --------------------------------------------------------------
        # Transportation infrastructure
        # --------------------------------------------------------------

        if target in {
            "road",
            "roads",
            "highway",
            "runway",
            "airport",
            "transportation",
        }:
            mask = (
                (brightness > 90.0)
                & (brightness < 235.0)
            )

            # Prefer elongated local structures.
            horizontal = ndimage.maximum_filter(
                mask,
                size=(
                    3,
                    11,
                ),
            )

            vertical = ndimage.maximum_filter(
                mask,
                size=(
                    11,
                    3,
                ),
            )

            mask = (
                horizontal
                | vertical
            )

            return (
                mask,
                "transportation_candidate",
            )

        return (
            np.zeros(
                array.shape[:2],
                dtype=bool,
            ),
            "unknown_candidate",
        )

    # ------------------------------------------------------------------
    # Morphological cleaning
    # ------------------------------------------------------------------

    def _clean_candidate_mask(
        self,
        mask: np.ndarray,
    ) -> np.ndarray:
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

        return cleaned

    # ------------------------------------------------------------------
    # Region extraction
    # ------------------------------------------------------------------

    def _extract_candidate_boxes(
        self,
        mask: np.ndarray,
        label: str,
    ) -> list[dict[str, Any]]:
        labeled, number = (
            ndimage.label(
                mask
            )
        )

        if number <= 0:
            return []

        objects = ndimage.find_objects(
            labeled
        )

        candidates: list[
            dict[str, Any]
        ] = []

        minimum_pixels = max(
            16,
            int(
                mask.size
                * 0.00002
            ),
        )

        for component_id, component_slice in enumerate(
            objects,
            start=1,
        ):
            if component_slice is None:
                continue

            ys, xs = np.where(
                labeled[
                    component_slice
                ]
                == component_id
            )

            pixel_count = len(
                xs
            )

            if pixel_count < minimum_pixels:
                continue

            y_slice, x_slice = (
                component_slice
            )

            y1 = float(
                y_slice.start
            )

            y2 = float(
                y_slice.stop - 1
            )

            x1 = float(
                x_slice.start
            )

            x2 = float(
                x_slice.stop - 1
            )

            box_width = max(
                1.0,
                x2 - x1 + 1.0,
            )

            box_height = max(
                1.0,
                y2 - y1 + 1.0,
            )

            box_area = (
                box_width
                * box_height
            )

            density = (
                pixel_count
                / box_area
            )

            candidates.append(
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label": label,
                    "pixel_count": int(
                        pixel_count
                    ),
                    "density": round(
                        float(
                            density
                        ),
                        4,
                    ),
                    "coordinate_space": (
                        "image_pixels"
                    ),
                }
            )

        candidates.sort(
            key=lambda item: item[
                "pixel_count"
            ],
            reverse=True,
        )

        # Limit the number of returned regions so a noisy fallback does
        # not flood the orchestrator.
        return candidates[
            :50
        ]

    # ------------------------------------------------------------------
    # Fallback confidence
    # ------------------------------------------------------------------

    def _calculate_fallback_confidence(
        self,
        mask: np.ndarray,
        boxes: list[dict[str, Any]],
    ) -> float:
        """
        Confidence describes strength of the visual proposal only.
        It is deliberately capped below a high semantic-confidence level.
        """
        if not boxes:
            return 0.20

        total = float(
            mask.size
        )

        coverage = (
            np.count_nonzero(
                mask
            )
            / total
            if total > 0
            else 0.0
        )

        mean_density = float(
            np.mean(
                [
                    item.get(
                        "density",
                        0.0,
                    )
                    for item in boxes
                ]
            )
        )

        score = (
            0.40
            + min(
                0.20,
                coverage
                * 2.0,
            )
            + min(
                0.15,
                mean_density
                * 0.15,
            )
        )

        return round(
            float(
                np.clip(
                    score,
                    0.20,
                    0.75,
                )
            ),
            3,
        )

    # ------------------------------------------------------------------
    # Output construction
    # ------------------------------------------------------------------

    def _build_output(
        self,
        start_time: float,
        image: Image.Image,
        prompt: str,
        result: dict[str, Any],
        adaptation: str,
        fallback: bool,
    ) -> ModelOutput:
        boxes = result.get(
            "boxes"
        )

        if not isinstance(
            boxes,
            list,
        ):
            boxes = []

        normalized_boxes = (
            self._normalize_box_list(
                boxes
            )
        )

        confidence = (
            self._safe_confidence(
                result.get(
                    "confidence"
                )
            )
        )

        if confidence is None:
            confidence = (
                0.20
                if not normalized_boxes
                else 0.50
            )

        overlay = (
            self._create_overlay(
                image,
                normalized_boxes,
            )
        )

        label = (
            result.get(
                "label"
            )
            or self._prompt_label(
                prompt
            )
        )

        if fallback:
            answer = (
                f"Found {len(normalized_boxes)} "
                f"candidate region(s) matching "
                f"'{prompt}'. These are visual candidates "
                "from the deterministic fallback and are not "
                "equivalent to a trained grounding model's "
                "semantic detections."
            )
        else:
            answer = (
                f"The configured grounding model found "
                f"{len(normalized_boxes)} region(s) matching "
                f"'{prompt}'."
            )

        latency = int(
            (
                time.perf_counter()
                - start_time
            )
            * 1000
        )

        raw = {
            "adaptation": adaptation,
            "base_model": (
                result.get(
                    "model_id"
                )
                if not fallback
                else "visual-proposal-grounding"
            ),
            "model_version": self.version,
            "fallback": fallback,
            "target_prompt": prompt,
            "label_detected": label,
            "regions_found": len(
                normalized_boxes
            ),
            "coordinate_space": (
                "image_pixels"
            ),
            "geographic_coordinates_available": False,
        }

        if fallback:
            raw[
                "fallback_reason"
            ] = result.get(
                "fallback_reason"
            )

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=answer,
            boxes=normalized_boxes,
            overlay=overlay,
            confidence=confidence,
            latency_ms=latency,
            status="ok",
            raw=raw,
        )

    # ------------------------------------------------------------------
    # Box normalization
    # ------------------------------------------------------------------

    def _normalize_boxes(
        self,
        result: Any,
    ) -> list[dict[str, Any]] | None:
        if isinstance(
            result,
            dict,
        ):
            candidate = (
                result.get(
                    "boxes"
                )
                or result.get(
                    "detections"
                )
                or result.get(
                    "regions"
                )
            )

        else:
            candidate = getattr(
                result,
                "boxes",
                None,
            )

        if candidate is None:
            return None

        if not isinstance(
            candidate,
            (list, tuple),
        ):
            return None

        return self._normalize_box_list(
            list(candidate)
        )

    def _normalize_box_list(
        self,
        boxes: list[Any],
    ) -> list[dict[str, Any]]:
        normalized: list[
            dict[str, Any]
        ] = []

        for box in boxes:
            if isinstance(
                box,
                dict,
            ):
                x1 = self._number(
                    box.get(
                        "x1"
                    )
                    if box.get(
                        "x1"
                    )
                    is not None
                    else box.get(
                        "xmin"
                    )
                )

                y1 = self._number(
                    box.get(
                        "y1"
                    )
                    if box.get(
                        "y1"
                    )
                    is not None
                    else box.get(
                        "ymin"
                    )
                )

                x2 = self._number(
                    box.get(
                        "x2"
                    )
                    if box.get(
                        "x2"
                    )
                    is not None
                    else box.get(
                        "xmax"
                    )
                )

                y2 = self._number(
                    box.get(
                        "y2"
                    )
                    if box.get(
                        "y2"
                    )
                    is not None
                    else box.get(
                        "ymax"
                    )
                )

                label = (
                    box.get(
                        "label"
                    )
                    or box.get(
                        "class_name"
                    )
                    or box.get(
                        "category"
                    )
                    or "candidate"
                )

                confidence = self._safe_confidence(
                    box.get(
                        "confidence"
                    )
                )

                coordinate_space = (
                    box.get(
                        "coordinate_space"
                    )
                    or "image_pixels"
                )

            elif isinstance(
                box,
                (list, tuple),
            ) and len(box) >= 4:
                x1 = self._number(
                    box[0]
                )
                y1 = self._number(
                    box[1]
                )
                x2 = self._number(
                    box[2]
                )
                y2 = self._number(
                    box[3]
                )

                label = "candidate"
                confidence = None
                coordinate_space = (
                    "image_pixels"
                )

            else:
                continue

            if None in (
                x1,
                y1,
                x2,
                y2,
            ):
                continue

            if x2 < x1:
                x1, x2 = (
                    x2,
                    x1,
                )

            if y2 < y1:
                y1, y2 = (
                    y2,
                    y1,
                )

            item = {
                "x1": float(
                    x1
                ),
                "y1": float(
                    y1
                ),
                "x2": float(
                    x2
                ),
                "y2": float(
                    y2
                ),
                "label": str(
                    label
                ),
                "coordinate_space": str(
                    coordinate_space
                ),
            }

            if confidence is not None:
                item[
                    "confidence"
                ] = confidence

            normalized.append(
                item
            )

        return normalized[
            :100
        ]

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------

    def _create_overlay(
        self,
        image: Image.Image,
        boxes: list[dict[str, Any]],
    ) -> bytes:
        overlay = (
            image.convert(
                "RGBA"
            )
        )

        draw = ImageDraw.Draw(
            overlay
        )

        for box in boxes:
            if (
                box.get(
                    "coordinate_space"
                )
                != "image_pixels"
            ):
                continue

            coordinates = [
                box["x1"],
                box["y1"],
                box["x2"],
                box["y2"],
            ]

            draw.rectangle(
                coordinates,
                outline="#3b82f6",
                width=3,
            )

        buffer = io.BytesIO()

        overlay.convert(
            "RGB"
        ).save(
            buffer,
            format="PNG",
        )

        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prompt_label(
        prompt: str,
    ) -> str:
        return (
            prompt[:120]
            if prompt
            else "candidate"
        )

    @staticmethod
    def _extract_confidence(
        result: Any,
        boxes: list[dict[str, Any]],
    ) -> float:
        if isinstance(
            result,
            dict,
        ):
            value = result.get(
                "confidence"
            )

            parsed = RSGroundingModel._safe_confidence(
                value
            )

            if parsed is not None:
                return parsed

        confidences = [
            item.get(
                "confidence"
            )
            for item in boxes
            if item.get(
                "confidence"
            ) is not None
        ]

        if confidences:
            return round(
                float(
                    np.mean(
                        confidences
                    )
                ),
                3,
            )

        return 0.50

    @staticmethod
    def _safe_raw_result(
        result: Any,
    ) -> dict[str, Any]:
        if isinstance(
            result,
            dict,
        ):
            safe: dict[str, Any] = {}

            for key, value in result.items():
                if key in {
                    "boxes",
                    "detections",
                    "regions",
                    "confidence",
                }:
                    continue

                if isinstance(
                    value,
                    (
                        str,
                        int,
                        float,
                        bool,
                        type(None),
                    ),
                ):
                    safe[key] = value

            return safe

        return {}

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            number = float(
                value
            )

            if not np.isfinite(
                number
            ):
                return None

            return number

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _safe_confidence(
        value: Any,
    ) -> float | None:
        number = (
            RSGroundingModel._number(
                value
            )
        )

        if number is None:
            return None

        return round(
            float(
                np.clip(
                    number,
                    0.0,
                    1.0,
                )
            ),
            3,
        )

    @staticmethod
    def _error(
        start_time: float,
        message: str,
    ) -> ModelOutput:
        return ModelOutput(
            model_id="RS_GROUNDING",
            version="3.0-grounded",
            task="text_guided_grounding",
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
    "RSGroundingModel",
]