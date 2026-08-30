"""Base model interface."""

from abc import ABC, abstractmethod
from typing import Any

from backend.registry.contracts import ModelInput, ModelOutput


class BaseModelWrapper(ABC):
    model_id: str = "BASE"
    version: str = "v0.0"

    @abstractmethod
    def infer(self, inputs: ModelInput) -> ModelOutput:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> bool:
        raise NotImplementedError

    def metadata(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "version": self.version}
