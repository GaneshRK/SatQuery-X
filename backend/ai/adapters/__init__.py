"""SatQuery-X AI Specialist Model Adapters per §37.

Exports standard adapters for the 6-layer architecture:
- GeoChatVQAAdapter: Remote-sensing conversational VQA & Captioning
- ChangeFormerAdapter: Bi-temporal pixel change detection & grounded change reasoning
- GroundingDINOAdapter: Text-guided visual grounding & spatial localization
- OpticalSARAdapter: Dual-encoder cross-modal optical and SAR fusion
- RemoteCLIPAdapter: Auxiliary semantic representation, retrieval & candidate scoring
- QwenSLMAdapter: Small Language Model query intent routing & structured planning
"""

from .base import (
    BaseModelAdapter,
    VQAAdapter,
    CaptionAdapter,
    GroundingAdapter,
    ChangeDetectionAdapter,
    ChangeVQAAdapter,
    OpticalSARFusionAdapter,
    RemoteCLIPAdapter as BaseRemoteCLIPAdapter,
    SLMPlannerAdapter,
)
from .geochat_adapter import GeoChatVQAAdapter
from .changeformer_adapter import ChangeFormerAdapter
from .grounding_adapter import GroundingDINOAdapter
from .optical_sar_adapter import OpticalSARAdapter
from .remoteclip_adapter import RemoteCLIPAdapter
from .qwen_adapter import QwenSLMAdapter

__all__ = [
    "BaseModelAdapter",
    "VQAAdapter",
    "CaptionAdapter",
    "GroundingAdapter",
    "ChangeDetectionAdapter",
    "ChangeVQAAdapter",
    "OpticalSARFusionAdapter",
    "BaseRemoteCLIPAdapter",
    "SLMPlannerAdapter",
    "GeoChatVQAAdapter",
    "ChangeFormerAdapter",
    "GroundingDINOAdapter",
    "OpticalSARAdapter",
    "RemoteCLIPAdapter",
    "QwenSLMAdapter",
]
