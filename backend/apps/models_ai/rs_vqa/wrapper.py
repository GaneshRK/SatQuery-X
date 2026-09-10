"""
SatQuery-X RS_VQA specialist wrapper.

Remote-Sensing Visual Question Answering
-----------------------------------------
Input:
    Image + Question + optional upstream evidence

Output:
    Answer + Confidence + Provenance

Design principles
-----------------
- Prefer a configured real VQA/VLM model when available.
- Never fabricate scientific measurements.
- Never infer physical area, land-cover percentage, sensor,
  resolution, or geolocation from an RGB preview alone.
- Use upstream specialist evidence when it is available.
- Keep fallback answers explicitly limited to visual observations.
- Do not expose chain-of-thought.
- Preserve concise provenance so the orchestrator can audit the answer.
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


class RSVQAModel:
    """
    Remote-sensing visual question answering specialist.

    The wrapper supports three execution paths:

    1. Configured VQA/VLM model
    2. Structured upstream evidence
    3. Conservative visual fallback

    The fallback is deliberately NOT a substitute for a trained
    remote-sensing VQA model.
    """

    model_id = "RS_VQA"
    version = "3.0-grounded"
    task = "visual_question_answering"

    def __init__(self) -> None:
        self.preferred_model = os.getenv(
            "VQA_MODEL_ID",
            "",
        ).strip()
        self.checkpoint = os.getenv("VQA_CHECKPOINT", "").strip()

        self.allow_visual_fallback = (
            os.getenv(
                "SATQUERY_VQA_VISUAL_FALLBACK",
                "true",
            )
            .strip()
            .lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        )

    # ==================================================================
    # Public API
    # ==================================================================

    def predict(
        self,
        inputs: ModelInput,
    ) -> ModelOutput:
        start_time = time.perf_counter()

        question = self._normalize_question(
            inputs.question
        )

        # --------------------------------------------------------------
        # Validate image availability.
        # --------------------------------------------------------------

        image = self._load_image(
            inputs
        )

        if image is None:
            return self._error_output(
                "No valid image was provided for RS_VQA.",
                start_time,
                question=question,
            )

        # --------------------------------------------------------------
        # 1. Prefer a configured real VQA/VLM.
        # --------------------------------------------------------------

        if self.preferred_model or self.checkpoint:
            model_output = self._try_configured_model(
                inputs,
                image,
                question,
                start_time,
            )

            if model_output is not None:
                return model_output

        # --------------------------------------------------------------
        # 2. Use structured upstream evidence.
        # --------------------------------------------------------------

        evidence_output = self._answer_from_evidence(
            inputs,
            question,
            image,
            start_time,
        )

        if evidence_output is not None:
            return evidence_output

        # --------------------------------------------------------------
        # 3. Conservative visual fallback.
        # --------------------------------------------------------------

        if self.allow_visual_fallback:
            return self._visual_fallback(
                image,
                question,
                start_time,
            )

        return self._error_output(
            (
                "No configured RS-VQA model or sufficient "
                "upstream evidence is available for this question."
            ),
            start_time,
            question=question,
        )

    # ==================================================================
    # Configured VQA/VLM
    # ==================================================================

    def _try_configured_model(
        self,
        inputs: ModelInput,
        image: Image.Image,
        question: str,
        start_time: float,
    ) -> ModelOutput | None:
        """
        Attempt to execute a registered real VQA/VLM model.

        The model manager intentionally returns None when the configured
        model has not been registered. That condition causes the wrapper
        to continue to the evidence/fallback path instead of inventing
        a model result.
        """

        model_id = self.preferred_model or self.checkpoint

        def factory():
            from apps.models_ai.rs_vqa.hf_model import HuggingFaceRSVQA
            return HuggingFaceRSVQA(model_id, device=model_manager.device)

        model = model_manager.load_model(
            model_id,
            factory_fn=factory,
            )

        if model is None:
            logger.info(
                "Configured VQA model '%s' is not registered.",
                self.preferred_model,
            )
            return None

        try:
            result = self._invoke_vqa_model(
                model,
                image,
                question,
                inputs,
            )

            normalized = self._normalize_model_result(
                result
            )

            if normalized is None:
                model_manager.mark_prediction(
                    model_id,
                    success=False,
                    error="Model returned no usable VQA result.",
                )
                return None

            answer = normalized.get(
                "answer"
            )

            if not answer:
                model_manager.mark_prediction(
                    model_id,
                    success=False,
                    error="VQA model returned no answer.",
                )
                return None

            confidence = self._safe_confidence(
                normalized.get(
                    "confidence"
                )
            )

            latency = int(
                (
                    time.perf_counter()
                    - start_time
                )
                * 1000
            )

            model_manager.mark_prediction(
                model_id,
                success=True,
            )

            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                answer=str(
                    answer
                ),
                confidence=confidence,
                latency_ms=latency,
                status="ok",
                raw={
                    "execution": "configured_model",
                    "base_model": model_id,
                    "device": model_manager.device,
                    "question": question,
                    "provenance": normalized.get(
                        "provenance",
                        "Answer generated by configured VQA/VLM model.",
                    ),
                },
            )

        except Exception as exc:
            model_manager.mark_prediction(
                model_id,
                success=False,
                error=str(exc),
            )

            logger.exception(
                "Configured VQA model '%s' failed.",
                model_id,
            )

            return None

    def _invoke_vqa_model(
        self,
        model: Any,
        image: Image.Image,
        question: str,
        inputs: ModelInput,
    ) -> Any:
        """
        Support several common specialist interfaces.

        No model-specific implementation is assumed to be present.
        """

        if hasattr(
            model,
            "answer",
        ):
            return model.answer(
                image=image,
                question=question,
                inputs=inputs,
            )

        if hasattr(
            model,
            "predict",
        ):
            try:
                return model.predict(
                    image=image,
                    question=question,
                    inputs=inputs,
                )
            except TypeError:
                return model.predict(
                    image,
                    question,
                )

        if hasattr(
            model,
            "generate",
        ):
            try:
                return model.generate(
                    image=image,
                    question=question,
                )
            except TypeError:
                return model.generate(
                    image,
                    question,
                )

        if callable(model):
            try:
                return model(
                    image=image,
                    question=question,
                )
            except TypeError:
                return model(
                    image,
                    question,
                )

        raise TypeError(
            (
                f"Configured VQA model '{self.preferred_model}' "
                "does not expose a supported inference interface."
            )
        )

    # ==================================================================
    # Structured evidence answering
    # ==================================================================

    def _answer_from_evidence(
        self,
        inputs: ModelInput,
        question: str,
        image: Image.Image,
        start_time: float,
    ) -> ModelOutput | None:
        """
        Answer only when upstream evidence actually supports the
        requested question.

        This prevents RS_VQA from independently manufacturing
        scientific measurements that should come from dedicated
        specialists such as change detection, grounding, GIS, or
        spectral analysis.
        """

        evidence = self._extract_evidence(
            inputs
        )

        if not evidence:
            return None

        question_type = self._classify_question(
            question
        )

        answer: str | None = None
        provenance: str | None = None
        evidence_confidence: float | None = None

        # --------------------------------------------------------------
        # Change-related questions
        # --------------------------------------------------------------

        if question_type == "change":
            change = self._find_evidence(
                evidence,
                (
                    "CHANGE_DETECTION",
                    "change_detection",
                    "change",
                ),
            )

            if change:
                answer = self._answer_change_question(
                    change,
                    question,
                )

                if answer:
                    provenance = (
                        "Answer grounded in upstream "
                        "change-detection evidence."
                    )

                    evidence_confidence = (
                        self._extract_confidence(
                            change
                        )
                    )

        # --------------------------------------------------------------
        # Location / geographic questions
        # --------------------------------------------------------------

        elif question_type == "location":
            location = self._find_evidence(
                evidence,
                (
                    "GIS",
                    "GEOSPATIAL",
                    "LOCATION",
                    "MAP_CONTEXT",
                    "grounding",
                ),
            )

            if location:
                answer = self._answer_location_question(
                    location,
                    question,
                )

                if answer:
                    provenance = (
                        "Answer grounded in available "
                        "geospatial evidence."
                    )

                    evidence_confidence = (
                        self._extract_confidence(
                            location
                        )
                    )

        # --------------------------------------------------------------
        # Grounding/object questions
        # --------------------------------------------------------------

        elif question_type == "object":
            grounding = self._find_evidence(
                evidence,
                (
                    "RS_GROUNDING",
                    "GROUNDING",
                    "grounding",
                    "objects",
                ),
            )

            if grounding:
                answer = self._answer_object_question(
                    grounding,
                    question,
                )

                if answer:
                    provenance = (
                        "Answer grounded in upstream "
                        "visual-grounding evidence."
                    )

                    evidence_confidence = (
                        self._extract_confidence(
                            grounding
                        )
                    )

        # --------------------------------------------------------------
        # Metadata questions
        # --------------------------------------------------------------

        elif question_type == "metadata":
            metadata = self._find_evidence(
                evidence,
                (
                    "METADATA",
                    "IMAGE_METADATA",
                    "metadata",
                ),
            )

            if metadata:
                answer = self._answer_metadata_question(
                    metadata,
                    question,
                )

                if answer:
                    provenance = (
                        "Answer grounded in supplied "
                        "imagery metadata."
                    )

                    evidence_confidence = (
                        self._extract_confidence(
                            metadata
                        )
                    )

        if not answer:
            return None

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
            confidence=(
                self._safe_confidence(
                    evidence_confidence,
                    default=0.72,
                )
            ),
            latency_ms=latency,
            status="ok",
            raw={
                "execution": "upstream_evidence",
                "question": question,
                "question_type": question_type,
                "provenance": provenance,
                "evidence_keys": list(
                    evidence.keys()
                ),
                "device": model_manager.device,
            },
        )

    # ==================================================================
    # Conservative visual fallback
    # ==================================================================

    def _visual_fallback(
        self,
        image: Image.Image,
        question: str,
        start_time: float,
    ) -> ModelOutput:
        """
        Produce a conservative visual answer.

        This path intentionally does NOT claim:
        - physical area
        - land-cover percentages
        - sensor identity
        - geographic coordinates
        - spectral indices
        - scientifically validated class probabilities

        It only describes directly observable visual properties.
        """

        arr = np.asarray(
            image.convert("RGB")
        )

        height, width = arr.shape[:2]

        answer: str

        question_type = self._classify_question(
            question
        )

        if question_type == "metadata":
            answer = (
                f"The available image is approximately "
                f"{width} × {height} pixels. "
                "The image alone does not establish its satellite "
                "sensor, ground resolution, CRS, or acquisition date."
            )

        elif question_type == "object":
            answer = self._describe_visible_scene(
                arr
            )

        elif question_type == "location":
            answer = (
                "The image alone does not provide enough reliable "
                "evidence to determine a geographic location. "
                "A georeference, map context, or location-specific "
                "metadata is required."
            )

        elif question_type == "change":
            answer = (
                "A change assessment requires two temporally distinct "
                "observations or validated change-detection evidence. "
                "A single image is insufficient to establish change."
            )

        elif self._is_yes_no_question(
            question
        ):
            answer = (
                "The available visual preview is not sufficient "
                "to answer that reliably. A dedicated remote-sensing "
                "analysis or trained VQA model is required."
            )

        else:
            answer = self._describe_visible_scene(
                arr
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
            answer=answer,
            confidence=0.55,
            latency_ms=latency,
            status="ok",
            raw={
                "execution": "visual_fallback",
                "base_model": "deterministic_visual_observation",
                "question": question,
                "question_type": question_type,
                "device": model_manager.device,
                "disclosure": (
                    "Fallback describes visible image properties only; "
                    "it does not provide remote-sensing semantic "
                    "measurements or geospatial ground truth."
                ),
                "image_dimensions": [
                    width,
                    height,
                ],
            },
        )

    # ==================================================================
    # Visual description
    # ==================================================================

    def _describe_visible_scene(
        self,
        arr: np.ndarray,
    ) -> str:
        """
        Describe broad visual characteristics without converting
        RGB colors into unsupported land-cover percentages.
        """

        rgb = arr.astype(
            np.float32
        )

        mean_rgb = np.mean(
            rgb,
            axis=(0, 1),
        )

        brightness = float(
            np.mean(
                mean_rgb
            )
        )

        spread = float(
            np.std(
                rgb
            )
        )

        dominant_channel = int(
            np.argmax(
                mean_rgb
            )
        )

        channel_names = {
            0: "red",
            1: "green",
            2: "blue",
        }

        dominant = channel_names.get(
            dominant_channel,
            "mixed",
        )

        if brightness < 70:
            illumination = "relatively dark"
        elif brightness > 190:
            illumination = "relatively bright"
        else:
            illumination = "moderately illuminated"

        if spread < 25:
            texture = "fairly uniform in color"
        elif spread > 65:
            texture = "visually varied"
        else:
            texture = "moderately varied"

        return (
            f"The available preview is {illumination} and "
            f"{texture}. Its average RGB appearance is dominated "
            f"by the {dominant} channel. These observations describe "
            f"the displayed image only and should not be treated as "
            f"validated land-cover classification."
        )

    # ==================================================================
    # Question handling
    # ==================================================================

    @staticmethod
    def _normalize_question(
        question: str | None,
    ) -> str:
        value = (
            question
            or "What is visible in this remote-sensing image?"
        )

        return " ".join(
            str(value)
            .strip()
            .lower()
            .split()
        )

    @staticmethod
    def _classify_question(
        question: str,
    ) -> str:
        q = question.lower()

        if any(
            keyword in q
            for keyword in (
                "change",
                "changed",
                "difference",
                "before and after",
                "temporal",
                "demolished",
                "new construction",
                "lost",
                "gained",
            )
        ):
            return "change"

        if any(
            keyword in q
            for keyword in (
                "where",
                "location",
                "coordinates",
                "latitude",
                "longitude",
                "crs",
                "projection",
                "georeference",
            )
        ):
            return "location"

        if any(
            keyword in q
            for keyword in (
                "sensor",
                "satellite",
                "resolution",
                "dimension",
                "pixel size",
                "acquisition date",
                "capture date",
                "metadata",
            )
        ):
            return "metadata"

        if any(
            keyword in q
            for keyword in (
                "where is the building",
                "where are the buildings",
                "where is the road",
                "where are the roads",
                "where is the river",
                "where is the lake",
                "find the building",
                "find the road",
                "locate the building",
                "locate the road",
                "object",
                "objects",
                "building",
                "buildings",
            )
        ):
            return "object"

        return "general"

    @staticmethod
    def _is_yes_no_question(
        question: str,
    ) -> bool:
        prefixes = (
            "is ",
            "are ",
            "does ",
            "do ",
            "has ",
            "have ",
            "can ",
            "was ",
            "were ",
        )

        return question.lower().startswith(
            prefixes
        )

    # ==================================================================
    # Evidence extraction
    # ==================================================================

    def _extract_evidence(
        self,
        inputs: ModelInput,
    ) -> dict[str, Any]:
        """
        Extract structured evidence from ModelInput.params.

        Different orchestrator versions may use either:
            params["evidence"]
        or:
            params["evidence_bundle"]

        Both are supported.
        """

        params = getattr(
            inputs,
            "params",
            None,
        )

        if not isinstance(
            params,
            dict,
        ):
            return {}

        evidence = params.get(
            "evidence"
        )

        if evidence is None:
            evidence = params.get(
                "evidence_bundle"
            )

        if isinstance(
            evidence,
            dict,
        ):
            return evidence

        return {}

    @staticmethod
    def _find_evidence(
        evidence: dict[str, Any],
        keys: tuple[str, ...],
    ) -> dict[str, Any] | None:
        for key in keys:
            value = evidence.get(
                key
            )

            if isinstance(
                value,
                dict,
            ):
                return value

        return None

    # ==================================================================
    # Evidence answerers
    # ==================================================================

    def _answer_change_question(
        self,
        evidence: dict[str, Any],
        question: str,
    ) -> str | None:
        q = question.lower()

        changed_pixels = evidence.get(
            "changed_pixels"
        )

        change_percent = evidence.get(
            "change_percent"
        )

        regions = evidence.get(
            "regions"
        )

        if any(
            keyword in q
            for keyword in (
                "how much",
                "percentage",
                "percent",
                "%",
            )
        ):
            if change_percent is not None:
                return (
                    f"The validated change-detection result "
                    f"reports approximately {change_percent}% "
                    f"of the compared image area as changed."
                )

            return None

        if any(
            keyword in q
            for keyword in (
                "how many",
                "regions",
                "areas changed",
            )
        ):
            if isinstance(
                regions,
                list,
            ):
                return (
                    f"The change-detection evidence identifies "
                    f"{len(regions)} reported change region(s)."
                )

            if changed_pixels is not None:
                return (
                    f"The change-detection evidence reports "
                    f"{changed_pixels} changed pixels."
                )

            return None

        if any(
            keyword in q
            for keyword in (
                "area",
                "square meter",
                "km",
                "hectare",
            )
        ):
            physical_area = evidence.get(
                "change_area_m2"
            )

            if physical_area is not None:
                return (
                    f"The validated change analysis reports "
                    f"approximately {physical_area} square meters "
                    f"of changed area."
                )

            return (
                "The change evidence does not provide a validated "
                "physical area measurement."
            )

        return (
            "The upstream change-detection analysis reports "
            "measurable differences between the supplied observations."
        )

    def _answer_location_question(
        self,
        evidence: dict[str, Any],
        question: str,
    ) -> str | None:
        coordinates = evidence.get(
            "coordinates"
        )

        bounds = evidence.get(
            "bounds"
        )

        crs = evidence.get(
            "crs"
        )

        label = evidence.get(
            "location_label"
        )

        if label:
            return (
                f"The available geospatial evidence identifies "
                f"the location as {label}."
            )

        if coordinates:
            return (
                "The geospatial evidence provides coordinates "
                f"({coordinates})."
            )

        if bounds:
            return (
                "The available geospatial evidence provides "
                f"bounds: {bounds}."
            )

        if crs:
            return (
                f"The supplied imagery is associated with CRS "
                f"{crs}, but this alone does not establish the "
                "scene's geographic location."
            )

        return None

    def _answer_object_question(
        self,
        evidence: dict[str, Any],
        question: str,
    ) -> str | None:
        objects = evidence.get(
            "objects"
        )

        detections = evidence.get(
            "detections"
        )

        if isinstance(
            objects,
            list,
        ) and objects:
            labels = []

            for item in objects:
                if isinstance(
                    item,
                    dict,
                ):
                    label = item.get(
                        "label"
                    )

                    if label:
                        labels.append(
                            str(label)
                        )

                elif item:
                    labels.append(
                        str(item)
                    )

            if labels:
                unique_labels = list(
                    dict.fromkeys(
                        labels
                    )
                )

                return (
                    "The visual-grounding evidence identifies "
                    + ", ".join(
                        unique_labels
                    )
                    + "."
                )

        if isinstance(
            detections,
            list,
        ) and detections:
            labels = []

            for detection in detections:
                if not isinstance(
                    detection,
                    dict,
                ):
                    continue

                label = detection.get(
                    "label"
                )

                if label:
                    labels.append(
                        str(label)
                    )

            if labels:
                return (
                    "The available grounding evidence identifies "
                    + ", ".join(
                        dict.fromkeys(
                            labels
                        )
                    )
                    + "."
                )

        return None

    def _answer_metadata_question(
        self,
        evidence: dict[str, Any],
        question: str,
    ) -> str | None:
        q = question.lower()

        if "sensor" in q or "satellite" in q:
            sensor = (
                evidence.get(
                    "sensor"
                )
                or evidence.get(
                    "platform"
                )
            )

            if sensor:
                return (
                    f"The supplied imagery metadata identifies "
                    f"the sensor/platform as {sensor}."
                )

            return None

        if "resolution" in q or "pixel size" in q:
            resolution = (
                evidence.get(
                    "resolution_m"
                )
                or evidence.get(
                    "ground_resolution_m"
                )
            )

            if resolution is not None:
                return (
                    f"The supplied metadata reports a ground "
                    f"resolution of {resolution} meters per pixel."
                )

            return None

        if (
            "date" in q
            or "acquisition" in q
            or "capture" in q
        ):
            date = (
                evidence.get(
                    "acquisition_date"
                )
                or evidence.get(
                    "date"
                )
            )

            if date:
                return (
                    f"The supplied imagery metadata reports "
                    f"an acquisition date of {date}."
                )

            return None

        dimensions = evidence.get(
            "dimensions"
        )

        if dimensions:
            return (
                f"The supplied metadata reports image dimensions "
                f"of {dimensions}."
            )

        return None

    # ==================================================================
    # Confidence / result normalization
    # ==================================================================

    @staticmethod
    def _extract_confidence(
        evidence: dict[str, Any],
    ) -> float | None:
        for key in (
            "confidence",
            "score",
            "evidence_confidence",
        ):
            value = evidence.get(
                key
            )

            if value is not None:
                try:
                    return float(
                        value
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

        return None

    @staticmethod
    def _safe_confidence(
        value: Any,
        default: float = 0.55,
    ) -> float:
        try:
            parsed = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            parsed = default

        return round(
            max(
                0.0,
                min(
                    1.0,
                    parsed,
                ),
            ),
            3,
        )

    @staticmethod
    def _normalize_model_result(
        result: Any,
    ) -> dict[str, Any] | None:
        if result is None:
            return None

        if isinstance(
            result,
            str,
        ):
            return {
                "answer": result,
                "confidence": None,
                "provenance": (
                    "Configured VQA model."
                ),
            }

        if isinstance(
            result,
            dict,
        ):
            answer = (
                result.get(
                    "answer"
                )
                or result.get(
                    "text"
                )
                or result.get(
                    "response"
                )
            )

            if not answer:
                return None

            return {
                "answer": answer,
                "confidence": result.get(
                    "confidence"
                ),
                "provenance": result.get(
                    "provenance",
                    "Configured VQA model.",
                ),
            }

        answer = getattr(
            result,
            "answer",
            None,
        )

        if answer:
            return {
                "answer": answer,
                "confidence": getattr(
                    result,
                    "confidence",
                    None,
                ),
                "provenance": getattr(
                    result,
                    "provenance",
                    "Configured VQA model.",
                ),
            }

        return None

    # ==================================================================
    # Image loading
    # ==================================================================

    def _load_image(
        self,
        inputs: ModelInput,
    ) -> Image.Image | None:
        image_bytes = getattr(
            inputs,
            "image_bytes",
            None,
        )

        if image_bytes:
            for item in image_bytes:
                if not item:
                    continue

                try:
                    with Image.open(
                        io.BytesIO(item)
                    ) as image:
                        return image.convert(
                            "RGB"
                        )
                except Exception:
                    logger.warning(
                        "Unable to decode supplied image bytes.",
                        exc_info=True,
                    )

        image_paths = getattr(
            inputs,
            "image_paths",
            None,
        )

        if image_paths:
            for raw_path in image_paths:
                if not raw_path:
                    continue

                path = Path(
                    str(raw_path)
                )

                if not path.exists():
                    continue

                try:
                    with Image.open(
                        path
                    ) as image:
                        return image.convert(
                            "RGB"
                        )
                except Exception:
                    logger.warning(
                        "Unable to decode image path '%s'.",
                        path,
                        exc_info=True,
                    )

        return None

    # ==================================================================
    # Error result
    # ==================================================================

    def _error_output(
        self,
        message: str,
        start_time: float,
        *,
        question: str,
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
            raw={
                "question": question,
                "device": model_manager.device,
            },
        )


__all__ = [
    "RSVQAModel",
]