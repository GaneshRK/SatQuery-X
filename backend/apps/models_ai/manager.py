"""Model Resource Manager (ModelManager) per §49, §50, §51.

Handles specialist model lifecycle:
- Hardware auto-detection (CUDA / MPS / CPU)
- Dynamic model loading and LRU unloading
- VRAM & memory monitoring
- Low-hardware development mode (SATQUERY_MODE=development)
- Transparent fallback disclosures (never fabricating model outputs)
"""

from __future__ import annotations

import gc
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class ModelManager:
    _instance: ModelManager | None = None

    def __new__(cls) -> ModelManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self.mode = os.getenv("SATQUERY_MODE", "development").lower()
        self.device = self._detect_device()
        self.dtype = self._detect_dtype()
        self._loaded_models: dict[str, Any] = {}
        self._last_accessed: dict[str, float] = {}
        self.max_cached_models = int(os.getenv("MAX_CACHED_MODELS", "4"))
        self._initialized = True
        logger.info(
            "ModelManager initialized: device=%s, dtype=%s, mode=%s",
            self.device,
            self.dtype,
            self.mode,
        )

    def _detect_device(self) -> str:
        env_device = os.getenv("MODEL_DEVICE", "auto").lower()
        if env_device != "auto":
            return env_device

        if HAS_TORCH and torch.cuda.is_available():
            return "cuda"
        if HAS_TORCH and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _detect_dtype(self) -> str:
        env_dtype = os.getenv("MODEL_DTYPE", "auto").lower()
        if env_dtype != "auto":
            return env_dtype

        if self.device == "cuda":
            return "float16"
        return "float32"

    def get_vram_info(self) -> dict[str, Any]:
        """Returns VRAM usage if running on CUDA."""
        if not HAS_TORCH or self.device != "cuda" or not torch.cuda.is_available():
            return {"available": False, "device": self.device}

        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            return {
                "available": True,
                "device": self.device,
                "free_gb": round(free_bytes / (1024 ** 3), 2),
                "total_gb": round(total_bytes / (1024 ** 3), 2),
                "used_gb": round((total_bytes - free_bytes) / (1024 ** 3), 2),
            }
        except Exception as e:
            return {"available": False, "device": self.device, "error": str(e)}

    def load_model(self, model_id: str, factory_fn: Any = None) -> Any:
        """Loads a model into cache, evicting oldest if capacity reached."""
        if model_id in self._loaded_models:
            self._last_accessed[model_id] = time.time()
            return self._loaded_models[model_id]

        if len(self._loaded_models) >= self.max_cached_models:
            self._evict_oldest()

        if factory_fn:
            logger.info("Instantiating specialist model '%s' on %s", model_id, self.device)
            model_instance = factory_fn()
            self._loaded_models[model_id] = model_instance
            self._last_accessed[model_id] = time.time()
            return model_instance

        return None

    def unload_model(self, model_id: str) -> bool:
        """Unloads a model from cache and releases memory/VRAM."""
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
            if model_id in self._last_accessed:
                del self._last_accessed[model_id]

            gc.collect()
            if HAS_TORCH and self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Model '%s' unloaded from memory", model_id)
            return True
        return False

    def _evict_oldest(self) -> None:
        """Evicts the least recently accessed model from memory."""
        if not self._last_accessed:
            return
        oldest_model_id = min(self._last_accessed, key=self._last_accessed.get)
        self.unload_model(oldest_model_id)

    def health_check(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "dtype": self.dtype,
            "mode": self.mode,
            "loaded_models": list(self._loaded_models.keys()),
            "cached_count": len(self._loaded_models),
            "max_cached": self.max_cached_models,
            "vram": self.get_vram_info(),
            "status": "healthy",
        }


# Singleton instance
model_manager = ModelManager()
