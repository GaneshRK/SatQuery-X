from pathlib import Path


def test_asset_ingestion_module_exists():
    path = Path("apps/satellite/services/asset_ingestion.py")
    assert path.exists()


def test_download_task_exists():
    source = Path("apps/satellite/tasks.py").read_text()
    assert "def download_satellite_asset_task" in source
    assert "download_scene_asset" in source
