"""
Explicit mock satellite provider for tests only.

WARNING:
    These candidates are synthetic test fixtures.

This provider must NEVER be used as an automatic production fallback.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .base import (
    SatelliteCandidateDTO,
    SatelliteProvider,
)


class MockSatelliteProvider(
    SatelliteProvider
):
    """
    Deterministic test fixture provider.

    This class exists so unit/integration tests can run without an external
    Copernicus account or network connection.

    It is intentionally marked synthetic.
    """

    name = (
        "Test Fixture Mock Provider (Tests Only)"
    )

    def search_scenes(
        self,
        aoi_geometry: dict[str, Any],
        date_start: str,
        date_end: str,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float | None = None,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        if not isinstance(
            aoi_geometry,
            dict,
        ):
            raise ValueError(
                "Mock provider requires a GeoJSON AOI."
            )

        if not aoi_geometry.get(
            "coordinates"
        ):
            raise ValueError(
                "Mock provider requires AOI coordinates."
            )

        start = datetime.strptime(
            date_start,
            "%Y-%m-%d",
        )

        end = datetime.strptime(
            date_end,
            "%Y-%m-%d",
        )

        if start > end:
            raise ValueError(
                "date_start cannot be later than date_end."
            )

        limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        normalized_sensor = (
            str(sensor)
            .strip()
            .upper()
        )

        if "SENTINEL-1" in normalized_sensor:
            collection = "sentinel-1-grd"
            scene_prefix = "S1A"
        else:
            collection = "sentinel-2-l2a"
            scene_prefix = "S2A"

        first_date = end
        second_date = max(
            start,
            end - timedelta(
                days=1
            ),
        )

        candidates = [
            SatelliteCandidateDTO(
                stac_item_id=(
                    f"TEST-{scene_prefix}-"
                    f"{first_date:%Y%m%d}-001"
                ),
                collection=collection,
                sensor=(
                    "SENTINEL-1"
                    if "SENTINEL-1"
                    in normalized_sensor
                    else "SENTINEL-2"
                ),
                acquisition_date=(
                    first_date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                cloud_cover_pct=(
                    0.0
                    if "SENTINEL-1"
                    in normalized_sensor
                    else 5.0
                ),
                footprint_geom=aoi_geometry,
                thumbnail_url=None,
                assets_summary={},
                provider="TEST_MOCK_ONLY",
                is_synthetic=True,
                metadata={
                    "fixture": True,
                    "purpose": (
                        "automated tests only"
                    ),
                },
            ),
            SatelliteCandidateDTO(
                stac_item_id=(
                    f"TEST-{scene_prefix}-"
                    f"{second_date:%Y%m%d}-002"
                ),
                collection=collection,
                sensor=(
                    "SENTINEL-1"
                    if "SENTINEL-1"
                    in normalized_sensor
                    else "SENTINEL-2"
                ),
                acquisition_date=(
                    second_date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                cloud_cover_pct=(
                    0.0
                    if "SENTINEL-1"
                    in normalized_sensor
                    else 8.0
                ),
                footprint_geom=aoi_geometry,
                thumbnail_url=None,
                assets_summary={},
                provider="TEST_MOCK_ONLY",
                is_synthetic=True,
                metadata={
                    "fixture": True,
                    "purpose": (
                        "automated tests only"
                    ),
                },
            ),
        ]

        if max_cloud_cover is not None:
            candidates = [
                candidate
                for candidate in candidates
                if (
                    candidate.cloud_cover_pct
                    is not None
                    and candidate.cloud_cover_pct
                    <= float(
                        max_cloud_cover
                    )
                )
            ]

        return candidates[:limit]

    def get_scene_metadata(
        self,
        stac_item_id: str,
    ) -> dict[str, Any]:
        return {
            "stac_item_id": str(
                stac_item_id
            ),
            "provider": (
                "TEST_MOCK_ONLY"
            ),
            "synthetic": True,
            "status": (
                "TEST_FIXTURE"
            ),
            "warning": (
                "This metadata is synthetic "
                "test data and must not be "
                "used as scientific evidence."
            ),
        }

    def health_check(
        self,
    ) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": "test_only",
            "healthy": True,
            "synthetic": True,
        }


__all__ = [
    "MockSatelliteProvider",
]