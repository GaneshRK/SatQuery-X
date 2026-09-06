"""Optical + SAR Dual-Encoder Cross-Modal Fusion Adapter per §16, §32, §37.

Implements true multimodal fusion exploiting complementary physics:
Optical (spectral reflectance) + SAR (radar backscatter & structure)
  ↓ Optical Preprocessing (reflectance norm) & SAR Preprocessing (speckle filter + log dB)
  ↓ Dual Encoders
  ↓ Cross-Modal Fusion → Joint Representation
  ↓ Target Identification (Water, Built-up, Vegetation)
"""

from __future__ import annotations

import io
import os
import time
from typing import Any

from PIL import Image

from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager
from apps.models_ai.optical_sar_fusion.wrapper import OpticalSARFusionModel
from .base import OpticalSARFusionAdapter as BaseOpticalSARAdapter


class OpticalSARAdapter(BaseOpticalSARAdapter):
    """
    Specialist adapter for true cross-modal optical and SAR feature fusion.
    """
    model_id = "OpticalSARFusion"
    version = "2.1-cross-modal"
    task = "cross_modal_fusion_analysis"
    gpu_requirement = "OPTIONAL"

    def __init__(self) -> None:
        super().__init__()
        self._fusion_backend = OpticalSARFusionModel()
        self.model_name = os.getenv("FUSION_MODEL_NAME", "DualBranch-OpticalSAR-Net")

    def fuse(
        self,
        optical_image: Any,
        sar_image: Any,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ModelOutput:
        """Executes dual-encoder optical and SAR fusion analysis."""
        start_t = time.perf_counter()
        img_opt = self._to_pil(optical_image)
        img_sar = self._to_pil(sar_image)

        if img_opt is None or img_sar is None:
            return ModelOutput(
                model_id=self.model_id,
                version=self.version,
                task=self.task,
                status="error",
                error="OpticalSARAdapter: Requires both one optical image and one SAR radar image.",
                latency_ms=int((time.perf_counter() - start_t) * 1000),
            )

        buf_opt, buf_sar = io.BytesIO(), io.BytesIO()
        img_opt.save(buf_opt, format="PNG")
        img_sar.save(buf_sar, format="PNG")

        inputs = ModelInput(
            model_id=self.model_id,
            image_bytes=[buf_opt.getvalue(), buf_sar.getvalue()],
            params=params or {},
        )

        out = self._fusion_backend.predict(inputs)
        out.model_id = self.model_id
        out.version = self.version
        if out.raw:
            out.raw["specialist_adapter"] = "OpticalSARAdapter"
            out.raw["fusion_architecture"] = self.model_name
        return out
