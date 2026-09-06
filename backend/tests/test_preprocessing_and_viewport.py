import pytest
import numpy as np
from apps.agent.geocoding import resolve_location
from apps.agent.understander import understand_query
from apps.agent.validator import validate_agent_inputs
from apps.geospatial.preprocessing import (
    clean_satellite_imagery,
    detect_clouds,
    detect_cloud_shadows,
    reduce_haze_dos,
    apply_lee_filter,
)


@pytest.mark.django_db
def test_geocoding_resolves_map_viewport():
    session_context = {
        "current_viewport": {
            "bbox": [80.15, 12.95, 80.35, 13.15],
            "center": [80.25, 13.05],
            "zoom": 11,
        }
    }
    loc = resolve_location("What is changing here?", session_context)
    assert loc is not None
    assert loc["source"] == "map_viewport"
    assert loc["bbox"] == [80.15, 12.95, 80.35, 13.15]
    assert loc["coords"] == [80.25, 13.05]


@pytest.mark.django_db
def test_query_without_image_uses_viewport_and_avoids_ambiguity():
    session_context = {
        "current_viewport": {
            "bbox": [93.10, 26.50, 93.30, 26.70],
            "center": [93.20, 26.60],
            "zoom": 10,
        },
        "image_count": 0,
        "has_images": False,
    }
    intent = understand_query("What is changing here?", session_context)
    assert intent.clarification_required is False
    assert intent.intent in ("change_vqa", "change_detection")
    assert intent.location["source"] == "map_viewport"

    validation = validate_agent_inputs(intent, [], None)
    assert validation["valid"] is True
    assert validation["mode"] == "MODE_A_CHANGE"


@pytest.mark.django_db
def test_preprocessing_clean_optical_imagery():
    # Synthetic optical raster with a cloudy quadrant
    raster = np.full((4, 100, 100), 100, dtype=np.uint8)
    raster[:, 0:30, 0:30] = 250  # bright cloud

    cleaned, report = clean_satellite_imagery(raster, sensor="SENTINEL-2", modality="OPTICAL")
    assert report.cloud_cover_pct > 0.0
    assert report.usable_clear_data_pct < 100.0
    assert any("Cloud" in m for m in report.cleaning_methods_applied)


@pytest.mark.django_db
def test_preprocessing_clean_sar_imagery():
    # Synthetic SAR raster with speckle
    sar_raster = np.random.randint(50, 200, size=(1, 64, 64), dtype=np.uint8)

    cleaned, report = clean_satellite_imagery(sar_raster, sensor="SENTINEL-1", modality="SAR")
    assert report.sar_speckle_reduced is True
    assert report.cloud_cover_pct == 0.0
    assert any("Lee Speckle Filter" in m for m in report.cleaning_methods_applied)
