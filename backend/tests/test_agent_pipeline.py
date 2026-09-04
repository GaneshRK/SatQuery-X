import io
import numpy as np
from PIL import Image
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from apps.agent.agent import Agent
from apps.agent.contracts import ModelInput
from apps.agent.planner import create_execution_plan
from apps.agent.registry import get_model_wrapper, list_models_info
from apps.agent.understander import understand_query
from apps.agent.validator import validate_agent_inputs
from apps.imagery.models import ImageAsset, ImagePair
from apps.queries.models import Query
from apps.sessions.models import Session

User = get_user_model()


def _make_test_image_bytes(color=(100, 150, 100), size=(64, 64)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_understander_representative_queries():
    # 1. Describe
    i1 = understand_query("Describe the land-cover and major objects visible in this image.")
    assert i1.intent == "caption"

    # 2. Highlight
    i2 = understand_query("Highlight the water body referred to in the query.")
    assert i2.intent == "grounding"
    assert i2.target == "water"

    # 3. Change dates
    i3 = understand_query("What changed between these two dates, and where did the change occur?")
    assert i3.intent == "change_vqa"
    assert i3.temporal is True

    # 4. Optical + SAR
    i4 = understand_query("Use the optical and SAR images together to identify built-up and water-covered regions.")
    assert i4.intent == "optical_sar_fusion"
    assert i4.cross_modal is True

    # 5. Increase/decrease
    i5 = understand_query("Has the built-up area increased, decreased, or remained unchanged?")
    assert i5.intent == "change_vqa"
    assert i5.target == "built_up"


def test_model_registry_contracts_and_honesty():
    models = list_models_info()
    assert len(models) >= 6
    for m in models:
        assert m["adaptation"] == "baseline"  # Honest labeling per §2 & §9

    # Test RS_VQA wrapper
    vqa_model = get_model_wrapper("RS_VQA")
    out = vqa_model.predict(ModelInput(
        model_id="RS_VQA",
        image_bytes=[_make_test_image_bytes()],
        question="Is there vegetation in this image?",
    ))
    assert out.status == "ok"
    assert out.answer is not None
    assert out.raw.get("adaptation") == "baseline"

    # Test CHANGE_DETECTION wrapper
    cd_model = get_model_wrapper("CHANGE_DETECTION")
    out_cd = cd_model.predict(ModelInput(
        model_id="CHANGE_DETECTION",
        image_bytes=[_make_test_image_bytes((50, 50, 50)), _make_test_image_bytes((150, 150, 150))],
    ))
    assert out_cd.status == "ok"
    assert out_cd.change_mask is not None
    assert out_cd.raw.get("adaptation") == "baseline"


@pytest.mark.django_db
def test_end_to_end_single_image_vqa_agent():
    user = User.objects.create_user(username="agentuser", password="password")
    session = Session.objects.create(user=user, name="Agent Test Session")

    img_data = _make_test_image_bytes((80, 160, 80))
    asset = ImageAsset.objects.create(
        session=session,
        original_filename="sample_optical.png",
        file_format="PNG",
        modality="OPTICAL",
        sensor="SENTINEL-2",
        processing_status="VALIDATED",
    )
    asset.file.save("sample_optical.png", ContentFile(img_data))

    query = Query.objects.create(
        session=session,
        user=user,
        text="Describe the land-cover and major objects visible in this image.",
        image=asset,
    )

    result = Agent.run(query)
    assert result["status"] == "COMPLETED"
    assert query.status == "COMPLETED"
    assert query.answer is not None
    assert query.execution_steps.count() >= 1

    first_step = query.execution_steps.first()
    assert first_step.status == "DONE"
    assert first_step.tool_name == "RS_CAPTION"


@pytest.mark.django_db
def test_end_to_end_bitemporal_change_agent():
    user = User.objects.create_user(username="changeuser", password="password")
    session = Session.objects.create(user=user, name="BiTemporal Session")

    img_t1 = ImageAsset.objects.create(
        session=session,
        original_filename="t1.png",
        file_format="PNG",
        modality="OPTICAL",
        sensor="SENTINEL-2",
        processing_status="VALIDATED",
    )
    img_t1.file.save("t1.png", ContentFile(_make_test_image_bytes((60, 60, 60))))

    img_t2 = ImageAsset.objects.create(
        session=session,
        original_filename="t2.png",
        file_format="PNG",
        modality="OPTICAL",
        sensor="SENTINEL-2",
        processing_status="VALIDATED",
    )
    img_t2.file.save("t2.png", ContentFile(_make_test_image_bytes((180, 180, 180))))

    pair = ImagePair.objects.create(
        session=session,
        image_a=img_t1,
        image_b=img_t2,
        pair_type="BI_TEMPORAL",
        compatibility_status="COMPATIBLE",
    )

    query = Query.objects.create(
        session=session,
        user=user,
        text="Has the built-up area increased, decreased, or remained unchanged?",
        image_pair=pair,
    )

    result = Agent.run(query)
    assert result["status"] == "COMPLETED"
    assert query.answer is not None
    assert "increased" in query.answer.lower() or "unchanged" in query.answer.lower() or "area" in query.answer.lower()
    # Check that execution steps were logged in order
    steps = list(query.execution_steps.all())
    step_tools = [s.tool_name for s in steps]
    assert "CHANGE_DETECTION" in step_tools
    assert "CHANGE_VQA" in step_tools
    assert "AREA_QUANTIFIER" in step_tools
