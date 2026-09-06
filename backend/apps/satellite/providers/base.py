from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SatelliteCandidateDTO:
    stac_item_id: str
    collection: str
    sensor: str
    acquisition_date: str
    cloud_cover_pct: float
    footprint_geom: dict[str, Any]
    thumbnail_url: str | None = None
    assets_summary: dict[str, Any] = field(default_factory=dict)
    provider: str = "copernicus"
    is_synthetic: bool = False


class SatelliteProvider(ABC):
    name: str

    @abstractmethod
    def search_scenes(
        self,
        aoi_geometry: dict[str, Any],
        date_start: str,
        date_end: str,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        """Query provider STAC or Catalog API for scenes matching spatial and temporal filters."""
        pass

    @abstractmethod
    def get_scene_metadata(self, stac_item_id: str) -> dict[str, Any]:
        """Fetch granular band and product metadata for a specific scene."""
        pass
