from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_settings_exists_and_disables_debug():
    text = (ROOT / "config/settings/prod.py").read_text()
    assert "DEBUG = False" in text
    assert "DJANGO_SECRET_KEY" in text
    assert '"*" in ALLOWED_HOSTS' in text


def test_base_settings_do_not_default_to_debug_or_wildcard_hosts():
    text = (ROOT / "config/settings/base.py").read_text()
    assert 'os.getenv("DJANGO_DEBUG", "False")' in text
    assert 'ALLOWED_HOSTS = [h.strip()' in text


def test_scoped_throttles_exist():
    text = (ROOT / "apps/system/throttles.py").read_text()
    for name in ["AnalysisRateThrottle", "SatelliteSearchRateThrottle", "SatelliteAcquisitionRateThrottle", "ImageryUploadRateThrottle"]:
        assert name in text
