"""
SatQuery-X Specialist Model Registry
=====================================

Central registry for specialist remote-sensing model wrappers.

Responsibilities
----------------
- Load model definitions from models.yaml.
- Dynamically import wrapper classes.
- Cache wrapper instances safely.
- Expose model metadata to the planner/executor.
- Distinguish registry availability from actual model readiness.
- Never claim a model is trained, loaded, or production-ready unless
  the wrapper/model itself confirms that state.
- Provide compatibility helpers for the master AgentExecutor.

Scientific integrity
--------------------
This registry does not create fallback models, synthetic predictions,
fake confidence values, or fabricated model capabilities.

A registered wrapper means only that the wrapper can be imported and
instantiated. Actual inference readiness is determined by the wrapper
and its configured model/runtime.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)


# ============================================================================
# Registry configuration
# ============================================================================

REGISTRY_PATH = (
    Path(__file__).resolve().parent / "models.yaml"
)

_REGISTRY_CACHE: dict[str, dict[str, Any]] | None = None

_INSTANCES_CACHE: dict[str, Any] = {}

_REGISTRY_LOCK = threading.RLock()


# ============================================================================
# Configuration loading
# ============================================================================


def load_registry_config(
    force_reload: bool = False,
) -> dict[str, dict[str, Any]]:
    """
    Load and validate models.yaml.

    The registry is cached after the first load.

    Parameters
    ----------
    force_reload:
        Reload models.yaml instead of using the cached configuration.

    Returns
    -------
    dict
        Mapping of model ID -> model configuration.

    Raises
    ------
    ValueError
        If the YAML root is not a mapping or contains malformed entries.
    """

    global _REGISTRY_CACHE

    with _REGISTRY_LOCK:

        if (
            _REGISTRY_CACHE is not None
            and not force_reload
        ):
            return _REGISTRY_CACHE

        if not REGISTRY_PATH.exists():
            logger.warning(
                "Model registry file does not exist: %s",
                REGISTRY_PATH,
            )

            _REGISTRY_CACHE = {}
            return _REGISTRY_CACHE

        try:

            with REGISTRY_PATH.open(
                "r",
                encoding="utf-8",
            ) as handle:

                loaded = (
                    yaml.safe_load(handle)
                    or {}
                )

        except Exception as exc:

            logger.exception(
                "Unable to load model registry: %s",
                REGISTRY_PATH,
            )

            raise ValueError(
                f"Unable to load model registry: {exc}"
            ) from exc

        if not isinstance(
            loaded,
            dict,
        ):
            raise ValueError(
                "models.yaml must contain a top-level mapping."
            )

        normalized: dict[
            str,
            dict[str, Any],
        ] = {}

        for raw_model_id, raw_info in loaded.items():

            model_id = str(
                raw_model_id
            ).strip()

            if not model_id:
                continue

            if not isinstance(
                raw_info,
                dict,
            ):
                raise ValueError(
                    f"Configuration for model '{model_id}' "
                    "must be a mapping."
                )

            info = dict(
                raw_info
            )

            # Normalize common optional fields so consumers can
            # safely inspect the registry.
            if not isinstance(
                info.get("input_modes"),
                list,
            ):
                info["input_modes"] = []

            if not isinstance(
                info.get("depends_on"),
                list,
            ):
                info["depends_on"] = []

            normalized[
                model_id
            ] = info

        _REGISTRY_CACHE = normalized

        return _REGISTRY_CACHE


# ============================================================================
# Cache management
# ============================================================================


def clear_registry_cache() -> None:
    """
    Clear both configuration and instantiated-wrapper caches.

    Useful after changing models.yaml or during application reloads/tests.
    """

    global _REGISTRY_CACHE

    with _REGISTRY_LOCK:

        _REGISTRY_CACHE = None

        _INSTANCES_CACHE.clear()


def clear_model_instance(
    model_id: str,
) -> None:
    """
    Remove one instantiated wrapper from the cache.
    """

    with _REGISTRY_LOCK:

        _INSTANCES_CACHE.pop(
            str(model_id),
            None,
        )


# ============================================================================
# Registry inspection
# ============================================================================


def get_model_info(
    model_id: str,
) -> dict[str, Any] | None:
    """
    Return the raw configuration for one registered model.

    Returns None when the model ID is not registered.
    """

    model_id = str(
        model_id
    ).strip()

    if not model_id:
        return None

    config = load_registry_config()

    info = config.get(
        model_id
    )

    if info is None:
        return None

    return dict(
        info
    )


def list_registered_model_ids() -> list[str]:
    """
    Return all registered model IDs.
    """

    return list(
        load_registry_config().keys()
    )


def is_model_registered(
    model_id: str,
) -> bool:
    """
    Return True only when the model ID exists in models.yaml.
    """

    return (
        get_model_info(model_id)
        is not None
    )


# ============================================================================
# Wrapper import
# ============================================================================


def _import_wrapper_class(
    model_id: str,
) -> type[Any]:
    """
    Import the wrapper class declared by models.yaml.
    """

    info = get_model_info(
        model_id
    )

    if info is None:
        raise ValueError(
            f"Model ID '{model_id}' is not found "
            f"in registry {REGISTRY_PATH}."
        )

    wrapper_path = str(
        info.get(
            "wrapper",
            ""
        )
        or ""
    ).strip()

    if not wrapper_path:
        raise ValueError(
            f"No wrapper class is configured for model "
            f"'{model_id}'."
        )

    if "." not in wrapper_path:
        raise ValueError(
            f"Invalid wrapper path for model '{model_id}': "
            f"'{wrapper_path}'."
        )

    module_name, class_name = (
        wrapper_path.rsplit(
            ".",
            1,
        )
    )

    try:

        module = importlib.import_module(
            module_name
        )

    except Exception as exc:

        logger.exception(
            "Unable to import wrapper module '%s' for model '%s'.",
            module_name,
            model_id,
        )

        raise ImportError(
            f"Unable to import wrapper '{wrapper_path}' "
            f"for model '{model_id}': {exc}"
        ) from exc

    try:

        wrapper_class = getattr(
            module,
            class_name,
        )

    except AttributeError as exc:

        raise ImportError(
            f"Wrapper class '{class_name}' was not found "
            f"in module '{module_name}'."
        ) from exc

    if not isinstance(
        wrapper_class,
        type,
    ):
        raise TypeError(
            f"Configured wrapper '{wrapper_path}' "
            "is not a class."
        )

    return wrapper_class


# ============================================================================
# Wrapper lifecycle
# ============================================================================


def get_model_wrapper(
    model_id: str,
) -> Any | None:
    """
    Return the cached specialist wrapper instance.

    Unlike the old implementation, this function does not manufacture
    a fallback model.

    Returns
    -------
    object | None
        Instantiated wrapper when available.

    Notes
    -----
    Unknown/unavailable models return None rather than silently selecting
    another model. This allows the master executor to distinguish an
    unavailable specialist from a successful inference.
    """

    model_id = str(
        model_id
    ).strip()

    if not model_id:
        return None

    with _REGISTRY_LOCK:

        cached = _INSTANCES_CACHE.get(
            model_id
        )

        if cached is not None:
            return cached

        info = get_model_info(
            model_id
        )

        if info is None:
            logger.warning(
                "Requested unregistered model: %s",
                model_id,
            )
            return None

        try:

            wrapper_class = (
                _import_wrapper_class(
                    model_id
                )
            )

            instance = wrapper_class()

        except Exception:

            logger.exception(
                "Unable to instantiate model wrapper '%s'.",
                model_id,
            )

            return None

        _INSTANCES_CACHE[
            model_id
        ] = instance

        return instance


# ============================================================================
# Wrapper readiness
# ============================================================================


def _wrapper_readiness(
    wrapper: Any,
) -> dict[str, Any]:
    """
    Inspect wrapper-provided readiness information when available.

    The registry never assumes that an imported wrapper means the actual
    model is loaded or configured.
    """

    if wrapper is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "wrapper_unavailable",
        }

    # Explicit readiness methods are preferred.
    for method_name in (
        "health_check",
        "readiness",
        "get_readiness",
    ):

        method = getattr(
            wrapper,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:

            result = method()

            if isinstance(
                result,
                dict,
            ):

                normalized = dict(
                    result
                )

                normalized.setdefault(
                    "status",
                    "UNKNOWN",
                )

                return normalized

            if isinstance(
                result,
                bool,
            ):

                return {
                    "status": (
                        "READY"
                        if result
                        else "NOT_READY"
                    )
                }

        except Exception as exc:

            logger.debug(
                "Wrapper readiness check failed.",
                exc_info=True,
            )

            return {
                "status": "NOT_READY",
                "reason": (
                    "wrapper_readiness_check_failed"
                ),
            }

    # Some wrappers expose a model/model_id/configuration attribute.
    # Do not infer readiness from these alone.
    return {
        "status": "UNKNOWN",
    }


# ============================================================================
# Model metadata
# ============================================================================


def get_model_status(
    model_id: str,
) -> dict[str, Any]:
    """
    Return operational metadata for one registered model.

    Status meanings
    ---------------
    REGISTERED
        Entry exists in models.yaml.

    WRAPPER_READY
        Wrapper imported and instantiated successfully.

    READY
        Wrapper explicitly reports readiness.

    NOT_READY
        Wrapper explicitly reports that it is not ready.

    UNKNOWN
        Wrapper exists but does not expose a readiness contract.

    UNAVAILABLE
        Registry entry or wrapper could not be loaded.
    """

    model_id = str(
        model_id
    ).strip()

    info = get_model_info(
        model_id
    )

    if info is None:

        return {
            "id": model_id,
            "status": "UNAVAILABLE",
            "registered": False,
            "wrapper_available": False,
        }

    wrapper = get_model_wrapper(
        model_id
    )

    if wrapper is None:

        return {
            "id": model_id,
            "status": "UNAVAILABLE",
            "registered": True,
            "wrapper_available": False,
            "task": info.get(
                "task",
                "",
            ),
            "input_modes": info.get(
                "input_modes",
                [],
            ),
            "depends_on": info.get(
                "depends_on",
                [],
            ),
            "version": info.get(
                "version"
            ),
            "adaptation": info.get(
                "adaptation"
            ),
            "base_model": info.get(
                "base_model"
            ),
        }

    readiness = _wrapper_readiness(
        wrapper
    )

    readiness_status = str(
        readiness.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    if readiness_status in {
        "READY",
        "HEALTHY",
        "OK",
    }:
        status = "READY"

    elif readiness_status in {
        "NOT_READY",
        "UNAVAILABLE",
        "FAILED",
    }:
        status = "NOT_READY"

    else:
        status = "WRAPPER_READY"

    return {
        "id": model_id,
        "status": status,
        "registered": True,
        "wrapper_available": True,
        "task": info.get(
            "task",
            "",
        ),
        "input_modes": info.get(
            "input_modes",
            [],
        ),
        "depends_on": info.get(
            "depends_on",
            [],
        ),
        "version": info.get(
            "version"
        ),
        "adaptation": info.get(
            "adaptation"
        ),
        "base_model": info.get(
            "base_model"
        ),
        "wrapper": info.get(
            "wrapper"
        ),
        "readiness": readiness,
    }


def list_models_info() -> list[dict[str, Any]]:
    """
    Return operational metadata for every registered specialist.

    No artificial "baseline", "PyTorch ready", or "spectral heuristic"
    status is generated here. The registry reports only what it can
    actually establish.
    """

    result = []

    for model_id in list_registered_model_ids():

        try:

            result.append(
                get_model_status(
                    model_id
                )
            )

        except Exception as exc:

            logger.exception(
                "Unable to inspect registered model '%s'.",
                model_id,
            )

            info = get_model_info(
                model_id
            ) or {}

            result.append(
                {
                    "id": model_id,
                    "status": "UNAVAILABLE",
                    "registered": True,
                    "wrapper_available": False,
                    "task": info.get(
                        "task",
                        "",
                    ),
                    "input_modes": info.get(
                        "input_modes",
                        [],
                    ),
                    "depends_on": info.get(
                        "depends_on",
                        [],
                    ),
                    "version": info.get(
                        "version"
                    ),
                    "adaptation": info.get(
                        "adaptation"
                    ),
                    "base_model": info.get(
                        "base_model"
                    ),
                    "error": str(
                        exc
                    ),
                }
            )

    return result


# ============================================================================
# Dependency validation
# ============================================================================


def validate_model_dependencies(
    model_id: str,
) -> dict[str, Any]:
    """
    Validate that declared registry dependencies exist.

    This does not execute the dependencies.
    """

    info = get_model_info(
        model_id
    )

    if info is None:

        return {
            "valid": False,
            "model_id": model_id,
            "reason": "model_not_registered",
        }

    dependencies = info.get(
        "depends_on",
        [],
    )

    missing = [
        dependency
        for dependency in dependencies
        if not is_model_registered(
            dependency
        )
    ]

    return {
        "valid": not missing,
        "model_id": model_id,
        "dependencies": list(
            dependencies
        ),
        "missing_dependencies": missing,
    }


# ============================================================================
# Model capability helpers
# ============================================================================


def model_supports_input_mode(
    model_id: str,
    input_mode: str,
) -> bool:
    """
    Check whether a registered model declares support for an input mode.
    """

    info = get_model_info(
        model_id
    )

    if info is None:
        return False

    modes = info.get(
        "input_modes",
        [],
    )

    return str(
        input_mode
    ) in {
        str(mode)
        for mode in modes
    }


def get_models_for_task(
    task: str,
) -> list[dict[str, Any]]:
    """
    Return registered models declaring a matching task.
    """

    task = str(
        task
    ).strip()

    if not task:
        return []

    result = []

    for model in list_models_info():

        if str(
            model.get(
                "task",
                "",
            )
        ) == task:

            result.append(
                model
            )

    return result


# ============================================================================
# Compatibility helpers
# ============================================================================


def reload_registry() -> list[dict[str, Any]]:
    """
    Reload models.yaml and return the current model information.
    """

    clear_registry_cache()

    load_registry_config(
        force_reload=True
    )

    return list_models_info()


__all__ = [
    "REGISTRY_PATH",
    "load_registry_config",
    "clear_registry_cache",
    "clear_model_instance",
    "get_model_info",
    "list_registered_model_ids",
    "is_model_registered",
    "get_model_wrapper",
    "get_model_status",
    "list_models_info",
    "validate_model_dependencies",
    "model_supports_input_mode",
    "get_models_for_task",
    "reload_registry",
]