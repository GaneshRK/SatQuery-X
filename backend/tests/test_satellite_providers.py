"""Tests for the Copernicus and Mock satellite providers."""

import pytest
from apps.satellite.providers import get_satellite_provider
from apps.satellite.providers.mock import MockSatelliteProvider
from apps.satellite.providers.copernicus import CopernicusProvider


def test_provider_factory_mock():
    provider = get_satellite_provider(force_mock=True)
    assert isinstance(provider, MockSatelliteProvider)
    assert "Mock" in provider.name


def test_provider_factory_copernicus():
    provider = get_satellite_provider(force_mock=False)
    assert isinstance(provider, CopernicusProvider)
    assert "Copernicus" in provider.name


def test_mock_provider_search():
    provider = MockSatelliteProvider()
    results = provider.search_scenes(
        aoi_geometry={
            "type": "Polygon",
            "coordinates": [[[92.9, 26.5], [93.6, 26.5], [93.6, 26.8], [92.9, 26.8], [92.9, 26.5]]],
        },
        date_start="2024-04-01",
        date_end="2024-08-01",
        sensor="SENTINEL-2",
        max_cloud_cover=20.0,
        limit=5,
    )
    assert len(results) > 0
    first = results[0]
    assert first.stac_item_id
    assert first.collection
    assert first.cloud_cover_pct <= 20.0
    assert first.footprint_geom is not None


def test_mock_provider_get_metadata():
    provider = MockSatelliteProvider()
    meta = provider.get_scene_metadata("S2A_MSIL2A_20240718T043701_N0510_R133_T46RCS")
    assert meta["stac_item_id"] == "S2A_MSIL2A_20240718T043701_N0510_R133_T46RCS"
    assert "sensor" in meta
    assert "resolution_m" in meta
