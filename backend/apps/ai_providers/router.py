from __future__ import annotations
import logging
from typing import Any
from .base import AIProvider, AIRequest, AIResponse
from .local_provider import LocalProvider
from .openai_provider import OpenAIProvider
from .hf_provider import HuggingFaceProvider

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Intelligent Model Router.
    Selects optimal AI/VLM/LLM provider based on task, modality, availability,
    and server configuration with seamless local baseline fallback.
    """

    def __init__(self):
        self.local_provider = LocalProvider()
        self.openai_provider = OpenAIProvider()
        self.hf_provider = HuggingFaceProvider()

    def route(self, request: AIRequest) -> AIResponse:
        task = request.task.upper()

        # 1. Complex Multimodal Reasoning / Planning / Synthesis
        if task in ("REASONING", "PLANNING", "EXPLANATION"):
            if self.openai_provider.is_configured():
                resp = self.openai_provider.generate(request)
                if resp.status == "ok":
                    return resp
            # Fallback to local deterministic reasoning
            return self.local_provider.generate(request)

        # 2. Remote Sensing Visual Question Answering (VQA) / Captioning
        if task in ("VQA", "CAPTION"):
            if self.openai_provider.is_configured() and request.image_paths:
                resp = self.openai_provider.generate(request)
                if resp.status == "ok":
                    return resp
            if self.hf_provider.is_configured():
                resp = self.hf_provider.generate(request)
                if resp.status == "ok":
                    return resp
            return self.local_provider.generate(request)

        # 3. Grounding / Segmentation / Detection
        # Defer to specialized local computer vision / baseline specialist
        return self.local_provider.generate(request)

    def health_check(self) -> dict[str, Any]:
        return {
            "local": self.local_provider.health_check(),
            "openai": self.openai_provider.health_check(),
            "huggingface": self.hf_provider.health_check(),
            "active_reasoning_provider": "openai" if self.openai_provider.is_configured() else "local",
        }
