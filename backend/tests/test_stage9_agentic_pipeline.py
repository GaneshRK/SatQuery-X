"""Static Stage 9 integrity checks that do not require a live Django database."""
from pathlib import Path


def test_stage9_files_exist():
    assert Path("apps/agent/tool_registry.py").exists()
    assert Path("apps/agent/planner.py").exists()
    assert Path("apps/agent/executor.py").exists()
    assert Path("docs/STAGE_9_AGENTIC_SATELLITE_PIPELINE.md").exists()


def test_agentic_acquisition_contract_is_present():
    registry = Path("apps/agent/tool_registry.py").read_text(encoding="utf-8")
    planner = Path("apps/agent/planner.py").read_text(encoding="utf-8")
    executor = Path("apps/agent/executor.py").read_text(encoding="utf-8")
    assert 'name="acquire_satellite_imagery"' in registry
    assert '"acquire_satellite_imagery"' in planner
    assert 'tool_name == "acquire_satellite_imagery"' in executor


def test_no_synthetic_acquisition_fallback():
    registry = Path("apps/agent/tool_registry.py").read_text(encoding="utf-8")
    assert "synthetic" not in registry[registry.index("def _handle_acquire_satellite"):registry.index("# ===========================================================================\n# Change detection")].lower()
