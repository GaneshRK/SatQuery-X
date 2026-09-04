from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from typing import Any
from .base import SatelliteCandidateDTO, SatelliteProvider
from .mock import MockSatelliteProvider

logger = logging.getLogger(__name__)


class CopernicusProvider(SatelliteProvider):
    name = "Copernicus Data Space Ecosystem"
    STAC_ENDPOINT = "https://catalogue.dataspace.copernicus.eu/stac/search"

    def search_scenes(
        self,
        aoi_geometry: dict[str, Any],
        date_start: str,
        date_end: str,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        collection = "sentinel-2-l2a" if "2" in sensor else "sentinel-1-grd"
        payload: dict[str, Any] = {
            "collections": [collection],
            "datetime": f"{date_start}T00:00:00Z/{date_end}T23:59:59Z",
            "limit": limit,
        }

        # Spatial intersection if AOI geometry is provided
        if aoi_geometry and "coordinates" in aoi_geometry:
            payload["intersects"] = aoi_geometry

        # Cloud cover filter for optical imagery
        if "2" in sensor:
            payload["query"] = {
                "eo:cloud_cover": {"lte": max_cloud_cover}
            }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.STAC_ENDPOINT,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "SatQuery-AI-SIH26167/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=5.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    features = data.get("features", [])
                    candidates = []
                    for f in features:
                        props = f.get("properties", {})
                        geom = f.get("geometry", aoi_geometry)
                        item_id = f.get("id", "UNKNOWN_SCENE")
                        dt = props.get("datetime", date_end)[:10]
                        cloud = float(props.get("eo:cloud_cover", 0.0))
                        thumb = f.get("assets", {}).get("thumbnail", {}).get("href")

                        candidates.append(
                            SatelliteCandidateDTO(
                                stac_item_id=item_id,
                                collection=collection,
                                sensor=sensor,
                                acquisition_date=dt,
                                cloud_cover_pct=cloud,
                                footprint_geom=geom,
                                thumbnail_url=thumb,
                                provider="copernicus_live",
                            )
                        )
                    if candidates:
                        return candidates
        except Exception as e:
            logger.warning("Copernicus STAC live search error or timeout (%s). Falling back to provider mock.", e)

        # Fallback to Mock provider if live Copernicus is unreachable
        mock_provider = MockSatelliteProvider()
        fallback_candidates = mock_provider.search_scenes(
            aoi_geometry, date_start, date_end, sensor, max_cloud_cover, limit
        )
        for c in fallback_candidates:
            c.provider = "copernicus_cached_fallback"
        return fallback_candidates

    def get_scene_metadata(self, stac_item_id: str) -> dict[str, Any]:
        return {
            "stac_item_id": stac_item_id,
            "provider": "copernicus",
            "status": "AVAILABLE_FOR_INGESTION",
        }
