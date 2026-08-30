"""Unit tests for PlanExecutor and sequential execution trace synthesis."""

import uuid
from backend.planner.executor import PlanExecutor
from backend.planner.schemas import PlanStep


def test_executor_single_image(synthetic_optical_png):
    executor = PlanExecutor()
    session_id = uuid.uuid4()
    query_id = uuid.uuid4()

    plan = [
        PlanStep(step=1, tool="RS_VQA", version="v0.1-baseline", params={"question": "What is visible?"}),
    ]

    trace = executor.execute(
        query="What is visible?",
        plan=plan,
        task_classification="vqa",
        detected_mode="single_image",
        image_bytes=[synthetic_optical_png],
        image_metadata=[{"width": 256, "height": 256, "sensor_type": "optical"}],
        session_id=session_id,
        query_id=query_id,
    )

    assert trace.query == "What is visible?"
    assert trace.detected_mode == "single_image"
    assert trace.answer is not None
    assert trace.confidence > 0.0
    assert "step1" in trace.timings_ms
    assert "total" in trace.timings_ms
    assert len(trace.errors) == 0


def test_executor_bitemporal_pipeline(synthetic_bitemporal_pngs):
    t1_bytes, t2_bytes = synthetic_bitemporal_pngs
    executor = PlanExecutor()
    session_id = uuid.uuid4()
    query_id = uuid.uuid4()

    plan = [
        PlanStep(step=1, tool="CHANGE_DETECTION", version="v0.1-baseline", params={}),
        PlanStep(step=2, tool="CHANGE_VQA", version="v0.1-baseline", params={"question": "Has area increased?", "change_mask_ref": "step1.change_mask"}),
    ]

    trace = executor.execute(
        query="Has area increased?",
        plan=plan,
        task_classification="change_vqa",
        detected_mode="bi_temporal",
        image_bytes=[t1_bytes, t2_bytes],
        image_metadata=[
            {"width": 256, "height": 256, "sensor_type": "optical"},
            {"width": 256, "height": 256, "sensor_type": "optical"},
        ],
        session_id=session_id,
        query_id=query_id,
    )

    assert trace.detected_mode == "bi_temporal"
    assert "step1" in trace.outputs
    assert "step2" in trace.outputs
    assert trace.evidence.change_mask_url is not None
    assert trace.evidence.quantified_area_km2 is not None
    assert trace.confidence > 0.0
