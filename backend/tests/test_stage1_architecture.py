"""Stage 1 architecture integrity checks."""

from pathlib import Path

import yaml

from apps.agent.registry import get_model_info, list_registered_model_ids


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REGISTRY = BACKEND_ROOT / "apps" / "agent" / "models.yaml"

EXPECTED_MODELS = {
    "RS_VQA",
    "RS_CAPTION",
    "RS_GROUNDING",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "OPTICAL_SAR_FUSION",
}


def test_single_canonical_registry_exists():
    assert CANONICAL_REGISTRY.is_file()
    assert not (BACKEND_ROOT / "registry" / "models.yaml").exists()


def test_registry_contains_expected_specialists():
    assert set(list_registered_model_ids()) == EXPECTED_MODELS


def test_registered_wrappers_point_to_canonical_model_package():
    with CANONICAL_REGISTRY.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    for model_id in EXPECTED_MODELS:
        wrapper = config[model_id]["wrapper"]
        assert wrapper.startswith("apps.models_ai.")

        module_name, class_name = wrapper.rsplit(".", 1)
        module_path = BACKEND_ROOT / Path(module_name.replace(".", "/") + ".py")
        assert module_path.is_file(), (model_id, wrapper)
        assert class_name


def test_no_legacy_model_manager_import_path():
    for path in [
        BACKEND_ROOT / "apps" / "models_ai" / "rs_vqa" / "wrapper.py",
        BACKEND_ROOT / "apps" / "satellite" / "tasks.py",
    ]:
        assert "apps.models_ai.manage" not in path.read_text(encoding="utf-8")


def test_model_info_is_available_for_every_specialist():
    for model_id in EXPECTED_MODELS:
        info = get_model_info(model_id)
        assert info is not None
        assert info["wrapper"].startswith("apps.models_ai.")
