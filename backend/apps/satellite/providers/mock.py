from __future__ import annotations
from typing import Any
from .base import SatelliteCandidateDTO, SatelliteProvider


class MockSatelliteProvider(SatelliteProvider):
    name = "Test Fixture Mock Provider (Unit Tests Only)"

    def search_scenes(
        self,
        aoi_geometry: dict[str, Any],
        date_start: str,
        date_end: str,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        date_str = date_end.replace("-", "")
        start_str = date_start.replace("-", "")

        is_s2 = "2" in sensor
        if is_s2:
            candidates = [
                SatelliteCandidateDTO(
                    stac_item_id=f"S2A_MSIL2A_{date_str}T051651_N0500_R062_T43REQ",
                    collection="sentinel-2-l2a",
                    sensor="SENTINEL-2",
                    acquisition_date=date_end,
                    cloud_cover_pct=2.4,
                    footprint_geom=aoi_geometry or {"type": "Polygon", "coordinates": [[[93.0, 26.5], [93.25, 26.5], [93.25, 26.75], [93.0, 26.75], [93.0, 26.5]]]},
                    thumbnail_url="https://browser.dataspace.copernicus.eu/sample_thumb_s2.jpg",
                    provider="TEST_MOCK_ONLY",
                    is_synthetic=True,
                ),
                SatelliteCandidateDTO(
                    stac_item_id=f"S2B_MSIL2A_{start_str}T052649_N0500_R062_T43REQ",
                    collection="sentinel-2-l2a",
                    sensor="SENTINEL-2",
                    acquisition_date=date_start,
                    cloud_cover_pct=5.8,
                    footprint_geom=aoi_geometry or {"type": "Polygon", "coordinates": [[[93.0, 26.5], [93.25, 26.5], [93.25, 26.75], [93.0, 26.75], [93.0, 26.5]]]},
                    thumbnail_url="https://browser.dataspace.copernicus.eu/sample_thumb_s2b.jpg",
                    provider="TEST_MOCK_ONLY",
                    is_synthetic=True,
                ),
            ]
        else:
            candidates = [
                SatelliteCandidateDTO(
                    stac_item_id=f"S1A_IW_GRDH_1SDV_{date_str}T124500_049876_05FE12",
                    collection="sentinel-1-grd",
                    sensor="SENTINEL-1",
                    acquisition_date=date_end,
                    cloud_cover_pct=0.0,
                    footprint_geom=aoi_geometry or {"type": "Polygon", "coordinates": [[[93.0, 26.5], [93.25, 26.5], [93.25, 26.75], [93.0, 26.75], [93.0, 26.5]]]},
                    thumbnail_url="https://browser.dataspace.copernicus.eu/sample_thumb_s1.jpg",
                    provider="TEST_MOCK_ONLY",
                    is_synthetic=True,
                )
            ]

        return [c for c in candidates if c.cloud_cover_pct <= max_cloud_cover][:limit]

    def get_scene_metadata(self, stac_item_id: str) -> dict[str, Any]:
        return {
            "stac_item_id": stac_item_id,
            "provider": "mock_cdse",
            "sensor": "SENTINEL-2" if "S2" in stac_item_id else "SENTINEL-1",
            "resolution_m": 10.0,
            "crs": "EPSG:4326",
            "status": "SIMULATED_READY",
        }
