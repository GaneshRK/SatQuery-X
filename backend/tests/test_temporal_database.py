import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from apps.satellite.models import (
    AreaOfInterest,
    SatelliteScene,
    SatelliteAsset,
    TemporalObservation,
    ChangeEvent,
    DataSyncJob,
)
from apps.satellite.indexer import HistoricalCatalogueIndexer
from apps.satellite.sync import RealtimeCatalogueSynchronizer


@pytest.fixture(autouse=True)
def mock_satellite_env(monkeypatch):
    monkeypatch.setenv("SATQUERY_MOCK_SATELLITE", "True")


@pytest.mark.django_db
def test_aoi_creation_and_spatial_attributes():
    client = APIClient()
    payload = {
        "name": "Chennai Port and Coastline",
        "description": "Port infrastructure and urban development observation target",
        "bbox": [80.25, 13.05, 80.35, 13.15],
    }
    url = reverse("satellite_aoi_list_create")
    resp = client.post(url, payload, format="json")
    assert resp.status_code == 201
    data = resp.data
    assert "aoi" in data
    assert data["aoi"]["name"] == "Chennai Port and Coastline"
    assert data["aoi"]["area_sqkm"] > 0
    assert len(data["aoi"]["centroid"]) == 2


@pytest.mark.django_db
def test_historical_catalogue_indexing():
    aoi = AreaOfInterest.objects.create(
        name="Pollachi Agricultural District",
        bbox=[76.95, 10.60, 77.05, 10.70],
        geometry={"type": "Polygon", "coordinates": [[[76.95, 10.60], [77.05, 10.60], [77.05, 10.70], [76.95, 10.70], [76.95, 10.60]]]},
        centroid=[77.0, 10.65],
        area_sqkm=120.5,
    )

    indexer = HistoricalCatalogueIndexer()
    res = indexer.index_aoi_history(
        aoi=aoi,
        start_year=2018,
        end_year=2024,
        sensor="SENTINEL-2",
        max_cloud_cover=20.0,
        samples_per_year=1,
    )

    assert res["status"] == "COMPLETED"
    assert res["scenes_indexed"] > 0
    assert res["observations_created"] > 0

    # Verify database records
    scenes = SatelliteScene.objects.filter(provider="copernicus")
    assert scenes.exists()
    for s in scenes:
        assert s.external_id != ""
        assert s.platform in ["Sentinel-2", "Sentinel-2A", "Sentinel-2B"]
        assert s.resolution == 10.0

    observations = TemporalObservation.objects.filter(aoi=aoi)
    assert observations.count() > 0
    for obs in observations:
        assert obs.year >= 2018
        assert obs.quality_score > 0.0


@pytest.mark.django_db
def test_aoi_timeline_api():
    client = APIClient()
    aoi = AreaOfInterest.objects.create(
        name="Bengaluru IT Corridor",
        bbox=[77.65, 12.90, 77.75, 13.00],
        geometry={"type": "Polygon", "coordinates": [[[77.65, 12.90], [77.75, 12.90], [77.75, 13.00], [77.65, 13.00], [77.65, 12.90]]]},
        centroid=[77.70, 12.95],
        area_sqkm=110.0,
    )

    url = reverse("satellite_aoi_timeline", kwargs={"aoi_id": aoi.id})
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.data
    assert data["aoi_name"] == "Bengaluru IT Corridor"
    assert "observations" in data
    assert "earliest_observation" in data
    assert "latest_observation" in data
    assert "data_gaps" in data


@pytest.mark.django_db
def test_bitemporal_change_detection_api():
    client = APIClient()
    aoi = AreaOfInterest.objects.create(
        name="Assam River Basin",
        bbox=[92.70, 26.10, 92.85, 26.25],
        geometry={"type": "Polygon", "coordinates": [[[92.70, 26.10], [92.85, 26.10], [92.85, 26.25], [92.70, 26.25], [92.70, 26.10]]]},
        centroid=[92.775, 26.175],
        area_sqkm=245.0,
    )

    url = reverse("satellite_change_analysis")
    payload = {
        "aoi_id": str(aoi.id),
        "change_type": "WATER_EXPANSION",
    }
    resp = client.post(url, payload, format="json")
    assert resp.status_code == 201
    data = resp.data
    assert data["change_type"] == "WATER_EXPANSION"
    assert data["area_hectares"] > 0
    assert data["confidence"] > 0.8
    assert "change_polygon" in data
    assert "evidence_data" in data


@pytest.mark.django_db
def test_realtime_catalogue_sync_status():
    client = APIClient()
    url = reverse("satellite_sync_status")
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.data
    assert "status" in data
    assert "provider" in data
    assert "scenes_indexed_total" in data
