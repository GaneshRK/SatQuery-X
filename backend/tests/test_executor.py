"""Unit tests for Executor component and live step logging per §8.4."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from apps.agent.executor import execute_plan
from apps.imagery.models import ImageAsset
from apps.queries.models import Query
from apps.sessions.models import Session

User = get_user_model()


@pytest.mark.django_db
def test_executor_execution_steps_and_quantifier(synthetic_optical_png):
    user = User.objects.create_user(username="execuser", password="password")
    session = Session.objects.create(user=user, name="Executor Session")

    asset = ImageAsset.objects.create(
        session=session,
        original_filename="opt.png",
        file_format="PNG",
        modality="OPTICAL",
        sensor="SENTINEL-2",
        processing_status="VALIDATED",
        affine_transform=[10.0, 0.0, 1000.0, 0.0, -10.0, 5000.0],
        crs="EPSG:32643",
    )
    asset.file.save("opt.png", ContentFile(synthetic_optical_png))

    query = Query.objects.create(
        session=session,
        user=user,
        text="Highlight vegetation",
        image=asset,
    )

    plan = {
        "mode": "SINGLE_IMAGE",
        "task": "GROUNDING",
        "steps": [
            {"step": 1, "tool": "RS_GROUNDING", "parameters": {"prompt": "vegetation"}},
            {"step": 2, "tool": "AREA_QUANTIFIER", "parameters": {}},
        ],
    }

    res = execute_plan(query, plan, [asset])
    assert res["status"] == "COMPLETED"
    assert query.execution_steps.count() == 2

    step1 = query.execution_steps.get(step_number=1)
    assert step1.status == "DONE"
    assert step1.tool_name == "RS_GROUNDING"

    step2 = query.execution_steps.get(step_number=2)
    assert step2.status == "DONE"
    assert step2.tool_name == "AREA_QUANTIFIER"
