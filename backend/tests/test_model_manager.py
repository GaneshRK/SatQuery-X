"""Unit tests for ModelManager (apps.models_ai.manager)."""

import pytest
from apps.models_ai.manager import ModelManager


def test_model_manager_singleton():
    m1 = ModelManager()
    m2 = ModelManager()
    assert m1 is m2


def test_model_manager_device_and_health():
    mgr = ModelManager()
    health = mgr.health_check()
    assert health["status"] == "healthy"
    assert health["device"] in ("cpu", "cuda", "mps")
    assert health["dtype"] in ("float32", "float16", "bfloat16")
    assert isinstance(health["loaded_models"], list)


def test_model_manager_lifecycle():
    mgr = ModelManager()
    mgr.max_cached_models = 2

    # Load dummy models
    m_a = mgr.load_model("dummy_a", factory_fn=lambda: {"name": "model_a"})
    assert m_a["name"] == "model_a"
    assert "dummy_a" in mgr._loaded_models

    m_b = mgr.load_model("dummy_b", factory_fn=lambda: {"name": "model_b"})
    assert "dummy_b" in mgr._loaded_models

    # Loading a 3rd model should evict the oldest
    m_c = mgr.load_model("dummy_c", factory_fn=lambda: {"name": "model_c"})
    assert "dummy_c" in mgr._loaded_models
    assert len(mgr._loaded_models) <= 2

    # Test explicit unload
    unloaded = mgr.unload_model("dummy_c")
    assert unloaded is True
    assert "dummy_c" not in mgr._loaded_models
