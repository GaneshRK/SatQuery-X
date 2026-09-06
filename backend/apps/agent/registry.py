"""Model registry managing specialist remote-sensing models per §8.6."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).resolve().parent / "models.yaml"

_REGISTRY_CACHE: dict[str, Any] | None = None
_INSTANCES_CACHE: dict[str, Any] = {}


def load_registry_config() -> dict[str, Any]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        if REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                _REGISTRY_CACHE = yaml.safe_load(f) or {}
        else:
            _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def list_models_info() -> list[dict[str, Any]]:
    cfg = load_registry_config()
    result = []
    for model_id, info in cfg.items():
        wrapper_path = info.get("wrapper")
        status = "NOT_CONFIGURED"
        backend_engine = "spectral_heuristics"
        try:
            if wrapper_path:
                mod_name, cls_name = wrapper_path.rsplit(".", 1)
                mod = importlib.import_module(mod_name)
                getattr(mod, cls_name)
                has_torch = importlib.util.find_spec("torch") is not None
                status = "READY_BASELINE" if has_torch else "READY_ALGORITHMIC"
                backend_engine = "pytorch_blip" if "blip" in str(info.get("base_model", "")) and has_torch else "numpy_rasterio_spectral"
        except Exception as e:
            status = "UNAVAILABLE"
            backend_engine = str(e)

        result.append({
            "id": model_id,
            "task": info.get("task", ""),
            "input_modes": info.get("input_modes", []),
            "version": info.get("version", "1.0-baseline"),
            "adaptation": info.get("adaptation", "baseline"),
            "base_model": info.get("base_model", ""),
            "status": status,
            "backend_engine": backend_engine,
        })
    return result


def get_model_wrapper(model_id: str) -> Any:
    global _INSTANCES_CACHE
    if model_id in _INSTANCES_CACHE:
        return _INSTANCES_CACHE[model_id]

    cfg = load_registry_config()
    model_info = cfg.get(model_id)
    if not model_info:
        raise ValueError(f"Model ID '{model_id}' not found in registry {REGISTRY_PATH}")

    wrapper_path = model_info.get("wrapper")
    if not wrapper_path:
        raise ValueError(f"No wrapper class defined for model '{model_id}'")

    module_name, class_name = wrapper_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    instance = cls()
    _INSTANCES_CACHE[model_id] = instance
    return instance
