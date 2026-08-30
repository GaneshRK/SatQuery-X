"""Declarative model registry loader and invoker."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.registry.contracts import ModelInput, ModelOutput, ModelStatus


@dataclass
class RegistryEntry:
    id: str
    version: str
    task: str
    input_modes: list[str]
    status: str
    base_arch: str = ""
    training_data: list[str] = field(default_factory=list)
    hardware: str = "cpu"
    wrapper_path: str = ""
    depends_on: list[str] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path(__file__).parent / "models.yaml"
        self._entries: dict[str, RegistryEntry] = {}
        self._instances: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        with open(self.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for item in data.get("models", []):
            entry = RegistryEntry(
                id=item["id"],
                version=item.get("version", "v0.0"),
                task=item["task"],
                input_modes=item.get("input_modes", []),
                status=item.get("status", "baseline"),
                base_arch=item.get("base_arch", ""),
                training_data=item.get("training_data", []),
                hardware=item.get("hardware", "cpu"),
                wrapper_path=item.get("wrapper", ""),
                depends_on=item.get("depends_on", []),
                output=item.get("output", {}),
                metadata=item,
            )
            self._entries[entry.id] = entry

    def list_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())

    def list_models(self) -> list[dict[str, Any]]:
        result = []
        for entry in self._entries.values():
            health = self._safe_health(entry.id)
            result.append(
                {
                    "id": entry.id,
                    "version": entry.version,
                    "task": entry.task,
                    "input_modes": entry.input_modes,
                    "status": entry.status,
                    "base_arch": entry.base_arch,
                    "training_data": entry.training_data,
                    "hardware": entry.hardware,
                    "healthy": health,
                    "depends_on": entry.depends_on,
                    "output": entry.output,
                    "metadata": {
                        k: v
                        for k, v in entry.metadata.items()
                        if k not in {"wrapper"}
                    },
                }
            )
        return result

    def get(self, model_id: str) -> RegistryEntry:
        if model_id not in self._entries:
            raise KeyError(f"Unknown model: {model_id}")
        return self._entries[model_id]

    def _get_instance(self, model_id: str) -> Any:
        if model_id not in self._instances:
            entry = self.get(model_id)
            module_path, class_name = entry.wrapper_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            self._instances[model_id] = cls()
        return self._instances[model_id]

    def _safe_health(self, model_id: str) -> bool:
        try:
            instance = self._get_instance(model_id)
            return bool(instance.health())
        except Exception:
            return False

    def invoke(self, model_id: str, payload: ModelInput) -> ModelOutput:
        entry = self.get(model_id)
        if entry.status == ModelStatus.NOT_IMPLEMENTED.value:
            return ModelOutput(
                model_id=model_id,
                version=entry.version,
                task=entry.task,  # type: ignore[arg-type]
                status=ModelStatus.NOT_IMPLEMENTED,
                error=f"Model {model_id} is marked NOT_IMPLEMENTED in registry.",
            )
        instance = self._get_instance(model_id)
        return instance.infer(payload)

    def health(self, model_id: str) -> bool:
        return self._safe_health(model_id)


_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
