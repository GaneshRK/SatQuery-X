"""
SatQuery-X AI Model Resource Manager.

Responsibilities
----------------
- Detect available compute hardware.
- Maintain specialist-model lifecycle.
- Lazily instantiate models.
- Cache loaded specialists.
- Evict least-recently-used models when necessary.
- Track model usage and failures.
- Expose health/resource information to the orchestrator.
- Support development mode on low-resource machines.
- Never fabricate a model or silently claim that a model is loaded.

This file is NOT Django's project-level manage.py.

It is the model lifecycle manager located at:

    backend/apps/models_ai/manage.py
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Optional PyTorch
# ----------------------------------------------------------------------

try:
    import torch

    HAS_TORCH = True

except ImportError:
    torch = None
    HAS_TORCH = False


# ----------------------------------------------------------------------
# Model metadata
# ----------------------------------------------------------------------


@dataclass
class ModelRecord:
    """
    Runtime information for one specialist model.
    """

    model_id: str

    factory: Callable[[], Any] | None = None

    instance: Any | None = None

    loaded: bool = False

    load_count: int = 0

    prediction_count: int = 0

    failure_count: int = 0

    last_loaded_at: float | None = None

    last_accessed_at: float | None = None

    last_error: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ----------------------------------------------------------------------
# Model manager
# ----------------------------------------------------------------------


class ModelManager:
    """
    Central lifecycle manager for SatQuery-X specialist models.

    The manager is intentionally independent of Django request handling.

    Specialist wrappers can use:

        model_manager.device

        model_manager.dtype

        model_manager.load_model(...)

        model_manager.unload_model(...)

        model_manager.register_model(...)

        model_manager.health_check()

    The orchestrator can therefore treat specialist models as managed
    resources instead of directly constructing them everywhere.
    """

    _instance: ModelManager | None = None

    _singleton_lock = threading.Lock()

    def __new__(
        cls,
    ) -> ModelManager:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(
                        cls
                    )

                    cls._instance._initialized = False

        return cls._instance

    def __init__(
        self,
    ) -> None:
        if getattr(
            self,
            "_initialized",
            False,
        ):
            return

        self._lock = threading.RLock()

        # --------------------------------------------------------------
        # Runtime mode
        # --------------------------------------------------------------

        self.mode = (
            os.getenv(
                "SATQUERY_MODE",
                "development",
            )
            .strip()
            .lower()
        )

        if self.mode not in {
            "development",
            "production",
            "testing",
        }:
            logger.warning(
                "Unknown SATQUERY_MODE=%s. "
                "Using development mode.",
                self.mode,
            )

            self.mode = "development"

        # --------------------------------------------------------------
        # Hardware
        # --------------------------------------------------------------

        self.device = (
            self._detect_device()
        )

        self.dtype = (
            self._detect_dtype()
        )

        # --------------------------------------------------------------
        # Cache configuration
        # --------------------------------------------------------------

        self.max_cached_models = (
            self._read_positive_int(
                "MAX_CACHED_MODELS",
                default=4,
            )
        )

        # Development environments generally benefit from a smaller
        # cache unless explicitly configured.
        if (
            self.mode == "development"
            and "MAX_CACHED_MODELS"
            not in os.environ
        ):
            self.max_cached_models = 2

        # --------------------------------------------------------------
        # Model registry/cache
        # --------------------------------------------------------------

        self._registry: dict[
            str,
            ModelRecord,
        ] = {}

        self._loaded_models: dict[
            str,
            Any,
        ] = {}

        self._last_accessed: dict[
            str,
            float,
        ] = {}

        self._initialized = True

        logger.info(
            "SatQuery-X ModelManager initialized: "
            "mode=%s device=%s dtype=%s max_cached_models=%s",
            self.mode,
            self.device,
            self.dtype,
            self.max_cached_models,
        )

    # ==================================================================
    # Hardware detection
    # ==================================================================

    def _detect_device(
        self,
    ) -> str:
        """
        Detect compute device.

        Priority:
            MODEL_DEVICE
            CUDA
            Apple MPS
            CPU
        """

        requested = (
            os.getenv(
                "MODEL_DEVICE",
                "auto",
            )
            .strip()
            .lower()
        )

        allowed = {
            "auto",
            "cpu",
            "cuda",
            "mps",
        }

        if requested not in allowed:
            logger.warning(
                "Unsupported MODEL_DEVICE=%s. "
                "Falling back to auto detection.",
                requested,
            )

            requested = "auto"

        if requested == "cpu":
            return "cpu"

        if requested == "cuda":
            if (
                HAS_TORCH
                and torch is not None
                and torch.cuda.is_available()
            ):
                return "cuda"

            logger.warning(
                "MODEL_DEVICE=cuda was requested, "
                "but CUDA is unavailable. "
                "Falling back to CPU."
            )

            return "cpu"

        if requested == "mps":
            if (
                HAS_TORCH
                and torch is not None
                and hasattr(
                    torch.backends,
                    "mps",
                )
                and torch.backends.mps.is_available()
            ):
                return "mps"

            logger.warning(
                "MODEL_DEVICE=mps was requested, "
                "but MPS is unavailable. "
                "Falling back to CPU."
            )

            return "cpu"

        # --------------------------------------------------------------
        # Automatic detection
        # --------------------------------------------------------------

        if (
            HAS_TORCH
            and torch is not None
            and torch.cuda.is_available()
        ):
            return "cuda"

        if (
            HAS_TORCH
            and torch is not None
            and hasattr(
                torch.backends,
                "mps",
            )
            and torch.backends.mps.is_available()
        ):
            return "mps"

        return "cpu"

    def _detect_dtype(
        self,
    ) -> str:
        """
        Select numerical precision.

        This is metadata used by model implementations. The manager does
        not forcibly convert arbitrary specialist models.
        """

        requested = (
            os.getenv(
                "MODEL_DTYPE",
                "auto",
            )
            .strip()
            .lower()
        )

        allowed = {
            "auto",
            "float16",
            "float32",
            "bfloat16",
        }

        if requested not in allowed:
            logger.warning(
                "Unsupported MODEL_DTYPE=%s. "
                "Falling back to auto.",
                requested,
            )

            requested = "auto"

        if requested != "auto":
            return requested

        if self.device == "cuda":
            return "float16"

        if self.device == "mps":
            return "float32"

        return "float32"

    # ==================================================================
    # Registry
    # ==================================================================

    def register_model(
        self,
        model_id: str,
        factory_fn: Callable[[], Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRecord:
        """
        Register a specialist model factory.

        Registration is lazy.

        The factory is NOT executed here.
        """

        normalized_id = self._normalize_model_id(
            model_id
        )

        if not callable(
            factory_fn
        ):
            raise TypeError(
                "factory_fn must be callable."
            )

        with self._lock:
            existing = self._registry.get(
                normalized_id
            )

            if existing is not None:
                # Preserve a currently loaded instance while updating
                # registration metadata/factory.
                existing.factory = factory_fn

                if metadata:
                    existing.metadata.update(
                        metadata
                    )

                return existing

            record = ModelRecord(
                model_id=normalized_id,
                factory=factory_fn,
                metadata=dict(
                    metadata or {}
                ),
            )

            self._registry[
                normalized_id
            ] = record

            logger.info(
                "Registered specialist model: %s",
                normalized_id,
            )

            return record

    def unregister_model(
        self,
        model_id: str,
    ) -> bool:
        """
        Remove a model from the registry.

        Loaded instances are unloaded first.
        """

        normalized_id = self._normalize_model_id(
            model_id
        )

        with self._lock:
            self.unload_model(
                normalized_id
            )

            return (
                self._registry.pop(
                    normalized_id,
                    None,
                )
                is not None
            )

    def is_registered(
        self,
        model_id: str,
    ) -> bool:
        normalized_id = (
            self._normalize_model_id(
                model_id
            )
        )

        with self._lock:
            return (
                normalized_id
                in self._registry
            )

    def registered_models(
        self,
    ) -> list[str]:
        with self._lock:
            return sorted(
                self._registry.keys()
            )

    # ==================================================================
    # Loading
    # ==================================================================

    def load_model(
        self,
        model_id: str,
        factory_fn: Callable[[], Any] | None = None,
    ) -> Any | None:
        """
        Lazily load a specialist model.

        Behavior
        --------
        1. Return cached instance when already loaded.
        2. Register supplied factory when necessary.
        3. Evict least-recently-used model if cache is full.
        4. Instantiate the real factory.
        5. Store runtime metadata.

        Important
        ---------
        If no factory is registered/supplied, this method returns None.

        It never creates a fake model.
        """

        normalized_id = (
            self._normalize_model_id(
                model_id
            )
        )

        with self._lock:
            now = time.time()

            # ----------------------------------------------------------
            # Already loaded
            # ----------------------------------------------------------

            if normalized_id in (
                self._loaded_models
            ):
                self._last_accessed[
                    normalized_id
                ] = now

                record = self._registry.get(
                    normalized_id
                )

                if record:
                    record.last_accessed_at = now

                return self._loaded_models[
                    normalized_id
                ]

            # ----------------------------------------------------------
            # Register an on-demand factory
            # ----------------------------------------------------------

            record = self._registry.get(
                normalized_id
            )

            if (
                record is None
                and factory_fn is not None
            ):
                record = self.register_model(
                    normalized_id,
                    factory_fn,
                )

            elif (
                record is not None
                and factory_fn is not None
            ):
                record.factory = factory_fn

            # ----------------------------------------------------------
            # No known implementation
            # ----------------------------------------------------------

            if record is None:
                logger.warning(
                    "Specialist model '%s' is not registered.",
                    normalized_id,
                )

                return None

            if record.factory is None:
                logger.warning(
                    "Specialist model '%s' has no factory.",
                    normalized_id,
                )

                return None

            # ----------------------------------------------------------
            # Cache eviction
            # ----------------------------------------------------------

            self._ensure_cache_capacity(
                normalized_id
            )

            # ----------------------------------------------------------
            # Actual model construction
            # ----------------------------------------------------------

            try:
                logger.info(
                    "Loading specialist model '%s' on %s.",
                    normalized_id,
                    self.device,
                )

                instance = record.factory()

                if instance is None:
                    raise RuntimeError(
                        f"Factory for '{normalized_id}' "
                        "returned None."
                    )

                now = time.time()

                record.instance = instance
                record.loaded = True
                record.load_count += 1
                record.last_loaded_at = now
                record.last_accessed_at = now
                record.last_error = None

                self._loaded_models[
                    normalized_id
                ] = instance

                self._last_accessed[
                    normalized_id
                ] = now

                logger.info(
                    "Specialist model '%s' loaded successfully.",
                    normalized_id,
                )

                return instance

            except Exception as exc:
                record.failure_count += 1
                record.last_error = str(
                    exc
                )

                logger.exception(
                    "Failed to load specialist model '%s'.",
                    normalized_id,
                )

                return None

    # ==================================================================
    # Prediction lifecycle
    # ==================================================================

    def mark_prediction(
        self,
        model_id: str,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """
        Update runtime statistics after a specialist invocation.
        """

        normalized_id = (
            self._normalize_model_id(
                model_id
            )
        )

        with self._lock:
            record = self._registry.get(
                normalized_id
            )

            if record is None:
                return

            record.prediction_count += 1

            record.last_accessed_at = (
                time.time()
            )

            self._last_accessed[
                normalized_id
            ] = record.last_accessed_at

            if not success:
                record.failure_count += 1

                if error:
                    record.last_error = str(
                        error
                    )

    # ==================================================================
    # Unloading
    # ==================================================================

    def unload_model(
        self,
        model_id: str,
    ) -> bool:
        """
        Unload a specialist model from memory.
        """

        normalized_id = (
            self._normalize_model_id(
                model_id
            )
        )

        with self._lock:
            instance = self._loaded_models.pop(
                normalized_id,
                None,
            )

            self._last_accessed.pop(
                normalized_id,
                None,
            )

            record = self._registry.get(
                normalized_id
            )

            if record is not None:
                record.instance = None
                record.loaded = False
                record.last_accessed_at = None

            if instance is None:
                return False

            # Explicitly release local references.
            del instance

            self._release_memory()

            logger.info(
                "Specialist model '%s' unloaded.",
                normalized_id,
            )

            return True

    def unload_all(
        self,
    ) -> int:
        """
        Unload every currently cached model.
        """

        with self._lock:
            model_ids = list(
                self._loaded_models.keys()
            )

            unloaded = 0

            for model_id in model_ids:
                if self.unload_model(
                    model_id
                ):
                    unloaded += 1

            self._release_memory()

            return unloaded

    # ==================================================================
    # LRU cache
    # ==================================================================

    def _ensure_cache_capacity(
        self,
        requested_model_id: str,
    ) -> None:
        """
        Evict least-recently-used models until another model can fit.
        """

        while (
            len(
                self._loaded_models
            )
            >= self.max_cached_models
            and requested_model_id
            not in self._loaded_models
        ):
            if not self._last_accessed:
                break

            oldest_model_id = min(
                self._last_accessed,
                key=self._last_accessed.get,
            )

            logger.info(
                "LRU eviction: '%s'.",
                oldest_model_id,
            )

            self.unload_model(
                oldest_model_id
            )

    def _evict_oldest(
        self,
    ) -> str | None:
        """
        Backwards-compatible helper.

        Returns the evicted model ID.
        """

        with self._lock:
            if not self._last_accessed:
                return None

            oldest_model_id = min(
                self._last_accessed,
                key=self._last_accessed.get,
            )

            if self.unload_model(
                oldest_model_id
            ):
                return oldest_model_id

            return None

    # ==================================================================
    # Hardware/resource monitoring
    # ==================================================================

    def get_vram_info(
        self,
    ) -> dict[str, Any]:
        """
        Return CUDA VRAM information when available.
        """

        if not (
            HAS_TORCH
            and torch is not None
            and self.device == "cuda"
            and torch.cuda.is_available()
        ):
            return {
                "available": False,
                "device": self.device,
            }

        try:
            free_bytes, total_bytes = (
                torch.cuda.mem_get_info()
            )

            used_bytes = (
                total_bytes
                - free_bytes
            )

            return {
                "available": True,
                "device": "cuda",
                "free_gb": round(
                    free_bytes
                    / (
                        1024**3
                    ),
                    3,
                ),
                "total_gb": round(
                    total_bytes
                    / (
                        1024**3
                    ),
                    3,
                ),
                "used_gb": round(
                    used_bytes
                    / (
                        1024**3
                    ),
                    3,
                ),
            }

        except Exception as exc:
            return {
                "available": False,
                "device": self.device,
                "error": str(
                    exc
                ),
            }

    def get_memory_info(
        self,
    ) -> dict[str, Any]:
        """
        Return process memory information when psutil is available.

        psutil is optional and therefore does not become a hard
        dependency of the model manager.
        """

        try:
            import psutil

            process = psutil.Process()

            memory = (
                process.memory_info()
            )

            return {
                "available": True,
                "rss_gb": round(
                    memory.rss
                    / (
                        1024**3
                    ),
                    3,
                ),
                "vms_gb": round(
                    memory.vms
                    / (
                        1024**3
                    ),
                    3,
                ),
            }

        except ImportError:
            return {
                "available": False,
                "reason": (
                    "psutil is not installed."
                ),
            }

        except Exception as exc:
            return {
                "available": False,
                "error": str(
                    exc
                ),
            }

    # ==================================================================
    # Health
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return an auditable manager health snapshot.
        """

        with self._lock:
            loaded = []

            for model_id, record in (
                self._registry.items()
            ):
                if record.loaded:
                    loaded.append(
                        {
                            "model_id": model_id,
                            "loaded": True,
                            "load_count": record.load_count,
                            "prediction_count": (
                                record.prediction_count
                            ),
                            "failure_count": (
                                record.failure_count
                            ),
                            "last_error": (
                                record.last_error
                            ),
                            "metadata": dict(
                                record.metadata
                            ),
                        }
                    )

            return {
                "device": self.device,
                "dtype": self.dtype,
                "mode": self.mode,
                "registered_models": len(
                    self._registry
                ),
                "loaded_models": [
                    item["model_id"]
                    for item in loaded
                ],
                "cached_count": len(
                    self._loaded_models
                ),
                "max_cached": (
                    self.max_cached_models
                ),
                "vram": self.get_vram_info(),
                "memory": self.get_memory_info(),
                "status": "healthy",
            }

    def model_status(
        self,
        model_id: str,
    ) -> dict[str, Any]:
        """
        Return status for a specific specialist.
        """

        normalized_id = (
            self._normalize_model_id(
                model_id
            )
        )

        with self._lock:
            record = self._registry.get(
                normalized_id
            )

            if record is None:
                return {
                    "model_id": normalized_id,
                    "registered": False,
                    "loaded": False,
                }

            return {
                "model_id": normalized_id,
                "registered": True,
                "loaded": record.loaded,
                "load_count": record.load_count,
                "prediction_count": (
                    record.prediction_count
                ),
                "failure_count": (
                    record.failure_count
                ),
                "last_loaded_at": (
                    record.last_loaded_at
                ),
                "last_accessed_at": (
                    record.last_accessed_at
                ),
                "last_error": (
                    record.last_error
                ),
                "metadata": dict(
                    record.metadata
                ),
            }

    # ==================================================================
    # Memory cleanup
    # ==================================================================

    def _release_memory(
        self,
    ) -> None:
        """
        Release Python/GPU cache where supported.
        """

        try:
            gc.collect()
        except Exception:
            pass

        if (
            HAS_TORCH
            and torch is not None
            and self.device == "cuda"
            and torch.cuda.is_available()
        ):
            try:
                torch.cuda.empty_cache()
            except Exception:
                logger.exception(
                    "Unable to release CUDA cache."
                )

    # ==================================================================
    # Configuration helpers
    # ==================================================================

    @staticmethod
    def _read_positive_int(
        environment_name: str,
        default: int,
    ) -> int:
        value = os.getenv(
            environment_name
        )

        if value is None:
            return default

        try:
            parsed = int(
                value
            )

            if parsed <= 0:
                raise ValueError

            return parsed

        except (
            TypeError,
            ValueError,
        ):
            logger.warning(
                "%s=%r is invalid. Using %s.",
                environment_name,
                value,
                default,
            )

            return default

    @staticmethod
    def _normalize_model_id(
        model_id: str,
    ) -> str:
        if model_id is None:
            raise ValueError(
                "model_id cannot be None."
            )

        normalized = str(
            model_id
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "model_id cannot be empty."
            )

        return normalized


# ----------------------------------------------------------------------
# Singleton instance
# ----------------------------------------------------------------------

model_manager = ModelManager()


__all__ = [
    "ModelManager",
    "ModelRecord",
    "model_manager",
]