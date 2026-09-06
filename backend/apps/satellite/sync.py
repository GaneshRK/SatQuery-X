"""
Satellite catalogue synchronization for SatQuery-X.

This module synchronizes the latest available catalogue metadata for active
AOIs. It does not claim to provide live satellite video or real-time imagery.

All scene metadata and measurements must originate from the configured
satellite catalogue/provider.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.satellite.indexer import HistoricalCatalogueIndexer
from apps.satellite.models import (
    AOIMonitoring,
    AreaOfInterest,
    DataProvider,
    DataSyncJob,
)
from apps.satellite.providers import (
    SatelliteProvider,
    get_satellite_provider,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================


def _provider_identity(
    provider: SatelliteProvider,
) -> dict[str, str]:
    """Return non-sensitive provider identity metadata."""
    name = (
        getattr(provider, "name", None)
        or provider.__class__.__name__
    )

    slug = (
        getattr(provider, "slug", None)
        or ""
    )

    return {
        "name": str(name),
        "slug": str(slug),
    }


def _normalise_sensor(sensor: str | None) -> str:
    """
    Normalize a monitoring sensor value to the acquisition vocabulary.
    """
    value = str(sensor or "").strip().upper()

    if value in {
        "SENTINEL-1",
        "S1",
        "SAR",
    }:
        return "SENTINEL-1"

    if value in {
        "SENTINEL-2",
        "S2",
        "OPTICAL",
        "MULTISPECTRAL",
    }:
        return "SENTINEL-2"

    if value in {
        "BOTH",
        "OPTICAL+SAR",
        "SAR+OPTICAL",
    }:
        return "BOTH"

    return value or "SENTINEL-2"


def _sensor_list(
    target_sensor: str | None,
) -> list[str]:
    """
    Convert a monitoring target into one or more catalogue searches.
    """
    sensor = _normalise_sensor(target_sensor)

    if sensor == "BOTH":
        return [
            "SENTINEL-2",
            "SENTINEL-1",
        ]

    return [sensor]


def _date_window(
    lookback_days: int,
) -> tuple[str, str]:
    """
    Return an actual recent catalogue search window.
    """
    if lookback_days <= 0:
        raise ValueError(
            "lookback_days must be greater than zero."
        )

    end_date = timezone.now().date()
    start_date = (
        end_date
        - timedelta(days=lookback_days)
    )

    return (
        start_date.isoformat(),
        end_date.isoformat(),
    )


def _get_or_create_sync_job(
    provider: SatelliteProvider,
) -> DataSyncJob:
    """
    Create an audit record for a synchronization run.

    Provider identity is obtained from the configured provider rather than
    hardcoded here.
    """
    identity = _provider_identity(provider)

    provider_name = (
        identity["name"]
        or identity["slug"]
        or "configured-provider"
    )

    job = DataSyncJob.objects.create(
        provider=provider_name,
        status="PENDING",
        metadata={
            "provider": identity,
            "mode": (
                "latest available / near-real-time "
                "catalogue synchronization"
            ),
        },
    )

    return job


def _aoi_is_eligible(
    aoi: AreaOfInterest,
) -> bool:
    """
    An AOI must contain actual geometry before catalogue synchronization.
    """
    return bool(aoi.geometry)


def _monitoring_threshold(
    monitoring: AOIMonitoring,
) -> float | None:
    """
    Return the user's explicitly configured threshold.

    A missing threshold remains missing; it is not replaced by a fabricated
    scientific default.
    """
    value = monitoring.alert_on_change_pct

    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not 0 <= result <= 100:
        return None

    return result


# =============================================================================
# SYNCHRONIZER
# =============================================================================


class RealtimeCatalogueSynchronizer:
    """
    Synchronize the latest available satellite catalogue records.

    The name is retained for backward compatibility with the existing
    application. The actual product language should describe this as:

        "latest available / near-real-time catalogue synchronization"

    It is not live satellite footage.
    """

    def __init__(
        self,
        provider: SatelliteProvider | None = None,
        indexer: HistoricalCatalogueIndexer | None = None,
    ):
        self.provider = (
            provider
            or get_satellite_provider()
        )

        self.indexer = (
            indexer
            or HistoricalCatalogueIndexer(
                provider=self.provider
            )
        )

    # -------------------------------------------------------------------------
    # Active AOI synchronization
    # -------------------------------------------------------------------------

    def sync_active_aois(
        self,
        lookback_days: int = 14,
        max_aois: int | None = None,
    ) -> dict[str, Any]:
        """
        Synchronize recent catalogue observations for active monitoring AOIs.

        ``lookback_days`` controls the actual catalogue query window.

        No arbitrary cloud threshold is inserted here. Monitoring may specify
        one explicitly in the corresponding acquisition configuration, but
        synchronization itself should not silently discard observations.
        """
        if lookback_days <= 0:
            raise ValueError(
                "lookback_days must be greater than zero."
            )

        provider_identity = _provider_identity(
            self.provider
        )

        job = _get_or_create_sync_job(
            self.provider
        )

        job.mark_running()

        date_start, date_end = _date_window(
            lookback_days
        )

        monitoring_queryset = (
            AOIMonitoring.objects
            .select_related("aoi")
            .filter(
                is_active=True,
                aoi__geometry__isnull=False,
            )
            .order_by("created_at")
        )

        if max_aois is not None:
            if max_aois <= 0:
                raise ValueError(
                    "max_aois must be greater than zero."
                )

            monitoring_queryset = (
                monitoring_queryset[:max_aois]
            )

        monitoring_records = list(
            monitoring_queryset
        )

        total_discovered = 0
        total_indexed = 0
        total_assets = 0

        processed_aois = 0
        skipped_aois = 0

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        try:
            for monitoring in monitoring_records:
                aoi = monitoring.aoi

                if not _aoi_is_eligible(aoi):
                    skipped_aois += 1

                    results.append(
                        {
                            "aoi_id": str(aoi.id),
                            "status": "SKIPPED",
                            "reason": (
                                "AOI has no valid geometry."
                            ),
                        }
                    )

                    continue

                processed_aois += 1

                sensor_values = _sensor_list(
                    monitoring.target_sensor
                )

                aoi_result = {
                    "aoi_id": str(aoi.id),
                    "aoi_name": aoi.name,
                    "sensors": sensor_values,
                    "date_start": date_start,
                    "date_end": date_end,
                    "threshold": (
                        _monitoring_threshold(
                            monitoring
                        )
                    ),
                    "searches": [],
                }

                for sensor in sensor_values:
                    try:
                        search_result = (
                            self._sync_aoi_sensor(
                                aoi=aoi,
                                sensor=sensor,
                                date_start=date_start,
                                date_end=date_end,
                            )
                        )

                        aoi_result["searches"].append(
                            search_result
                        )

                        total_discovered += int(
                            search_result.get(
                                "scenes_discovered",
                                0,
                            )
                            or 0
                        )

                        total_indexed += int(
                            search_result.get(
                                "scenes_indexed",
                                0,
                            )
                            or 0
                        )

                        total_assets += int(
                            search_result.get(
                                "assets_indexed",
                                0,
                            )
                            or 0
                        )

                        for error in search_result.get(
                            "errors",
                            [],
                        ):
                            errors.append(
                                {
                                    "aoi_id": str(aoi.id),
                                    "sensor": sensor,
                                    **error,
                                }
                            )

                    except Exception as exc:
                        logger.exception(
                            "Catalogue sync failed for AOI %s / %s",
                            aoi.id,
                            sensor,
                        )

                        error_record = {
                            "aoi_id": str(aoi.id),
                            "sensor": sensor,
                            "error": str(exc),
                        }

                        errors.append(
                            error_record
                        )

                        aoi_result["searches"].append(
                            {
                                "status": "FAILED",
                                "sensor": sensor,
                                "error": str(exc),
                            }
                        )

                monitoring.last_checked_at = (
                    timezone.now()
                )

                monitoring.save(
                    update_fields=[
                        "last_checked_at",
                        "updated_at",
                    ]
                )

                results.append(
                    aoi_result
                )

            job.scenes_discovered = total_discovered
            job.scenes_ingested = total_indexed

            job.metadata = {
                **(
                    job.metadata
                    if isinstance(job.metadata, dict)
                    else {}
                ),
                "provider": provider_identity,
                "mode": (
                    "latest available / near-real-time "
                    "catalogue synchronization"
                ),
                "date_start": date_start,
                "date_end": date_end,
                "lookback_days": lookback_days,
                "processed_aois": processed_aois,
                "skipped_aois": skipped_aois,
                "assets_indexed": total_assets,
                "errors": len(errors),
            }

            job.save(
                update_fields=[
                    "scenes_discovered",
                    "scenes_ingested",
                    "metadata",
                    "updated_at",
                ]
            )

            if errors:
                job.mark_completed(
                    scenes_discovered=total_discovered,
                    scenes_ingested=total_indexed,
                )
                status = "COMPLETED_WITH_ERRORS"
            else:
                job.mark_completed(
                    scenes_discovered=total_discovered,
                    scenes_ingested=total_indexed,
                )
                status = "COMPLETED"

        except Exception as exc:
            logger.exception(
                "Satellite catalogue synchronization failed."
            )

            job.mark_failed(
                str(exc)
            )

            return {
                "status": "FAILED",
                "job_id": str(job.id),
                "provider": provider_identity,
                "date_start": date_start,
                "date_end": date_end,
                "processed_aois": processed_aois,
                "skipped_aois": skipped_aois,
                "scenes_discovered": total_discovered,
                "scenes_indexed": total_indexed,
                "assets_indexed": total_assets,
                "results": results,
                "errors": [
                    *errors,
                    {
                        "stage": "synchronization",
                        "error": str(exc),
                    },
                ],
            }

        return {
            "status": status,
            "job_id": str(job.id),
            "provider": provider_identity,
            "mode": (
                "latest available / near-real-time "
                "catalogue synchronization"
            ),
            "date_start": date_start,
            "date_end": date_end,
            "lookback_days": lookback_days,
            "processed_aois": processed_aois,
            "skipped_aois": skipped_aois,
            "scenes_discovered": total_discovered,
            "scenes_indexed": total_indexed,
            "assets_indexed": total_assets,
            "results": results,
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # Individual AOI/sensor synchronization
    # -------------------------------------------------------------------------

    @transaction.atomic
    def _sync_aoi_sensor(
        self,
        aoi: AreaOfInterest,
        sensor: str,
        date_start: str,
        date_end: str,
    ) -> dict[str, Any]:
        """
        Query and index one AOI/sensor combination.

        The provider is responsible for returning actual catalogue results.
        """
        candidates = self.provider.search_scenes(
            aoi_geometry=aoi.geometry,
            date_start=date_start,
            date_end=date_end,
            sensor=sensor,
            max_cloud_cover=None,
            limit=None,
        )

        if candidates is None:
            candidates = []

        candidates = list(candidates)

        indexed_scene_ids: list[str] = []
        indexed_observation_ids: list[str] = []

        errors: list[dict[str, Any]] = []

        for candidate in candidates:
            try:
                result = self.indexer._index_candidate(
                    aoi=aoi,
                    provider_record=self._provider_record(),
                    candidate=candidate,
                    requested_sensor=sensor,
                )

                indexed_scene_ids.append(
                    str(result["scene"].id)
                )

                indexed_observation_ids.append(
                    str(result["observation"].id)
                )

            except Exception as exc:
                logger.exception(
                    "Failed to index catalogue candidate."
                )

                errors.append(
                    {
                        "stac_item_id": (
                            self._candidate_id(
                                candidate
                            )
                        ),
                        "error": str(exc),
                    }
                )

        return {
            "status": (
                "COMPLETED"
                if not errors
                else "COMPLETED_WITH_ERRORS"
            ),
            "sensor": sensor,
            "date_start": date_start,
            "date_end": date_end,
            "scenes_discovered": len(candidates),
            "scenes_indexed": len(
                list(
                    dict.fromkeys(
                        indexed_scene_ids
                    )
                )
            ),
            "observations_indexed": len(
                list(
                    dict.fromkeys(
                        indexed_observation_ids
                    )
                )
            ),
            "assets_indexed": 0,
            "scene_ids": list(
                dict.fromkeys(
                    indexed_scene_ids
                )
            ),
            "observation_ids": list(
                dict.fromkeys(
                    indexed_observation_ids
                )
            ),
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # Provider record
    # -------------------------------------------------------------------------

    def _provider_record(self) -> DataProvider:
        """
        Resolve the local provider record through the indexer's provider
        handling.
        """
        from apps.satellite.indexer import (
            _ensure_provider_record,
        )

        return _ensure_provider_record(
            self.provider
        )

    # -------------------------------------------------------------------------
    # Candidate identity
    # -------------------------------------------------------------------------

    @staticmethod
    def _candidate_id(
        candidate: Any,
    ) -> str | None:
        if isinstance(candidate, dict):
            value = (
                candidate.get("stac_item_id")
                or candidate.get("external_id")
                or candidate.get("id")
            )
        else:
            value = (
                getattr(
                    candidate,
                    "stac_item_id",
                    None,
                )
                or getattr(
                    candidate,
                    "external_id",
                    None,
                )
                or getattr(
                    candidate,
                    "id",
                    None,
                )
            )

        return (
            str(value)
            if value is not None
            else None
        )


# =============================================================================
# BACKWARD-COMPATIBLE FUNCTION
# =============================================================================


def sync_latest_available_catalogue(
    *,
    provider: SatelliteProvider | None = None,
    lookback_days: int = 14,
    max_aois: int | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for Celery/tasks/management commands.
    """
    synchronizer = RealtimeCatalogueSynchronizer(
        provider=provider
    )

    return synchronizer.sync_active_aois(
        lookback_days=lookback_days,
        max_aois=max_aois,
    )


__all__ = [
    "RealtimeCatalogueSynchronizer",
    "sync_latest_available_catalogue",
]