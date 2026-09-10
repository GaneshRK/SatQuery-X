from apps.agent.modality_router import resolve_analysis_route


def test_single_image_route():
    out = resolve_analysis_route([{"modality": "optical"}], "SINGLE_IMAGE")
    assert out["route"] == "SINGLE_IMAGE"
    assert out["specialist"] == "RS_VQA"


def test_optical_sar_route_uses_metadata_not_position():
    out = resolve_analysis_route([{"modality": "sar"}, {"modality": "optical"}], "CROSS_MODAL")
    assert out["route"] == "CROSS_MODAL_OPTICAL_SAR"
    assert out["indices"]["optical"] == [1]
    assert out["indices"]["sar"] == [0]


def test_unknown_modality_is_not_guessed():
    out = resolve_analysis_route([{}, {}], "BI_TEMPORAL")
    assert out["route"] == "MULTI_IMAGE_MODALITY_UNKNOWN"
    assert out["specialist"] is None


def test_four_image_temporal_cross_modal_route():
    out = resolve_analysis_route([
        {"modality": "optical", "acquisition_date": "2026-01-01"},
        {"modality": "sar", "acquisition_date": "2026-01-01"},
        {"modality": "optical", "acquisition_date": "2026-02-01"},
        {"modality": "sar", "acquisition_date": "2026-02-01"},
    ], "TEMPORAL_CROSS_MODAL")
    assert out["route"] == "BI_TEMPORAL_OPTICAL_SAR"
    assert out["specialist"] == "COMPOSED_TEMPORAL_MULTIMODAL"
