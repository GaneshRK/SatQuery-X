import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.sessions.models import Session
from apps.agent.georeason import GeoReasonAgent, GeoReasonResult
from apps.agent.query_optimizer import QueryOptimizer

User = get_user_model()


@pytest.fixture
def auth_client():
    user = User.objects.create_user(username="test_analyst", password="password123")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_session_context_get_and_reset_endpoints(auth_client):
    client, user = auth_client
    session = Session.objects.create(name="Assam Flood Assessment", user=user)

    # 1. GET context
    resp = client.get(f"/api/v1/sessions/{session.id}/context/")
    assert resp.status_code == 200
    data = resp.json()
    assert "conversation_context" in data
    assert data["session_id"] == str(session.id)

    # 2. Mutate context directly
    session.conversation_context = {"active_focus": "water", "custom_tag": "test"}
    session.save(update_fields=["conversation_context"])

    resp_mutated = client.get(f"/api/v1/sessions/{session.id}/context/")
    assert resp_mutated.json()["conversation_context"]["active_focus"] == "water"

    # 3. Reset context
    reset_resp = client.post(f"/api/v1/sessions/{session.id}/context/reset/")
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["status"] == "reset"
    assert reset_data["conversation_context"]["active_focus"] == "landscape"


@pytest.mark.django_db
def test_visual_context_ingestion(auth_client):
    client, user = auth_client
    session = Session.objects.create(name="Barpeta Monitoring", user=user)

    visual_payload = {
        "center": [90.85, 26.32],
        "zoom": 13,
        "active_layer": "ndvi",
        "active_region": {"name": "Barpeta North", "bbox": [90.8, 26.3, 90.9, 26.4]},
    }

    resp = client.post(
        f"/api/v1/sessions/{session.id}/queries/",
        data={
            "text": "What is the vegetation status here?",
            "visual_context": visual_payload,
        },
        format="json",
    )
    assert resp.status_code in (200, 201, 202)

    session.refresh_from_db()
    assert session.conversation_context is not None
    assert session.conversation_context["current_visual_state"]["zoom"] == 13
    assert session.conversation_context["active_region"]["name"] == "Barpeta North"


def test_ui_actions_generation_in_georeason():
    agent = GeoReasonAgent()
    result = agent.synthesize(
        query_text="Where is the flood and show me exactly where it changed?",
        aoi_name="Kaziranga",
        satellite_scenes=[{"external_id": "S2A_2020", "cloud_cover": 2.0}],
        measurements={"total_inundated_area_ha": 3250.0, "change_percentage": 24.5},
        change_events=[{"change_type": "WATER_INUNDATION", "area_ha": 3250.0}],
        external_evidence=[],
        aoi_coords=[93.25, 26.65],
    )

    assert hasattr(result, "ui_actions")
    assert len(result.ui_actions) >= 1

    action_types = [a["type"] for a in result.ui_actions]
    assert "ZOOM_TO_REGION" in action_types
    assert "SHOW_LAYER" in action_types


def test_query_optimizer_ui_navigation_intents():
    optimizer = QueryOptimizer()

    # 1. Zoom command
    plan1 = optimizer.optimize("Zoom into Chennai")
    assert plan1.intent == "ui_navigation_command"
    assert plan1.operation == "action_dispatch"
    assert plan1.aoi["name"] == "Chennai Metropolitan Region"

    # 2. Show layer command
    plan2 = optimizer.optimize("Show vegetation index")
    assert plan2.intent == "ui_navigation_command"
    assert plan2.operation == "action_dispatch"

    # 3. Timeline navigation
    plan3 = optimizer.optimize("Show me 2020 observation")
    assert plan3.intent == "ui_navigation_command"
    assert plan3.operation == "action_dispatch"
