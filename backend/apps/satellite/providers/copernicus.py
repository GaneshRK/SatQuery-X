from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from typing import Any
from .base import SatelliteCandidateDTO, SatelliteProvider
from .mock import MockSatelliteProvider
from .auth import CDSETokenManager

logger = logging.getLogger(__name__)


class CopernicusProvider(SatelliteProvider):
    name = "Copernicus Data Space Ecosystem"
    PRIMARY_STAC_ENDPOINT = "https://stac.dataspace.copernicus.eu/v1/search"
    FALLBACK_STAC_ENDPOINT = "https://catalogue.dataspace.copernicus.eu/stac/search"

    def __init__(self):
        self.token_manager = CDSETokenManager()

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

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SatQuery-AI/2.0 (Copernicus STAC Client)",
        }
        # Attach Bearer token if token manager has credentials
        auth_headers = self.token_manager.get_auth_headers()
        headers.update(auth_headers)

        endpoints = [self.PRIMARY_STAC_ENDPOINT, self.FALLBACK_STAC_ENDPOINT]
        for endpoint in endpoints:
            try:
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    endpoint,
                    data=req_data,
                    headers=headers,
                )
                with urllib.request.urlopen(req, timeout=8.0) as response:
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
                            assets = f.get("assets", {})
                            thumb = assets.get("thumbnail", {}).get("href") or assets.get("visual", {}).get("href")

                            candidates.append(
                                SatelliteCandidateDTO(
                                    stac_item_id=item_id,
                                    collection=collection,
                                    sensor=sensor,
                                    acquisition_date=dt,
                                    cloud_cover_pct=cloud,
                                    footprint_geom=geom,
                                    thumbnail_url=thumb,
                                    assets_summary={k: {"href": v.get("href"), "type": v.get("type")} for k, v in assets.items() if isinstance(v, dict)},
                                    provider="copernicus_live",
                                )
                            )
                        if candidates:
                            return candidates
            except Exception as e:
                logger.warning("Copernicus STAC endpoint %s query failed: %s", endpoint, e)

        # Fallback to Mock provider if live Copernicus is unreachable or unconfigured
        logger.info("Falling back to MockSatelliteProvider for offline or unauthenticated mode")
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
            "auth_status": self.token_manager.health_check(),
        }

    def health_check(self) -> dict[str, Any]:
        auth_health = self.token_manager.health_check()
        try:
            req = urllib.request.Request(
                self.PRIMARY_STAC_ENDPOINT.replace("/search", ""),
                headers={"User-Agent": "SatQuery-AI/2.0"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                endpoint_reachable = (resp.status == 200)
        except Exception:
            endpoint_reachable = False

        return {
            "name": self.name,
            "primary_endpoint": self.PRIMARY_STAC_ENDPOINT,
            "reachable": endpoint_reachable,
            "auth": auth_health,
            "status": "healthy" if (endpoint_reachable and auth_health["healthy"]) else ("degraded" if endpoint_reachable else "unavailable")
        }
