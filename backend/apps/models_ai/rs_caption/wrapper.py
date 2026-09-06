"""
RS_CAPTION specialist model wrapper.

Remote-sensing scene captioning:

    Image
      ↓
    Scene evidence extraction
      ↓
    Grounded caption

Scientific constraints
----------------------
- Never fabricate scene measurements.
- Never assume Sentinel-2 or any other sensor.
- Never invent geographic coordinates.
- Never use arbitrary fallback land-cover percentages.
- Never describe a generic RGB difference as a semantic class with
  unwarranted certainty.
- Image dimensions are reported only when actually available.
- Captions distinguish observable visual evidence from unsupported
  semantic interpretation.
- If a trained captioning model is configured, this wrapper can use it
  through the model manager.
- If no trained captioning model is available, the deterministic CV
  fallback is explicitly disclosed as a fallback.
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager

logger = logging.getLogger(__name__)


class RSCaptionModel:
    """
    Remote-sensing scene captioning specialist.

    The wrapper supports:

    1. A configured external/trained captioning implementation when one
       is available.
    2. A transparent image-composition fallback.

    The fallback is deliberately conservative. It describes visual
    characteristics that can be measured from the supplied image, rather
    than claiming a land-cover class as ground truth.
    """

    model_id = "RS_CAPTION"
    version = "3.0-grounded"
    task = "image_captioning"

    def __init__(self) -> None:
        self.caption_model_id = os.getenv(
            "RS_CAPTION_MODEL_ID",
            "",
        ).strip()

        self.allow_cv_fallback = (
            os.getenv(
                "RS_CAPTION_ALLOW_CV_FALLBACK",
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
                        "RS_CAPTION."
                    ),
                )

            # Prefer an explicitly configured trained captioning model.
            trained_result = (
                self._try_trained_caption_model(
                    image,
                    inputs,
                )
            )

            if trained_result is not None:
                caption, confidence, raw = (
                    trained_result
                )

                return self._success(
                    start_time=start_time,
                    caption=caption,
                    confidence=confidence,
                    raw=raw,
                )

            if not self.allow_cv_fallback:
                return self._error(
                    start_time,
                    (
                        "No trained RS_CAPTION model is configured "
                        "and deterministic CV fallback is disabled."
                    ),
                )

            # Transparent fallback.
            caption, evidence = (
                self._generate_grounded_caption(
                    image,
                    inputs,
                )
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
                caption=caption,
                answer=caption,
                confidence=evidence[
                    "confidence"
                ],
                latency_ms=latency,
                status="ok",
                raw={
                    "adaptation": "deterministic_cv_fallback",
                    "base_model": (
                        "visual-composition-captioner"
                    ),
                    "model_version": self.version,
                    "fallback": True,
                    "fallback_reason": (
                        "No configured trained captioning "
                        "model was available."
                    ),
                    "device": model_manager.device,
                    **evidence,
                },
            )

        except Exception as exc:
            logger.exception(
                "RS_CAPTION failed."
            )

            return self._error(
                start_time,
                str(exc),
            )

    # ------------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------------

    def _load_image(
        self,
        inputs: ModelInput,
    ) -> Image.Image | None:
        """
        Load the first supplied image.

        Multi-image tasks should be routed to a multi-image specialist
        instead of silently captioning only one image.
        """
        image_bytes = getattr(
            inputs,
            "image_bytes",
            None,
        )

        if isinstance(
            image_bytes,
            (list, tuple),
        ):
            if len(image_bytes) > 0:
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
                            "Unable to decode image bytes."
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
                    "Unable to decode image bytes."
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
            if len(image_paths) > 0:
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
                        "Unable to decode image path."
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
                        "Unable to decode image path."
                    )

        return None

    # ------------------------------------------------------------------
    # Trained captioning model
    # ------------------------------------------------------------------

    def _try_trained_caption_model(
        self,
        image: Image.Image,
        inputs: ModelInput,
    ) -> tuple[
        str,
        float,
        dict[str, Any],
    ] | None:
        """
        Attempt to use a configured trained captioning model.

        The repository currently does not require a specific captioning
        framework. Therefore this method deliberately checks the model
        manager instead of silently downloading or pretending to have a
        model.

        A registered model may expose one of:

            generate_caption(image, prompt=...)
            caption(image, prompt=...)
            predict(image, prompt=...)

        The result must contain a real caption string.
        """
        if not self.caption_model_id:
            return None

        try:
            model = model_manager.load_model(
                self.caption_model_id
            )

            if model is None:
                return None

            prompt = self._get_caption_prompt(
                inputs
            )

            result = None

            if hasattr(
                model,
                "generate_caption",
            ):
                result = model.generate_caption(
                    image,
                    prompt=prompt,
                )

            elif hasattr(
                model,
                "caption",
            ):
                result = model.caption(
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

            if result is None:
                return None

            caption = None
            confidence = None
            metadata: dict[str, Any] = {}

            if isinstance(
                result,
                str,
            ):
                caption = result

            elif isinstance(
                result,
                dict,
            ):
                caption = (
                    result.get(
                        "caption"
                    )
                    or result.get(
                        "answer"
                    )
                    or result.get(
                        "text"
                    )
                )

                confidence = (
                    result.get(
                        "confidence"
                    )
                )

                metadata = dict(
                    result
                )

            else:
                caption = (
                    getattr(
                        result,
                        "caption",
                        None,
                    )
                    or getattr(
                        result,
                        "answer",
                        None,
                    )
                )

                confidence = getattr(
                    result,
                    "confidence",
                    None,
                )

            if not caption:
                return None

            caption = str(
                caption
            ).strip()

            if not caption:
                return None

            parsed_confidence = (
                self._safe_confidence(
                    confidence
                )
            )

            if parsed_confidence is None:
                parsed_confidence = 0.80

            return (
                caption,
                parsed_confidence,
                {
                    "adaptation": "trained_model",
                    "base_model": (
                        self.caption_model_id
                    ),
                    "fallback": False,
                    "device": (
                        model_manager.device
                    ),
                    "model_metadata": metadata,
                },
            )

        except Exception:
            logger.exception(
                "Configured RS caption model failed."
            )

            return None

    # ------------------------------------------------------------------
    # Grounded fallback captioning
    # ------------------------------------------------------------------

    def _generate_grounded_caption(
        self,
        image: Image.Image,
        inputs: ModelInput,
    ) -> tuple[
        str,
        dict[str, Any],
    ]:
        """
        Generate a conservative caption from actual image composition.

        This is not a semantic remote-sensing classifier.

        It reports visual evidence such as:
        - dominant color composition;
        - texture;
        - brightness;
        - spatial variation;
        - image dimensions.

        It avoids asserting that a color pattern definitely represents
        a particular land-cover class.
        """
        image_rgb = image.convert(
            "RGB"
        )

        array = np.asarray(
            image_rgb,
            dtype=np.float32,
        )

        height, width = (
            array.shape[:2]
        )

        features = (
            self._analyze_visual_composition(
                array
            )
        )

        scene_terms: list[str] = []

        # --------------------------------------------------------------
        # Vegetation-like visual evidence
        # --------------------------------------------------------------

        green_fraction = features[
            "green_dominant_fraction"
        ]

        if green_fraction >= 0.25:
            scene_terms.append(
                "substantial green-toned surface"
            )
        elif green_fraction >= 0.10:
            scene_terms.append(
                "some green-toned surface"
            )

        # --------------------------------------------------------------
        # Water-like visual evidence
        # --------------------------------------------------------------

        blue_fraction = features[
            "blue_dominant_fraction"
        ]

        if blue_fraction >= 0.20:
            scene_terms.append(
                "a substantial blue-toned surface"
            )
        elif blue_fraction >= 0.08:
            scene_terms.append(
                "some blue-toned surface"
            )

        # --------------------------------------------------------------
        # Bright/open-surface evidence
        # --------------------------------------------------------------

        bright_fraction = features[
            "bright_fraction"
        ]

        if bright_fraction >= 0.40:
            scene_terms.append(
                "broad bright or high-reflectance-looking areas"
            )

        # --------------------------------------------------------------
        # Dark-surface evidence
        # --------------------------------------------------------------

        dark_fraction = features[
            "dark_fraction"
        ]

        if dark_fraction >= 0.30:
            scene_terms.append(
                "substantial dark-toned areas"
            )

        # --------------------------------------------------------------
        # Spatial texture
        # --------------------------------------------------------------

        texture = features[
            "texture"
        ]

        if texture >= 0.18:
            scene_terms.append(
                "strong spatial texture and heterogeneity"
            )
        elif texture >= 0.08:
            scene_terms.append(
                "moderate spatial texture"
            )
        else:
            scene_terms.append(
                "relatively uniform visual texture"
            )

        # --------------------------------------------------------------
        # Caption
        # --------------------------------------------------------------

        dimensions = (
            f"{width}×{height}"
        )

        if scene_terms:
            joined = self._join_terms(
                scene_terms
            )

            caption = (
                "Remote-sensing image "
                f"({dimensions}) showing "
                f"{joined}. "
                "These descriptions are based on image "
                "appearance and should not be treated as a "
                "semantic land-cover classification."
            )
        else:
            caption = (
                "Remote-sensing image "
                f"({dimensions}) with mixed visual surface "
                "characteristics. The available image evidence "
                "is insufficient for a more specific semantic "
                "caption."
            )

        confidence = (
            self._calculate_caption_confidence(
                features
            )
        )

        evidence = {
            "image_width": int(
                width
            ),
            "image_height": int(
                height
            ),
            "green_dominant_fraction": round(
                green_fraction,
                4,
            ),
            "blue_dominant_fraction": round(
                blue_fraction,
                4,
            ),
            "bright_fraction": round(
                bright_fraction,
                4,
            ),
            "dark_fraction": round(
                dark_fraction,
                4,
            ),
            "texture": round(
                texture,
                4,
            ),
            "mean_brightness": round(
                features[
                    "mean_brightness"
                ],
                4,
            ),
            "brightness_std": round(
                features[
                    "brightness_std"
                ],
                4,
            ),
            "confidence_basis": (
                "visual-composition evidence "
                "availability; not semantic truth probability"
            ),
        }

        return (
            caption,
            {
                "confidence": confidence,
                **evidence,
            },
        )

    # ------------------------------------------------------------------
    # Visual composition analysis
    # ------------------------------------------------------------------

    def _analyze_visual_composition(
        self,
        array: np.ndarray,
    ) -> dict[str, float]:
        rgb = np.clip(
            array,
            0.0,
            255.0,
        )

        r = rgb[
            :, :, 0
        ]

        g = rgb[
            :, :, 1
        ]

        b = rgb[
            :, :, 2
        ]

        brightness = (
            0.299 * r
            + 0.587 * g
            + 0.114 * b
        )

        # These are visual color relationships, not remote-sensing
        # spectral indices.
        green_dominant = (
            (g > r * 1.05)
            & (g > b * 1.02)
        )

        blue_dominant = (
            (b > r * 1.08)
            & (b > g * 1.02)
        )

        bright = (
            brightness >= 200.0
        )

        dark = (
            brightness <= 55.0
        )

        # Spatial variation without introducing synthetic data.
        gray = brightness / 255.0

        if (
            gray.shape[0] > 1
            and gray.shape[1] > 1
        ):
            vertical_difference = np.abs(
                np.diff(
                    gray,
                    axis=0,
                )
            )

            horizontal_difference = np.abs(
                np.diff(
                    gray,
                    axis=1,
                )
            )

            texture = float(
                (
                    vertical_difference.mean()
                    + horizontal_difference.mean()
                )
                / 2.0
            )

        else:
            texture = 0.0

        total = float(
            brightness.size
        )

        if total <= 0:
            return {
                "green_dominant_fraction": 0.0,
                "blue_dominant_fraction": 0.0,
                "bright_fraction": 0.0,
                "dark_fraction": 0.0,
                "texture": 0.0,
                "mean_brightness": 0.0,
                "brightness_std": 0.0,
            }

        return {
            "green_dominant_fraction": float(
                np.count_nonzero(
                    green_dominant
                )
                / total
            ),
            "blue_dominant_fraction": float(
                np.count_nonzero(
                    blue_dominant
                )
                / total
            ),
            "bright_fraction": float(
                np.count_nonzero(
                    bright
                )
                / total
            ),
            "dark_fraction": float(
                np.count_nonzero(
                    dark
                )
                / total
            ),
            "texture": float(
                texture
            ),
            "mean_brightness": float(
                brightness.mean()
            ),
            "brightness_std": float(
                brightness.std()
            ),
        }

    # ------------------------------------------------------------------
    # Caption prompt
    # ------------------------------------------------------------------

    def _get_caption_prompt(
        self,
        inputs: ModelInput,
    ) -> str:
        params = getattr(
            inputs,
            "params",
            None,
        )

        if isinstance(
            params,
            dict,
        ):
            custom_prompt = params.get(
                "caption_prompt"
            )

            if custom_prompt:
                return str(
                    custom_prompt
                ).strip()

        return (
            "Describe the supplied remote-sensing image "
            "conservatively using only visually supported "
            "information. Do not invent coordinates, sensor "
            "metadata, land-cover classes, measurements, or "
            "physical area."
        )

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _calculate_caption_confidence(
        self,
        features: dict[str, float],
    ) -> float:
        """
        Confidence is evidence completeness for the generated
        visual description, not probability that the semantic
        interpretation is correct.
        """
        score = 0.60

        if (
            features[
                "green_dominant_fraction"
            ]
            > 0.10
            or features[
                "blue_dominant_fraction"
            ]
            > 0.08
        ):
            score += 0.06

        if (
            features[
                "brightness_std"
            ]
            > 20.0
        ):
            score += 0.06

        if (
            features[
                "texture"
            ]
            > 0.05
        ):
            score += 0.06

        return round(
            min(
                0.82,
                score,
            ),
            3,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _join_terms(
        terms: list[str],
    ) -> str:
        if not terms:
            return ""

        if len(terms) == 1:
            return terms[0]

        if len(terms) == 2:
            return (
                f"{terms[0]} and {terms[1]}"
            )

        return (
            ", ".join(
                terms[:-1]
            )
            + f", and {terms[-1]}"
        )

    @staticmethod
    def _safe_confidence(
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

        except (
            TypeError,
            ValueError,
        ):
            return None

    def _success(
        self,
        start_time: float,
        caption: str,
        confidence: float,
        raw: dict[str, Any],
    ) -> ModelOutput:
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
            caption=caption,
            answer=caption,
            confidence=confidence,
            latency_ms=latency,
            status="ok",
            raw=raw,
        )

    def _error(
        self,
        start_time: float,
        message: str,
    ) -> ModelOutput:
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
            error=message,
            latency_ms=latency,
        )


__all__ = [
    "RSCaptionModel",
]