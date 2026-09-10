"""
CHANGE_VQA specialist model wrapper.

Grounded question answering over bi-temporal change-detection evidence.

Pipeline
--------
T1 + T2
  ↓
Existing CHANGE_DETECTION evidence
  ↓
Question understanding
  ↓
Evidence extraction
  ↓
Question-specific reasoning
  ↓
Grounded answer

Important
---------
This module is a reasoning layer, NOT a second change detector.

It must not:
- invent change percentages;
- invent physical area;
- assume Sentinel-2 resolution;
- independently create a hardcoded difference mask;
- claim that generic pixel differences are buildings, flooding,
  deforestation, construction, etc.;
- fabricate geographic coordinates.

Semantic questions are answered only when the supplied evidence contains
appropriate semantic evidence. Otherwise the answer explicitly states that
the available change evidence is insufficient for that interpretation.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager

logger = logging.getLogger(__name__)


class ChangeVQAModel:
    """
    Grounded VQA/reasoning layer for change detection.

    Expected upstream evidence
    ---------------------------
    The preferred input is a structured CHANGE_DETECTION output supplied
    through ModelInput.params.

    Supported evidence keys include:

        change_detection
        change_result
        previous_result
        evidence
        change_percent
        change_pixels
        total_pixels
        area_m2
        area_ha
        area_km2
        regions
        components
        boxes
        geojson

    The wrapper also accepts ModelOutput-like dictionaries/objects when
    provided through params.
    """

    model_id = "CHANGE_VQA"
    version = "4.0-supervised-ready"
    task = "change_based_vqa"

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
                "Change VQA failed."
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
    # Main reasoning
    # ------------------------------------------------------------------

    def _predict_internal(
        self,
        inputs: ModelInput,
        start_time: float,
    ) -> ModelOutput:
        question = self._get_question(
            inputs
        )

        # Prefer the native two-image fusion model when configured. It encodes
        # T1 and T2 independently and fuses them with the question; it does not
        # concatenate the timestamps into one visual canvas.
        native_output = self._try_native_temporal_model(inputs, question, start_time)
        if native_output is not None:
            return native_output

        # Legacy supervised BLIP path remains available as a compatibility
        # option. It uses the documented temporal canvas representation.
        neural_output = self._try_configured_model(inputs, question, start_time)
        if neural_output is not None:
            return neural_output

        evidence = self._extract_evidence(
            inputs
        )

        if evidence is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error=(
                    "CHANGE_VQA requires structured change-detection "
                    "evidence. Run CHANGE_DETECTION first and provide "
                    "its result to the VQA layer."
                ),
                latency_ms=int(
                    (
                        time.perf_counter()
                        - start_time
                    )
                    * 1000
                ),
            )

        validation_error = (
            self._validate_evidence(
                evidence
            )
        )

        if validation_error:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error=validation_error,
                latency_ms=int(
                    (
                        time.perf_counter()
                        - start_time
                    )
                    * 1000
                ),
            )

        normalized = self._normalize_evidence(
            evidence
        )

        answer, answer_type, reasoning = (
            self._answer_question(
                question,
                normalized,
            )
        )

        latency = int(
            (
                time.perf_counter()
                - start_time
            )
            * 1000
        )

        confidence = self._calculate_confidence(
            normalized,
            answer_type,
        )

        raw = {
            "adaptation": "grounded",
            "base_model": "structured-change-evidence-reasoner",
            "model_version": self.version,
            "question": question,
            "answer_type": answer_type,
            "reasoning_basis": reasoning,
            "evidence_source": normalized[
                "evidence_source"
            ],
            "change_state": normalized[
                "change_state"
            ],
            "change_percent": normalized[
                "change_percent"
            ],
            "change_pixels": normalized[
                "change_pixels"
            ],
            "total_pixels": normalized[
                "total_pixels"
            ],
            "area_available": normalized[
                "area_available"
            ],
            "area_m2": normalized[
                "area_m2"
            ],
            "area_ha": normalized[
                "area_ha"
            ],
            "area_km2": normalized[
                "area_km2"
            ],
            "regions_count": normalized[
                "regions_count"
            ],
            "semantic_evidence_available": normalized[
                "semantic_evidence_available"
            ],
            "geospatial_evidence_available": normalized[
                "geospatial_evidence_available"
            ],
        }

        if normalized.get(
            "source_crs"
        ):
            raw["source_crs"] = normalized[
                "source_crs"
            ]

        if normalized.get(
            "geojson"
        ):
            raw["geojson_available"] = True

        return ModelOutput(
            model_id=self.model_id,
            version=self.version,
            task=self.task,
            answer=answer,
            confidence=confidence,
            latency_ms=latency,
            status="ok",
            raw=raw,
        )


    def _try_native_temporal_model(self, inputs: ModelInput, question: str, start_time: float) -> ModelOutput | None:
        checkpoint = os.getenv("CHANGE_VQA_NATIVE_CHECKPOINT", "").strip()
        if not checkpoint:
            return None
        images = getattr(inputs, "image_paths", []) or []
        image_bytes = getattr(inputs, "image_bytes", []) or []
        if len(images) < 2 and len(image_bytes) < 2:
            return None
        try:
            import torch
            from ml.native_multimodal.model import NativeTemporalMultimodalVQA, question_ids
            device = model_manager.device
            ck = torch.load(checkpoint, map_location=device, weights_only=False)
            answers = ck.get("id_to_answer") or {int(k): v for k, v in ck["id_to_answer"].items()}
            model = NativeTemporalMultimodalVQA(len(answers), question_buckets=int(ck.get("question_buckets", 4096))).to(device)
            model.load_state_dict(ck["state_dict"]); model.eval()

            from PIL import Image
            import io, numpy as np
            def load(v):
                im = Image.open(io.BytesIO(v)) if isinstance(v, (bytes, bytearray)) else Image.open(Path(v))
                im = im.convert("RGB").resize((256,256), Image.Resampling.BILINEAR)
                x = torch.from_numpy(np.asarray(im)).permute(2,0,1).float()/255.0
                return (x-torch.tensor([.5,.5,.5]).view(3,1,1))/torch.tensor([.5,.5,.5]).view(3,1,1)
            t1 = image_bytes[0] if len(image_bytes) >= 2 else images[0]
            t2 = image_bytes[1] if len(image_bytes) >= 2 else images[1]
            q = torch.tensor([question_ids(question)], dtype=torch.long, device=device)
            with torch.inference_mode():
                logits = model(load(t1).unsqueeze(0).to(device), load(t2).unsqueeze(0).to(device), q)
                probs = torch.softmax(logits, dim=-1)
                score, pred = probs.max(dim=-1)
            answer = answers[int(pred.item())]
            model_manager.mark_prediction(checkpoint, success=True)
            return ModelOutput(model_id=self.model_id, version="5.0-native-temporal", task=self.task, answer=answer,
                confidence=float(score.item()), status="ok", latency_ms=int((time.perf_counter()-start_time)*1000),
                raw={"adaptation":"native_temporal_multimodal_classifier","base_model":"NativeTemporalMultimodalVQA","checkpoint":checkpoint,
                     "confidence_type":"uncalibrated_softmax","question":question,"closed_vocabulary":True})
        except Exception as exc:
            logger.exception("Configured native temporal Change VQA checkpoint failed")
            try: model_manager.mark_prediction(checkpoint, success=False, error=str(exc))
            except Exception: pass
            return None

    def _try_configured_model(self, inputs: ModelInput, question: str, start_time: float) -> ModelOutput | None:
        checkpoint = os.getenv("CHANGE_VQA_CHECKPOINT", "").strip()
        if not checkpoint:
            return None
        images = getattr(inputs, "image_paths", []) or []
        image_bytes = getattr(inputs, "image_bytes", []) or []
        if len(images) < 2 and len(image_bytes) < 2:
            return None
        model_id = checkpoint
        try:
            def factory():
                from apps.models_ai.change_vqa.hf_model import HuggingFaceChangeVQA
                return HuggingFaceChangeVQA(model_id, device=model_manager.device)
            model = model_manager.load_model(model_id, factory_fn=factory)
            if model is None:
                return None
            t1 = image_bytes[0] if len(image_bytes) >= 2 else images[0]
            t2 = image_bytes[1] if len(image_bytes) >= 2 else images[1]
            result = model.answer(t1, t2, question)
            answer = str(result.get("answer", "")).strip()
            if not answer:
                model_manager.mark_prediction(model_id, success=False, error="Change VQA model returned no answer")
                return None
            model_manager.mark_prediction(model_id, success=True)
            return ModelOutput(model_id=self.model_id, version="4.0-supervised", task=self.task, answer=answer,
                confidence=result.get("confidence"), status="ok", latency_ms=int((time.perf_counter()-start_time)*1000),
                raw={"adaptation":"supervised_bitemporal_vqa","base_model":"BLIP VQA + LoRA","checkpoint":checkpoint,
                     "provenance":result.get("provenance", {}), "question":question})
        except Exception as exc:
            logger.exception("Configured Change VQA checkpoint failed")
            try:
                model_manager.mark_prediction(model_id, success=False, error=str(exc))
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _get_question(
        self,
        inputs: ModelInput,
    ) -> str:
        question = getattr(
            inputs,
            "question",
            None,
        )

        if not question:
            return (
                "What changed between these two dates?"
            )

        return str(
            question
        ).strip()

    def _extract_evidence(
        self,
        inputs: ModelInput,
    ) -> dict[str, Any] | None:
        """
        Locate structured CHANGE_DETECTION evidence.

        No image-difference fallback is performed here.

        This is deliberate: VQA must not become an accidental second
        change-detection implementation.
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
            return None

        candidate_keys = (
            "change_detection",
            "change_result",
            "previous_result",
            "evidence",
            "analysis_result",
            "change_evidence",
        )

        for key in candidate_keys:
            candidate = params.get(
                key
            )

            normalized = (
                self._coerce_evidence_object(
                    candidate
                )
            )

            if normalized is not None:
                return normalized

        # Allow a directly supplied evidence dictionary.
        direct_keys = (
            "change_percent",
            "change_pixels",
            "total_pixels",
            "regions",
            "components",
            "change_state",
        )

        if any(
            key in params
            for key in direct_keys
        ):
            return dict(params)

        return None

    def _coerce_evidence_object(
        self,
        value: Any,
    ) -> dict[str, Any] | None:
        if value is None:
            return None

        if isinstance(
            value,
            dict,
        ):
            return dict(value)

        # ModelOutput may expose .raw.
        raw = getattr(
            value,
            "raw",
            None,
        )

        if isinstance(
            raw,
            dict,
        ):
            return dict(raw)

        # Some orchestrators may serialize ModelOutput.
        try:
            if hasattr(
                value,
                "model_dump",
            ):
                dumped = value.model_dump()

                if isinstance(
                    dumped,
                    dict,
                ):
                    if isinstance(
                        dumped.get("raw"),
                        dict,
                    ):
                        return dict(
                            dumped["raw"]
                        )

                    return dumped
        except Exception:
            pass

        try:
            if hasattr(
                value,
                "dict",
            ):
                dumped = value.dict()

                if isinstance(
                    dumped,
                    dict,
                ):
                    if isinstance(
                        dumped.get("raw"),
                        dict,
                    ):
                        return dict(
                            dumped["raw"]
                        )

                    return dumped
        except Exception:
            pass

        # JSON string support.
        if isinstance(
            value,
            str,
        ):
            try:
                parsed = json.loads(
                    value
                )

                if isinstance(
                    parsed,
                    dict,
                ):
                    return parsed

            except Exception:
                return None

        return None

    # ------------------------------------------------------------------
    # Evidence validation
    # ------------------------------------------------------------------

    def _validate_evidence(
        self,
        evidence: dict[str, Any],
    ) -> str | None:
        """
        Validate that the evidence contains measured information.

        The VQA layer does not accept an image pair alone as sufficient
        evidence because that would encourage duplicated/independent
        measurements.
        """
        has_change_measurement = any(
            key in evidence
            for key in (
                "change_percent",
                "change_pixels",
                "total_pixels",
                "change_state",
                "change_detected",
            )
        )

        if not has_change_measurement:
            return (
                "The supplied change-detection result does not contain "
                "measured change evidence."
            )

        return None

    # ------------------------------------------------------------------
    # Evidence normalization
    # ------------------------------------------------------------------

    def _normalize_evidence(
        self,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        change_pixels = self._number_or_none(
            evidence.get(
                "change_pixels"
            )
        )

        total_pixels = self._number_or_none(
            evidence.get(
                "total_pixels"
            )
        )

        change_percent = self._number_or_none(
            evidence.get(
                "change_percent"
            )
        )

        if (
            change_percent is None
            and change_pixels is not None
            and total_pixels is not None
            and total_pixels > 0
        ):
            change_percent = (
                change_pixels
                / total_pixels
                * 100.0
            )

        area_m2 = self._number_or_none(
            evidence.get(
                "area_m2"
            )
        )

        area_ha = self._number_or_none(
            evidence.get(
                "area_ha"
            )
        )

        area_km2 = self._number_or_none(
            evidence.get(
                "area_km2"
            )
        )

        # Convert only when the upstream result already supplies a physical
        # measurement. This is unit conversion, not a fabricated measurement.
        if (
            area_ha is None
            and area_m2 is not None
        ):
            area_ha = (
                area_m2
                / 10000.0
            )

        if (
            area_km2 is None
            and area_m2 is not None
        ):
            area_km2 = (
                area_m2
                / 1_000_000.0
            )

        regions = evidence.get(
            "regions"
        )

        if regions is None:
            regions = evidence.get(
                "components"
            )

        if not isinstance(
            regions,
            list,
        ):
            regions = []

        change_state = (
            evidence.get(
                "change_state"
            )
        )

        if not change_state:
            detected = evidence.get(
                "change_detected"
            )

            if detected is True:
                change_state = (
                    "change_detected"
                )
            elif detected is False:
                change_state = (
                    "no_detected_change"
                )
            elif (
                change_pixels is not None
                and change_pixels > 0
            ):
                change_state = (
                    "change_detected"
                )
            else:
                change_state = (
                    "unknown"
                )

        source_crs = evidence.get(
            "source_crs"
        )

        geojson = evidence.get(
            "geojson"
        )

        geospatial_available = bool(
            evidence.get(
                "geospatial_reference_available",
                False,
            )
            or geojson is not None
            or source_crs is not None
        )

        semantic_evidence = self._extract_semantic_evidence(
            evidence
        )

        return {
            "evidence_source": (
                evidence.get(
                    "base_model"
                )
                or evidence.get(
                    "model_id"
                )
                or "CHANGE_DETECTION"
            ),
            "change_state": str(
                change_state
            ),
            "change_percent": (
                self._round_or_none(
                    change_percent,
                    4,
                )
            ),
            "change_pixels": (
                int(change_pixels)
                if change_pixels is not None
                else None
            ),
            "total_pixels": (
                int(total_pixels)
                if total_pixels is not None
                else None
            ),
            "area_available": bool(
                evidence.get(
                    "area_available",
                    area_m2 is not None,
                )
                and area_m2 is not None
            ),
            "area_m2": (
                self._round_or_none(
                    area_m2,
                    4,
                )
            ),
            "area_ha": (
                self._round_or_none(
                    area_ha,
                    6,
                )
            ),
            "area_km2": (
                self._round_or_none(
                    area_km2,
                    8,
                )
            ),
            "regions": regions,
            "regions_count": len(
                regions
            ),
            "source_crs": (
                str(source_crs)
                if source_crs
                else None
            ),
            "geojson": geojson,
            "geospatial_evidence_available": (
                geospatial_available
            ),
            "semantic_evidence_available": bool(
                semantic_evidence
            ),
            "semantic_evidence": semantic_evidence,
        }

    # ------------------------------------------------------------------
    # Question classification
    # ------------------------------------------------------------------

    def _classify_question(
        self,
        question: str,
    ) -> str:
        q = question.lower().strip()

        if any(
            phrase in q
            for phrase in (
                "how much area",
                "what area",
                "how large",
                "how big",
                "area changed",
                "changed area",
                "area of change",
                "size of change",
                "hectare",
                "hectares",
                "km2",
                "km²",
                "square meter",
                "square metre",
            )
        ):
            return "area"

        if any(
            phrase in q
            for phrase in (
                "what changed",
                "changes occurred",
                "change occurred",
                "difference",
                "different",
                "changed between",
                "changed from",
                "change between",
            )
        ):
            return "summary"

        if any(
            phrase in q
            for phrase in (
                "where",
                "which region",
                "which area",
                "location",
                "located",
                "concentrated",
                "which part",
                "north",
                "south",
                "east",
                "west",
            )
        ):
            return "location"

        if any(
            phrase in q
            for phrase in (
                "building",
                "buildings",
                "built-up",
                "built up",
                "urban",
                "construction",
                "road",
                "roads",
                "infrastructure",
            )
        ):
            return "built_environment"

        if any(
            phrase in q
            for phrase in (
                "water",
                "flood",
                "flooding",
                "river",
                "lake",
                "reservoir",
                "wetland",
            )
        ):
            return "water"

        if any(
            phrase in q
            for phrase in (
                "vegetation",
                "forest",
                "tree",
                "trees",
                "deforestation",
                "deforest",
                "green cover",
                "crop",
                "crops",
            )
        ):
            return "vegetation"

        if any(
            phrase in q
            for phrase in (
                "why",
                "cause",
                "reason",
                "what caused",
            )
        ):
            return "cause"

        if any(
            phrase in q
            for phrase in (
                "when",
                "date",
                "time",
                "before",
                "after",
            )
        ):
            return "temporal"

        return "summary"

    # ------------------------------------------------------------------
    # Answer generation
    # ------------------------------------------------------------------

    def _answer_question(
        self,
        question: str,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        question_type = (
            self._classify_question(
                question
            )
        )

        if question_type == "area":
            return self._answer_area(
                evidence
            )

        if question_type == "location":
            return self._answer_location(
                evidence
            )

        if question_type == "built_environment":
            return self._answer_semantic(
                evidence,
                "built_environment",
            )

        if question_type == "water":
            return self._answer_semantic(
                evidence,
                "water",
            )

        if question_type == "vegetation":
            return self._answer_semantic(
                evidence,
                "vegetation",
            )

        if question_type == "cause":
            return self._answer_cause(
                evidence
            )

        if question_type == "temporal":
            return self._answer_temporal(
                evidence
            )

        return self._answer_summary(
            evidence
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _answer_summary(
        self,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        state = evidence[
            "change_state"
        ]

        change_percent = evidence[
            "change_percent"
        ]

        regions_count = evidence[
            "regions_count"
        ]

        if state == "no_detected_change":
            answer = (
                "No meaningful spatial change was detected "
                "by the supplied change-detection analysis."
            )

            if change_percent is not None:
                answer += (
                    f" The measured changed-pixel proportion "
                    f"was {change_percent:.2f}%."
                )

            return (
                answer,
                "no_change_summary",
                "Used the upstream change state and measured pixel proportion.",
            )

        if state == (
            "change_below_component_filter"
        ):
            answer = (
                "Pixel-level differences were detected, but the "
                "upstream analysis did not identify a significant "
                "change cluster after its component-size filtering."
            )

            if change_percent is not None:
                answer += (
                    f" The measured changed-pixel proportion "
                    f"was {change_percent:.2f}%."
                )

            return (
                answer,
                "filtered_change_summary",
                "Used the upstream change state and measured change proportion.",
            )

        if state == "change_detected":
            if change_percent is not None:
                answer = (
                    f"The change-detection analysis found spatial "
                    f"differences across approximately "
                    f"{change_percent:.2f}% of the analyzed pixels."
                )
            else:
                answer = (
                    "The change-detection analysis found "
                    "spatial differences between the two observations."
                )

            if regions_count > 0:
                answer += (
                    f" It identified {regions_count} "
                    f"significant change region(s)."
                )

            if evidence[
                "area_available"
            ]:
                answer += (
                    " The physical area is available from "
                    "the upstream geospatial measurement."
                )
            else:
                answer += (
                    " Physical area is not available from "
                    "the supplied evidence."
                )

            return (
                answer,
                "change_summary",
                "Used only measured change pixels, upstream regions, and area metadata.",
            )

        answer = (
            "The supplied evidence indicates spatial differences, "
            "but the change state is not sufficiently resolved "
            "to provide a stronger interpretation."
        )

        return (
            answer,
            "uncertain_summary",
            "Evidence did not provide a definitive change state.",
        )

    # ------------------------------------------------------------------
    # Area
    # ------------------------------------------------------------------

    def _answer_area(
        self,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        if not evidence[
            "area_available"
        ]:
            change_percent = evidence[
                "change_percent"
            ]

            if change_percent is not None:
                answer = (
                    f"The analysis measured approximately "
                    f"{change_percent:.2f}% changed pixels, "
                    "but a physical area cannot be reported because "
                    "the supplied evidence does not contain valid "
                    "ground-resolution information."
                )
            else:
                answer = (
                    "A physical changed area cannot be reported "
                    "because the supplied change-detection evidence "
                    "does not contain sufficient ground-resolution metadata."
                )

            return (
                answer,
                "area_unavailable",
                "Physical area was not present in the upstream evidence.",
            )

        area_m2 = evidence[
            "area_m2"
        ]
        area_ha = evidence[
            "area_ha"
        ]
        area_km2 = evidence[
            "area_km2"
        ]

        parts: list[str] = []

        if area_m2 is not None:
            parts.append(
                f"{area_m2:.2f} m²"
            )

        if area_ha is not None:
            parts.append(
                f"{area_ha:.4f} hectares"
            )

        if area_km2 is not None:
            parts.append(
                f"{area_km2:.6f} km²"
            )

        if not parts:
            return (
                "The upstream analysis indicates that physical area "
                "is available, but no usable area value was supplied.",
                "area_incomplete",
                "Area availability was reported but no numeric area field was present.",
            )

        answer = (
            "The measured changed area is "
            + " / ".join(parts)
            + "."
        )

        return (
            answer,
            "area_measurement",
            "Reported the physical area directly from upstream change-detection evidence.",
        )

    # ------------------------------------------------------------------
    # Location
    # ------------------------------------------------------------------

    def _answer_location(
        self,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        regions = evidence[
            "regions"
        ]

        if not regions:
            return (
                "The supplied change-detection result does not "
                "contain enough spatial-region evidence to identify "
                "where the detected changes are concentrated.",
                "location_unavailable",
                "No connected-component or region geometry was supplied.",
            )

        if evidence[
            "geospatial_evidence_available"
        ]:
            if evidence.get(
                "geojson"
            ):
                return (
                    "The detected change regions have geospatial "
                    "geometry available in the supplied evidence. "
                    "Their exact map locations should be taken from "
                    "the associated GeoJSON/map artifact.",
                    "geospatial_location",
                    "Used upstream geospatial change-region geometry.",
                )

            return (
                "The detected change regions have geospatial "
                "reference metadata available. Their exact map "
                "locations should be read from the corresponding "
                "change-region geometries.",
                "geospatial_location",
                "Used upstream CRS/geospatial metadata and region evidence.",
            )

        # Pixel-space location is still useful, but must be explicitly
        # described as image coordinates.
        first = regions[0]

        bbox = first.get(
            "bbox"
        )

        if bbox and len(bbox) >= 4:
            answer = (
                "The largest reported change region is located "
                f"around image coordinates "
                f"x={bbox[0]:.0f}–{bbox[2]:.0f}, "
                f"y={bbox[1]:.0f}–{bbox[3]:.0f}. "
                "These are image/pixel coordinates, not geographic "
                "coordinates."
            )

            return (
                answer,
                "pixel_location",
                "Used the largest upstream change-component bounding box.",
            )

        return (
            f"The analysis identified {len(regions)} change region(s), "
            "but the supplied evidence does not contain enough "
            "geometry to describe their location.",
            "location_incomplete",
            "Regions were present without usable bounding geometry.",
        )

    # ------------------------------------------------------------------
    # Semantic questions
    # ------------------------------------------------------------------

    def _answer_semantic(
        self,
        evidence: dict[str, Any],
        category: str,
    ) -> tuple[str, str, str]:
        semantic = evidence.get(
            "semantic_evidence"
        )

        if not semantic:
            category_name = {
                "built_environment": (
                    "buildings, roads, construction, or built-up land"
                ),
                "water": (
                    "water bodies or flooding"
                ),
                "vegetation": (
                    "vegetation, forest, crops, or deforestation"
                ),
            }.get(
                category,
                "that semantic category",
            )

            return (
                "The available change-detection result measures "
                "spatial differences, but it does not contain a "
                f"dedicated semantic classification for {category_name}. "
                "Therefore I cannot reliably attribute the detected "
                "change to that category from this evidence alone.",
                "semantic_evidence_insufficient",
                "Generic change evidence cannot establish a semantic land-cover cause.",
            )

        category_evidence = semantic.get(
            category
        )

        if not category_evidence:
            return (
                "The supplied semantic evidence does not contain "
                f"a confirmed result for the requested category.",
                "semantic_category_unavailable",
                "Semantic evidence exists, but not for the requested class.",
            )

        if isinstance(
            category_evidence,
            dict,
        ):
            detected = category_evidence.get(
                "detected"
            )

            confidence = self._number_or_none(
                category_evidence.get(
                    "confidence"
                )
            )

            area = self._number_or_none(
                category_evidence.get(
                    "area_m2"
                )
            )

            if detected is True:
                answer = (
                    f"The supplied semantic analysis reports "
                    f"{category.replace('_', ' ')} in the changed region(s)."
                )

                if confidence is not None:
                    answer += (
                        f" Its reported model confidence is "
                        f"{confidence:.3f}."
                    )

                if area is not None:
                    answer += (
                        f" The associated measured area is "
                        f"{area:.2f} m²."
                    )

                return (
                    answer,
                    "semantic_result",
                    "Used dedicated semantic evidence supplied by the upstream pipeline.",
                )

            if detected is False:
                return (
                    f"The supplied semantic analysis did not detect "
                    f"{category.replace('_', ' ')} in the changed region(s).",
                    "semantic_negative",
                    "Used the dedicated semantic model's negative result.",
                )

        return (
            f"The supplied semantic evidence contains information "
            f"about {category.replace('_', ' ')}, but it is not "
            "structured strongly enough to support a definitive answer.",
            "semantic_uncertain",
            "Semantic evidence was present but not definitive.",
        )

    # ------------------------------------------------------------------
    # Cause questions
    # ------------------------------------------------------------------

    def _answer_cause(
        self,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        semantic = evidence.get(
            "semantic_evidence"
        )

        if isinstance(
            semantic,
            dict,
        ):
            cause = semantic.get(
                "cause"
            )

            if isinstance(
                cause,
                dict,
            ):
                label = cause.get(
                    "label"
                )

                confidence = self._number_or_none(
                    cause.get(
                        "confidence"
                    )
                )

                if label:
                    answer = (
                        "The supplied semantic analysis identifies "
                        f"the likely change category as {label}."
                    )

                    if confidence is not None:
                        answer += (
                            f" Reported confidence: "
                            f"{confidence:.3f}."
                        )

                    return (
                        answer,
                        "cause_from_semantic_evidence",
                        "Used dedicated semantic/cause evidence supplied upstream.",
                    )

        return (
            "The change-detection evidence establishes that spatial "
            "differences occurred, but it does not establish why they "
            "occurred. Determining the cause requires additional "
            "semantic, temporal, spectral, or contextual evidence.",
            "cause_unavailable",
            "Generic change evidence cannot establish causal attribution.",
        )

    # ------------------------------------------------------------------
    # Temporal questions
    # ------------------------------------------------------------------

    def _answer_temporal(
        self,
        evidence: dict[str, Any],
    ) -> tuple[str, str, str]:
        t1_date = evidence.get(
            "t1_date"
        )

        t2_date = evidence.get(
            "t2_date"
        )

        if t1_date and t2_date:
            return (
                f"The supplied observations compare {t1_date} "
                f"with {t2_date}. The detected change represents "
                "differences between those two acquisition states.",
                "temporal_comparison",
                "Used acquisition dates supplied by the upstream evidence.",
            )

        return (
            "The change result represents differences between the "
            "two supplied observations, but acquisition dates were "
            "not included in the evidence provided to this VQA layer.",
            "temporal_metadata_unavailable",
            "No T1/T2 acquisition dates were supplied.",
        )

    # ------------------------------------------------------------------
    # Semantic evidence extraction
    # ------------------------------------------------------------------

    def _extract_semantic_evidence(
        self,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Look for evidence generated by dedicated semantic models.

        This deliberately does not infer semantics from RGB differences.
        """
        candidates = (
            evidence.get(
                "semantic_evidence"
            ),
            evidence.get(
                "semantic_results"
            ),
            evidence.get(
                "classification"
            ),
            evidence.get(
                "classifications"
            ),
        )

        for candidate in candidates:
            if isinstance(
                candidate,
                dict,
            ):
                return candidate

        return {}

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        evidence: dict[str, Any],
        answer_type: str,
    ) -> float:
        """
        Confidence represents evidence availability/quality, not truth
        probability of a semantic claim.
        """
        if answer_type in (
            "area_measurement",
        ):
            if evidence[
                "area_available"
            ]:
                return 0.95

            return 0.45

        if answer_type in (
            "semantic_evidence_insufficient",
            "cause_unavailable",
            "location_unavailable",
            "location_incomplete",
            "temporal_metadata_unavailable",
        ):
            return 0.85

        base = 0.70

        if evidence[
            "change_percent"
        ] is not None:
            base += 0.08

        if evidence[
            "regions_count"
        ] > 0:
            base += 0.08

        if evidence[
            "area_available"
        ]:
            base += 0.05

        if evidence[
            "geospatial_evidence_available"
        ]:
            base += 0.04

        return round(
            min(
                0.97,
                base,
            ),
            3,
        )

    # ------------------------------------------------------------------
    # Numeric helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _number_or_none(
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
    def _round_or_none(
        value: float | None,
        digits: int,
    ) -> float | None:
        if value is None:
            return None

        return round(
            value,
            digits,
        )


__all__ = [
    "ChangeVQAModel",
]