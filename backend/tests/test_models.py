"""Unit tests for all 6 specialist model wrappers."""

from backend.models.change_detection.wrapper import ChangeDetectionModel
from backend.models.change_vqa.wrapper import ChangeVQAModel
from backend.models.optical_sar_fusion.wrapper import OpticalSARFusionModel
from backend.models.rs_caption.wrapper import RSCaptionModel
from backend.models.rs_grounding.wrapper import RSGroundingModel
from backend.models.rs_vqa.wrapper import RSVQAModel
from backend.registry.contracts import ModelInput, ModelStatus, TaskType


def test_rs_vqa_model(synthetic_optical_png):
    model = RSVQAModel()
    assert model.health() is True

    inputs = ModelInput(
        model_id="RS_VQA",
        image_bytes=[synthetic_optical_png],
        question="What is the dominant feature?",
    )
    output = model.infer(inputs)
    assert output.model_id == "RS_VQA"
    assert output.task == TaskType.VISUAL_QUESTION_ANSWERING
    assert output.answer is not None
    assert output.confidence > 0.0
    assert output.latency_ms > 0.0


def test_rs_caption_model(synthetic_optical_png):
    model = RSCaptionModel()
    assert model.health() is True

    inputs = ModelInput(model_id="RS_CAPTION", image_bytes=[synthetic_optical_png])
    output = model.infer(inputs)
    assert output.model_id == "RS_CAPTION"
    assert output.task == TaskType.IMAGE_CAPTIONING
    assert output.caption is not None
    assert output.confidence > 0.0


def test_rs_grounding_model(synthetic_optical_png):
    model = RSGroundingModel()
    assert model.health() is True

    inputs = ModelInput(
        model_id="RS_GROUNDING",
        image_bytes=[synthetic_optical_png],
        text_prompt="locate vegetation",
    )
    output = model.infer(inputs)
    assert output.model_id == "RS_GROUNDING"
    assert output.task == TaskType.TEXT_GUIDED_GROUNDING
    assert len(output.boxes) > 0
    assert output.confidence > 0.0


def test_change_detection_model(synthetic_bitemporal_pngs):
    t1_bytes, t2_bytes = synthetic_bitemporal_pngs
    model = ChangeDetectionModel()
    assert model.health() is True

    inputs = ModelInput(
        model_id="CHANGE_DETECTION",
        image_bytes=[t1_bytes, t2_bytes],
    )
    output = model.infer(inputs)
    assert output.model_id == "CHANGE_DETECTION"
    assert output.task == TaskType.BI_TEMPORAL_CHANGE_MAP
    assert output.change_mask_bytes is not None
    assert output.confidence > 0.0
    assert len(output.boxes) > 0


def test_change_vqa_model(synthetic_bitemporal_pngs):
    t1_bytes, t2_bytes = synthetic_bitemporal_pngs
    model = ChangeVQAModel()
    assert model.health() is True

    inputs = ModelInput(
        model_id="CHANGE_VQA",
        image_bytes=[t1_bytes, t2_bytes],
        question="Has built-up area increased?",
    )
    output = model.infer(inputs)
    assert output.model_id == "CHANGE_VQA"
    assert output.task == TaskType.CHANGE_BASED_VQA
    assert "Yes" in output.answer or "increase" in output.answer.lower()
    assert output.confidence > 0.5


def test_optical_sar_fusion_model(synthetic_optical_png, synthetic_sar_png):
    model = OpticalSARFusionModel()
    assert model.health() is True

    inputs = ModelInput(
        model_id="OPTICAL_SAR_FUSION",
        image_bytes=[synthetic_optical_png, synthetic_sar_png],
        question="Perform cross-modal fusion analysis of terrain.",
    )
    output = model.infer(inputs)
    assert output.model_id == "OPTICAL_SAR_FUSION"
    assert output.task == TaskType.CROSS_MODAL_FUSION
    assert output.answer is not None
    assert output.confidence > 0.5
