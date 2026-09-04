import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.sessions.models import Session
from apps.queries.models import Query
from apps.evidence.models import EvidenceRegion

User = get_user_model()


@pytest.fixture
def api_client():
    user = User.objects.create_user(username="analyst_test", email="analyst@example.com", password="password123")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_system_health_endpoint(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/health/")
    assert resp.status_code == 200
    data = resp.json()
    assert "subsystems" in data
    assert "django" in data["subsystems"]
    assert "database" in data["subsystems"]
    assert "storage" in data["subsystems"]


@pytest.mark.django_db
def test_query_exports(api_client):
    client, user = api_client
    session = Session.objects.create(user=user, name="Export Session")
    query = Query.objects.create(
        session=session,
        user=user,
        text="Identify structures in zone A",
        answer="Detected 4 structures",
        confidence=0.91,
        status="COMPLETED",
    )
    EvidenceRegion.objects.create(
        query=query,
        geojson_geometry={"type": "Polygon", "coordinates": [[[93.0, 26.5], [93.1, 26.5], [93.1, 26.6], [93.0, 26.6], [93.0, 26.5]]]},
        class_name="building",
        confidence=0.91,
        area_m2=5000.0,
        area_km2=0.005,
    )

    # Test GeoJSON export
    resp_geojson = client.get(f"/api/v1/sessions/{session.id}/queries/{query.id}/export/geojson/")
    assert resp_geojson.status_code == 200
    geojson_data = resp_geojson.json()
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"]) == 1

    # Test CSV export
    resp_csv = client.get(f"/api/v1/sessions/{session.id}/queries/{query.id}/export/csv/")
    assert resp_csv.status_code == 200
    assert "building" in resp_csv.content.decode("utf-8")

    # Test JSON 10-key contract export
    resp_json = client.get(f"/api/v1/sessions/{session.id}/queries/{query.id}/export/json/")
    assert resp_json.status_code == 200
    contract = resp_json.json()
    assert "answer" in contract
    assert "confidence" in contract
    assert "findings" in contract
    assert "limitations" in contract
