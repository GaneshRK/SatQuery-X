"""Unit tests for all 6 specialist model wrappers per §9."""

import pytest
from apps.agent.contracts import ModelInput
from apps.models_ai.change_detection.wrapper import ChangeDetectionModel
from apps.models_ai.change_vqa.wrapper import ChangeVQAModel
from apps.models_ai.optical_sar_fusion.wrapper import OpticalSARFusionModel
from apps.models_ai.rs_caption.wrapper import RSCaptionModel
from apps.models_ai.rs_grounding.wrapper import RSGroundingModel
from apps.models_ai.rs_vqa.wrapper import RSVQAModel


def test_rs_vqa_model(synthetic_optical_png):
    model = RSVQAModel()
    inputs = ModelInput(model_id="RS_VQA", image_bytes=[synthetic_optical_png], question="Is there vegetation?")
    out = model.predict(inputs)
    assert out.status == "ok"
    assert out.answer is not None
    assert out.confidence > 0.0
    assert out.raw.get("adaptation") == "baseline"


def test_rs_caption_model(synthetic_optical_png):
    model = RSCaptionModel()
    inputs = ModelInput(model_id="RS_CAPTION", image_bytes=[synthetic_optical_png])
    out = model.predict(inputs)
    assert out.status == "ok"
    assert out.caption is not None
    assert "remote-sensing" in out.caption.lower() or "vegetation" in out.caption.lower()


def test_rs_grounding_model(synthetic_optical_png):
    model = RSGroundingModel()
    inputs = ModelInput(model_id="RS_GROUNDING", image_bytes=[synthetic_optical_png], text_prompt="Highlight vegetation")
    out = model.predict(inputs)
    assert out.status == "ok"
    assert out.boxes is not None
    assert len(out.boxes) > 0


def test_change_detection_model(synthetic_optical_png):
    model = ChangeDetectionModel()
    inputs = ModelInput(model_id="CHANGE_DETECTION", image_bytes=[synthetic_optical_png, synthetic_optical_png])
    out = model.predict(inputs)
    assert out.status == "ok"
    assert out.change_mask is not None


def test_change_vqa_model(synthetic_optical_png):
    model = ChangeVQAModel()
    inputs = ModelInput(model_id="CHANGE_VQA", image_bytes=[synthetic_optical_png, synthetic_optical_png], question="Has the area changed?")
    out = model.predict(inputs)
    assert out.status == "ok"
    assert out.answer is not None


def test_optical_sar_fusion_model(synthetic_optical_png, synthetic_sar_png):
    model = OpticalSARFusionModel()
    inputs = ModelInput(model_id="OPTICAL_SAR_FUSION", image_bytes=[synthetic_optical_png, synthetic_sar_png])
    out = model.predict(inputs)
    assert out.status == "ok"
    assert "built-up" in out.answer.lower() or "optical-sar" in out.answer.lower()
