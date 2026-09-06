"""
Satellite catalogue indexing for SatQuery-X.

The indexer stores catalogue metadata only. It never creates synthetic
satellite scenes, fake footprints, fabricated cloud percentages, fabricated
resolutions, or invented quality scores.

Actual scene metadata comes from the configured satellite provider.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.satellite.models import (
    AreaOfInterest,
    DataProvider,
    SatelliteAsset,
    SatelliteCollection,
    SatelliteScene,
    TemporalObservation,
)
from apps.satellite.providers import (
    SatelliteProvider,
    get_satellite_provider,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================


def _parse_datetime(value: Any) -> datetime | None:
    """
    Parse an ISO-8601 acquisition timestamp.

    Date-only values are converted to midnight UTC because the catalogue
    contains a date but no time. This is not presented as the exact acquisition
    time.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime(
            value.year,
            value.month,
            value.day,
        )
    else:
        text = str(value).strip()

        if not text:
            return None

        try:
            if len(text) == 10:
                result = datetime.strptime(
                    text,
                    "%Y-%m-%d",
                )
            else:
                result = datetime.fromisoformat(
                    text.replace("Z", "+00:00")
                )
        except ValueError:
            logger.warning(
                "Unable to parse acquisition date: %r",
                value,
            )
            return None

    if timezone.is_naive(result):
        return timezone.make_aware(
            result,
            timezone=timezone.utc,
        )

    return result


def _normalise_sensor(sensor: Any) -> str:
    """
    Convert provider sensor labels into the local model vocabulary.

    This is classification of provider metadata, not an inference from image
    pixels.
    """
    text = str(sensor or "").strip().upper()

    if text in {"SENTINEL-1", "S1", "SAR"}:
        return "SAR"

    if text in {
        "SENTINEL-2",
        "S2",
        "OPTICAL",
        "MULTISPECTRAL",
    }:
        return "OPTICAL"

    if "HYPERSPECTRAL" in text:
        return "HYPERSPECTRAL"

    if "THERMAL" in text:
        return "THERMAL"

    return "UNKNOWN"


def _infer_modality(
    sensor: Any,
    candidate: Any,
) -> str:
    """
    Use explicit provider metadata where available.

    We do not infer scientific modality from arbitrary scene-ID characters.
    """
    explicit = (
        getattr(candidate, "modality", None)
        or getattr(candidate, "sensor_type", None)
        or getattr(candidate, "instrument", None)
    )

    if explicit:
        return str(explicit)

    normalised_sensor = _normalise_sensor(sensor)

    if normalised_sensor == "SAR":
        return "SAR"

    if normalised_sensor == "OPTICAL":
        return "MULTISPECTRAL"

    return ""


def _candidate_value(candidate: Any, *names: str) -> Any:
    """
    Read the first non-empty value from a provider candidate.

    Supports both dataclass-style objects and dictionaries so the indexer
    remains compatible with provider implementations.
    """
    for name in names:
        if isinstance(candidate, dict):
            value = candidate.get(name)
        else:
            value = getattr(candidate, name, None)

        if value is not None and value != "":
            return value

    return None


def _candidate_dict(candidate: Any) -> dict[str, Any]:
    """
    Convert provider candidate metadata into a JSON-safe dictionary when
    possible.
    """
    if isinstance(candidate, dict):
        return dict(candidate)

    result: dict[str, Any] = {}

    for attribute in (
        "stac_item_id",
        "collection",
        "acquisition_date",
        "cloud_cover_pct",
        "footprint_geom",
        "bbox",
        "geometry",
        "platform",
        "mission",
        "instrument",
        "sensor",
        "sensor_type",
        "modality",
        "processing_level",
        "crs",
        "resolution",
        "stac_item_url",
        "thumbnail_url",
        "assets",
        "metadata",
    ):
        value = getattr(candidate, attribute, None)

        if value is not None:
            result[attribute] = value

    return result


def _validate_cloud_cover(value: Any) -> float | None:
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not 0 <= result <= 100:
        logger.warning(
            "Ignoring invalid provider cloud cover value: %r",
            value,
        )
        return None

    return result


def _validate_resolution(value: Any) -> float | None:
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if result <= 0:
        logger.warning(
            "Ignoring invalid provider resolution value: %r",
            value,
        )
        return None

    return result


