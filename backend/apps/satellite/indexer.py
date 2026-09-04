from __future__ import annotations
import logging
from datetime import datetime, date
from typing import Any, List, Dict
from django.utils import timezone
from apps.satellite.models import (
    AreaOfInterest,
    SatelliteScene,
    SatelliteAsset,
    TemporalObservation,
    DataProvider,
    SatelliteCollection,
)
from apps.satellite.providers import get_satellite_provider, SatelliteProvider

logger = logging.getLogger(__name__)


class HistoricalCatalogueIndexer:
    """
    Indexes Earth observation catalogue metadata across historical timelines (2015 -> 2026)
    into local PostgreSQL/SQLite database models without storing massive raw raster binaries.
    """

    def __init__(self, provider: SatelliteProvider | None = None):
        self.provider = provider or get_satellite_provider()

    def index_aoi_history(
        self,
        aoi: AreaOfInterest,
        start_year: int = 2016,
        end_year: int = 2026,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float = 25.0,
        samples_per_year: int = 2,
    ) -> Dict[str, Any]:
        """
        Populate historical SatelliteScene and TemporalObservation records across yearly intervals.
        """
        indexed_scenes: List[SatelliteScene] = []
        observations_created = 0

        # Ensure default DataProvider exists
        provider_obj, _ = DataProvider.objects.get_or_create(
            slug="copernicus-dataspace",
            defaults={
                "name": "Copernicus Data Space Ecosystem",
                "base_url": "https://dataspace.copernicus.eu",
                "stac_endpoint": "https://stac.dataspace.copernicus.eu/v1",
                "is_active": True,
            },
        )

        for year in range(start_year, end_year + 1):
            date_start = f"{year}-01-01"
            date_end = f"{year}-12-31"

            try:
                candidates = self.provider.search_scenes(
                    aoi_geometry=aoi.geometry,
                    date_start=date_start,
                    date_end=date_end,
                    sensor=sensor,
                    max_cloud_cover=max_cloud_cover,
                    limit=samples_per_year,
                )
            except Exception as e:
                logger.warning("Historical search failed for %s year %d: %s", aoi.name, year, e)
                continue

            for cand in candidates:
                try:
                    # Parse acquisition datetime
                    acq_dt_str = cand.acquisition_date
                    if len(acq_dt_str) == 10:
                        acq_dt = timezone.make_aware(datetime.strptime(acq_dt_str, "%Y-%m-%d"))
                    else:
                        acq_dt = datetime.fromisoformat(acq_dt_str.replace("Z", "+00:00"))

                    # Compute deterministic quality score based on cloud cover
                    cloud_pct = cand.cloud_cover_pct if cand.cloud_cover_pct is not None else 10.0
                    quality_score = round(max(0.05, 1.0 - (cloud_pct / 100.0)), 3)

                    # Determine platform & sensor modality
                    platform = "Sentinel-2A" if "2A" in cand.stac_item_id else ("Sentinel-2B" if "2B" in cand.stac_item_id else ("Sentinel-1A" if "1A" in cand.stac_item_id else "Sentinel-2"))
                    sensor_type = "SAR" if "1" in sensor else "OPTICAL"
                    modality = "SAR_C_BAND" if sensor_type == "SAR" else "MULTISPECTRAL"

                    # Upsert SatelliteScene
                    scene, created = SatelliteScene.objects.update_or_create(
                        provider="copernicus",
                        collection=cand.collection,
                        external_id=cand.stac_item_id,
                        defaults={
                            "platform": platform,
                            "mission": "Sentinel-1" if sensor_type == "SAR" else "Sentinel-2",
                            "instrument": "C-SAR" if sensor_type == "SAR" else "MSI",
                            "acquisition_datetime": acq_dt,
                            "processing_level": "LEVEL2A" if sensor_type == "OPTICAL" else "GRD",
                            "cloud_cover": cand.cloud_cover_pct,
                            "geometry": cand.footprint_geom or aoi.geometry,
                            "bbox": aoi.bbox,
                            "crs": "EPSG:4326",
                            "resolution": 10.0,
                            "sensor": sensor_type,
                            "modality": modality,
                            "thumbnail_url": cand.thumbnail_url or "",
                            "availability_status": "INDEXED",
                            "metadata": {
                                "source": "Copernicus STAC v1",
                                "assets_count": len(cand.assets_summary),
                            },
                        },
                    )

                    # Ingest or update SatelliteAsset items
                    for asset_key, asset_info in cand.assets_summary.items():
                        if isinstance(asset_info, dict) and asset_info.get("href"):
                            SatelliteAsset.objects.get_or_create(
                                scene=scene,
                                asset_key=asset_key,
                                defaults={
                                    "href": asset_info["href"],
                                    "asset_type": asset_info.get("type") or "image/tiff",
                                    "is_downloaded": False,
                                },
                            )

                    # Upsert TemporalObservation
                    obs_date = acq_dt.date()
                    obs, obs_created = TemporalObservation.objects.update_or_create(
                        aoi=aoi,
                        scene=scene,
                        defaults={
                            "observation_date": obs_date,
                            "year": obs_date.year,
                            "month": obs_date.month,
                            "cloud_cover": cand.cloud_cover_pct,
                            "quality_score": quality_score,
                            "thumbnail_url": cand.thumbnail_url or "",
                            "is_preferred": (cloud_pct < 15.0),
                        },
                    )

                    indexed_scenes.append(scene)
                    if obs_created:
                        observations_created += 1

                except Exception as ex:
                    logger.error("Failed to index scene %s: %s", cand.stac_item_id, ex)

        return {
            "aoi_id": str(aoi.id),
            "aoi_name": aoi.name,
            "scenes_indexed": len(indexed_scenes),
            "observations_created": observations_created,
            "years_range": f"{start_year}-{end_year}",
            "status": "COMPLETED",
        }