def _quality_score_from_metadata(
    candidate: Any,
) -> float | None:
    """
    Return an explicitly supplied quality score.

    Cloud cover is deliberately NOT converted into a quality score because
    doing so would introduce an undocumented scientific scoring function.
    """
    value = _candidate_value(
        candidate,
        "quality_score",
        "quality",
        "quality_metric",
    )

    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not 0 <= result <= 1:
        return None

    return result


def _provider_identity(provider: SatelliteProvider) -> dict[str, str]:
    """
    Extract provider identity without hardcoding a provider name.
    """
    name = (
        getattr(provider, "name", None)
        or provider.__class__.__name__
    )

    slug = getattr(
        provider,
        "slug",
        None,
    )

    return {
        "name": str(name),
        "slug": str(slug or "").strip(),
    }


def _ensure_provider_record(
    provider: SatelliteProvider,
) -> DataProvider:
    """
    Resolve the local DataProvider record from provider metadata.

    Provider URLs are taken from the provider implementation where available.
    """
    identity = _provider_identity(provider)

    provider_name = identity["name"]
    provider_slug = identity["slug"]

    if not provider_slug:
        provider_slug = (
            provider_name.lower()
            .replace(" ", "-")
            .replace("_", "-")
        )

    base_url = (
        getattr(provider, "base_url", None)
        or getattr(provider, "url", None)
        or getattr(provider, "endpoint", None)
    )

    stac_endpoint = (
        getattr(provider, "stac_endpoint", None)
        or getattr(provider, "stac_url", None)
    )

    lookup = DataProvider.objects.filter(
        slug=provider_slug,
    ).first()

    if lookup:
        changed = False

        if base_url and lookup.base_url != base_url:
            lookup.base_url = base_url
            changed = True

        if stac_endpoint and lookup.stac_endpoint != stac_endpoint:
            lookup.stac_endpoint = stac_endpoint
            changed = True

        if not lookup.is_active:
            lookup.is_active = True
            changed = True

        if changed:
            lookup.save(
                update_fields=[
                    "base_url",
                    "stac_endpoint",
                    "is_active",
                    "updated_at",
                ]
            )

        return lookup

    if not base_url:
        raise ValueError(
            "The configured satellite provider does not expose a base URL. "
            "Register the provider explicitly before indexing."
        )

    return DataProvider.objects.create(
        name=provider_name,
        slug=provider_slug,
        base_url=base_url,
        stac_endpoint=stac_endpoint or "",
        is_active=True,
    )


def _ensure_collection(
    provider_record: DataProvider,
    candidate: Any,
    sensor: str,
) -> SatelliteCollection | None:
    """
    Create/update collection metadata only when the provider supplies enough
    information to identify a collection.
    """
    collection_id = _candidate_value(
        candidate,
        "collection",
        "collection_id",
    )

    if not collection_id:
        return None

    collection_id = str(collection_id)

    collection_name = _candidate_value(
        candidate,
        "collection_name",
        "name",
    ) or collection_id

    sensor_type = _normalise_sensor(
        _candidate_value(
            candidate,
            "sensor_type",
            "sensor",
        )
        or sensor
    )

    if sensor_type not in {
        "OPTICAL",
        "SAR",
        "HYPERSPECTRAL",
        "THERMAL",
    }:
        sensor_type = "OPTICAL" if sensor == "SENTINEL-2" else "SAR"

    platform = _candidate_value(
        candidate,
        "platform",
    )

    instrument = _candidate_value(
        candidate,
        "instrument",
    )

    spatial_resolution = _validate_resolution(
        _candidate_value(
            candidate,
            "spatial_resolution_meters",
            "resolution",
            "gsd",
        )
    )

    revisit = _validate_resolution(
        _candidate_value(
            candidate,
            "temporal_revisit_days",
            "revisit_days",
        )
    )

    collection, created = SatelliteCollection.objects.get_or_create(
        provider=provider_record,
        collection_id=collection_id,
        defaults={
            "name": str(collection_name),
            "sensor_type": sensor_type,
            "platform": str(platform or ""),
            "instrument": str(instrument or ""),
            "spatial_resolution_meters": spatial_resolution,
            "temporal_revisit_days": revisit,
            "is_active": True,
            "metadata": {},
        },
    )

    update_fields: list[str] = []

    if collection.name != str(collection_name):
        collection.name = str(collection_name)
        update_fields.append("name")

    if sensor_type and collection.sensor_type != sensor_type:
        collection.sensor_type = sensor_type
        update_fields.append("sensor_type")

    if platform is not None:
        platform_text = str(platform)

        if collection.platform != platform_text:
            collection.platform = platform_text
            update_fields.append("platform")

    if instrument is not None:
        instrument_text = str(instrument)

        if collection.instrument != instrument_text:
            collection.instrument = instrument_text
            update_fields.append("instrument")

    if spatial_resolution is not None:
        if collection.spatial_resolution_meters != spatial_resolution:
            collection.spatial_resolution_meters = spatial_resolution
            update_fields.append("spatial_resolution_meters")

    if revisit is not None:
        if collection.temporal_revisit_days != revisit:
            collection.temporal_revisit_days = revisit
            update_fields.append("temporal_revisit_days")

    if update_fields:
        update_fields.append("updated_at")
        collection.save(update_fields=update_fields)

    return collection


def _asset_metadata_from_candidate(
    candidate: Any,
) -> dict[str, Any]:
    """
    Extract STAC asset metadata without downloading raster data.
    """
    assets = _candidate_value(
        candidate,
        "assets",
    )

    if assets is None:
        return {}

    if isinstance(assets, dict):
        return dict(assets)

    try:
        return dict(assets)
    except (TypeError, ValueError):
        return {}


def _upsert_scene_asset_records(
    scene: SatelliteScene,
    candidate: Any,
) -> int:
    """
    Persist remote STAC asset references.

    This function does not download data and does not manufacture raster files.
    """
    assets = _asset_metadata_from_candidate(candidate)

    if not assets:
        return 0

    created_or_updated = 0

    for asset_key, raw_asset in assets.items():
        if not isinstance(raw_asset, dict):
            continue

        href = (
            raw_asset.get("href")
            or raw_asset.get("url")
        )

        if not href:
            continue

        asset_type = (
            raw_asset.get("type")
            or raw_asset.get("media_type")
            or ""
        )

        metadata = {
            key: value
            for key, value in raw_asset.items()
            if key not in {"href", "url", "type", "media_type"}
        }

        SatelliteAsset.objects.update_or_create(
            scene=scene,
            asset_key=str(asset_key),
            defaults={
                "asset_type": str(asset_type),
                "href": str(href),
                "metadata": metadata,
            },
        )

        created_or_updated += 1

    return created_or_updated


# =============================================================================
# INDEXER
# =============================================================================


class HistoricalCatalogueIndexer:
    """
    Index satellite catalogue metadata for an AOI.

    The indexer intentionally does not:
      - generate synthetic satellite imagery
      - create fake scene coordinates
      - substitute an AOI footprint for a missing scene footprint
      - invent cloud percentages
      - invent spatial resolution
      - invent acquisition timestamps
      - invent quality scores
      - download massive raster binaries
    """

    def __init__(
        self,
        provider: SatelliteProvider | None = None,
    ):
        self.provider = (
            provider
            or get_satellite_provider()
        )

    def index_aoi_history(
        self,
        aoi: AreaOfInterest,
        start_year: int = 2016,
        end_year: int | None = None,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float | None = None,
        samples_per_year: int = 2,
    ) -> dict[str, Any]:
        """
        Search and index catalogue observations for an AOI.

        ``max_cloud_cover`` is optional. If omitted, no cloud-cover threshold
        is introduced by this indexer.
        """
        if not aoi.geometry:
            raise ValueError(
                "AOI geometry is required for catalogue indexing."
            )

        if end_year is None:
            end_year = timezone.now().year

        if start_year > end_year:
            raise ValueError(
                "start_year must not be greater than end_year."
            )

        if samples_per_year <= 0:
            raise ValueError(
                "samples_per_year must be greater than zero."
            )

        if max_cloud_cover is not None:
            if not 0 <= max_cloud_cover <= 100:
                raise ValueError(
                    "max_cloud_cover must be between 0 and 100."
                )

        provider_record = _ensure_provider_record(
            self.provider
        )

        indexed_scene_ids: list[str] = []
        indexed_observation_ids: list[str] = []

        discovered_count = 0
        scene_created_count = 0
        scene_updated_count = 0
        observation_created_count = 0
        observation_updated_count = 0
        asset_count = 0

        errors: list[dict[str, Any]] = []

        for year in range(
            start_year,
            end_year + 1,
        ):
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
            except Exception as exc:
                logger.exception(
                    "Satellite catalogue search failed for AOI %s, year %s",
                    aoi.id,
                    year,
                )

                errors.append(
                    {
                        "year": year,
                        "stage": "catalogue_search",
                        "error": str(exc),
                    }
                )
                continue

            if candidates is None:
                continue

            for candidate in candidates:
                discovered_count += 1

                try:
                    result = self._index_candidate(
                        aoi=aoi,
                        provider_record=provider_record,
                        candidate=candidate,
                        requested_sensor=sensor,
                    )

                    scene = result["scene"]
                    observation = result["observation"]

                    indexed_scene_ids.append(
                        str(scene.id)
                    )

                    indexed_observation_ids.append(
                        str(observation.id)
                    )

                    if result["scene_created"]:
                        scene_created_count += 1
                    else:
                        scene_updated_count += 1

                    if result["observation_created"]:
                        observation_created_count += 1
                    else:
                        observation_updated_count += 1

                    asset_count += result["asset_count"]

                except Exception as exc:
                    logger.exception(
                        "Failed to index satellite candidate for AOI %s",
                        aoi.id,
                    )

                    errors.append(
                        {
                            "year": year,
                            "stage": "candidate_index",
                            "stac_item_id": _candidate_value(
                                candidate,
                                "stac_item_id",
                                "id",
                            ),
                            "error": str(exc),
                        }
                    )

        unique_scene_ids = list(
            dict.fromkeys(indexed_scene_ids)
        )

        unique_observation_ids = list(
            dict.fromkeys(indexed_observation_ids)
        )

        return {
            "status": (
                "COMPLETED"
                if not errors
                else "COMPLETED_WITH_ERRORS"
            ),
            "aoi_id": str(aoi.id),
            "provider": _provider_identity(
                self.provider
            ),
            "sensor": sensor,
            "start_year": start_year,
            "end_year": end_year,
            "max_cloud_cover": max_cloud_cover,
            "samples_per_year": samples_per_year,
            "scenes_discovered": discovered_count,
            "scenes_indexed": len(unique_scene_ids),
            "observations_indexed": len(
                unique_observation_ids
            ),
            "scene_created": scene_created_count,
            "scene_updated": scene_updated_count,
            "observation_created": observation_created_count,
            "observation_updated": observation_updated_count,
            "assets_indexed": asset_count,
            "scene_ids": unique_scene_ids,
            "observation_ids": unique_observation_ids,
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # Candidate indexing
    # -------------------------------------------------------------------------

    @transaction.atomic
    def _index_candidate(
        self,
        aoi: AreaOfInterest,
        provider_record: DataProvider,
        candidate: Any,
        requested_sensor: str,
    ) -> dict[str, Any]:
        """
        Convert one provider result into local catalogue records.
        """
        external_id = _candidate_value(
            candidate,
            "stac_item_id",
            "external_id",
            "id",
        )

        if not external_id:
            raise ValueError(
                "Provider candidate has no stable STAC/external ID."
            )

        external_id = str(external_id)

        acquisition_value = _candidate_value(
            candidate,
            "acquisition_date",
            "acquisition_datetime",
            "datetime",
        )

        acquisition_datetime = _parse_datetime(
            acquisition_value
        )

        if acquisition_datetime is None:
            raise ValueError(
                f"Candidate {external_id} has no valid acquisition timestamp."
            )

        cloud_cover = _validate_cloud_cover(
            _candidate_value(
                candidate,
                "cloud_cover_pct",
                "cloud_cover",
            )
        )

        geometry = _candidate_value(
            candidate,
            "footprint_geom",
            "geometry",
            "footprint",
        )

        bbox = _candidate_value(
            candidate,
            "bbox",
            "bounding_box",
        )

        platform = _candidate_value(
            candidate,
            "platform",
        )

        mission = _candidate_value(
            candidate,
            "mission",
        )

        instrument = _candidate_value(
            candidate,
            "instrument",
        )

        processing_level = _candidate_value(
            candidate,
            "processing_level",
            "processing",
        )

        candidate_sensor = (
            _candidate_value(
                candidate,
                "sensor",
                "sensor_type",
            )
            or requested_sensor
        )

        sensor_type = _normalise_sensor(
            candidate_sensor
        )

        modality = _infer_modality(
            requested_sensor,
            candidate,
        )

        crs = _candidate_value(
            candidate,
            "crs",
            "coordinate_reference_system",
        )

        resolution = _validate_resolution(
            _candidate_value(
                candidate,
                "resolution",
                "spatial_resolution_meters",
                "gsd",
            )
        )

        stac_item_url = _candidate_value(
            candidate,
            "stac_item_url",
            "item_url",
            "url",
        )

        thumbnail_url = _candidate_value(
            candidate,
            "thumbnail_url",
            "thumbnail",
        )

        raw_metadata = _candidate_dict(
            candidate
        )

        scene_defaults = {
            "provider": provider_record.slug,
            "collection": str(
                _candidate_value(
                    candidate,
                    "collection",
                    "collection_id",
                )
                or ""
            ),
            "external_id": external_id,
            "platform": str(platform or ""),
            "mission": str(mission or ""),
            "instrument": str(instrument or ""),
            "acquisition_datetime": acquisition_datetime,
            "processing_level": str(
                processing_level or ""
            ),
            "cloud_cover": cloud_cover,
            "geometry": geometry,
            "bbox": bbox,
            "crs": str(crs or ""),
            "resolution": resolution,
            "sensor": sensor_type,
            "modality": modality,
            "metadata": raw_metadata,
            "stac_item_url": str(
                stac_item_url or ""
            ),
            "thumbnail_url": str(
                thumbnail_url or ""
            ),
            "availability_status": "CATALOGUED",
        }

        scene, scene_created = (
            SatelliteScene.objects.update_or_create(
                provider=provider_record.slug,
                collection=scene_defaults["collection"],
                external_id=external_id,
                defaults=scene_defaults,
            )
        )

        collection = _ensure_collection(
            provider_record=provider_record,
            candidate=candidate,
            sensor=requested_sensor,
        )

        if collection:
            scene.metadata = {
                **(
                    scene.metadata
                    if isinstance(scene.metadata, dict)
                    else {}
                ),
                "catalogue_collection_id": (
                    collection.collection_id
                ),
                "catalogue_provider_id": (
                    str(provider_record.id)
                ),
            }

            scene.save(
                update_fields=[
                    "metadata",
                    "updated_at",
                ]
            )

        asset_count = _upsert_scene_asset_records(
            scene=scene,
            candidate=candidate,
        )

        quality_score = _quality_score_from_metadata(
            candidate
        )

        observation, observation_created = (
            TemporalObservation.objects.update_or_create(
                aoi=aoi,
                scene=scene,
                defaults={
                    "observation_date": (
                        acquisition_datetime.date()
                    ),
                    "year": (
                        acquisition_datetime.year
                    ),
                    "month": (
                        acquisition_datetime.month
                    ),
                    "cloud_cover": cloud_cover,
                    "quality_score": quality_score,
                    "thumbnail_url": str(
                        thumbnail_url or ""
                    ),
                    "metadata": {
                        "source": (
                            provider_record.slug
                        ),
                        "scene_external_id": (
                            external_id
                        ),
                    },
                },
            )
        )

        self._update_preferred_observation(
            aoi=aoi,
            observation=observation,
        )

        return {
            "scene": scene,
            "observation": observation,
            "scene_created": scene_created,
            "observation_created": observation_created,
            "asset_count": asset_count,
        }

    # -------------------------------------------------------------------------
    # Preferred observation
    # -------------------------------------------------------------------------

    def _update_preferred_observation(
        self,
        aoi: AreaOfInterest,
        observation: TemporalObservation,
    ) -> None:
        """
        Mark a preferred observation only when the catalogue provides enough
        information to make the comparison defensible.

        If cloud-cover information is absent for all observations, no arbitrary
        preference is created.
        """
        observations = list(
            TemporalObservation.objects.filter(
                aoi=aoi
            ).select_related("scene")
        )

        candidates = [
            item
            for item in observations
            if item.cloud_cover is not None
        ]

        if not candidates:
            return

        preferred = min(
            candidates,
            key=lambda item: (
                item.cloud_cover,
                -(
                    item.observation_date.toordinal()
                ),
            ),
        )

        TemporalObservation.objects.filter(
            aoi=aoi
        ).exclude(
            id=preferred.id
        ).filter(
            is_preferred=True
        ).update(
            is_preferred=False
        )

        if not preferred.is_preferred:
            preferred.is_preferred = True
            preferred.save(
                update_fields=[
                    "is_preferred",
                    "updated_at",
                ]
            )


__all__ = [
    "HistoricalCatalogueIndexer",
]