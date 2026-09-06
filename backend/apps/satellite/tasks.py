"""
Celery tasks for the SatQuery-X satellite subsystem.

Important design rules
----------------------
1. Never generate synthetic satellite imagery.
2. Never fabricate CRS, resolution, footprint, cloud percentage,
   acquisition dates, NDVI, change percentages, or confidence.
3. Catalogue synchronization only indexes metadata returned by a
   configured satellite provider.
4. Raster-derived scientific measurements belong to the imagery/model
   analysis pipeline, not to catalogue synchronization.
5. A task must fail transparently when the required provider or imagery
   is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.satellite.indexer import HistoricalCatalogueIndexer
from apps.satellite.models import (
    AcquisitionRequest,
    DataSyncJob,
    SatelliteScene,
)
from apps.satellite.sync import (
    RealtimeCatalogueSynchronizer,
)


logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================


def _json_safe(value: Any) -> Any:
    """
    Convert common Python/Django values into JSON-compatible structures.
    """
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    if hasattr(
        value,
        "isoformat",
    ):
        try:
            return value.isoformat()
        except Exception:
            pass

    return str(value)


def _safe_int(
    value: Any,
    default: int | None = None,
) -> int | None:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _scene_has_assets(
    scene: SatelliteScene,
) -> bool:
    """
    Catalogue metadata is not considered imagery evidence.

    A scene can exist in the catalogue without a downloadable/registered
    raster asset.
    """
    try:
        return bool(
            scene.assets.exists()
        )
    except Exception:
        return False


def _task_error(
    message: str,
    *,
    task_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": "failed",
        "detail": message,
    }

    if task_id:
        result["task_id"] = task_id

    if extra:
        result.update(
            _json_safe(extra)
        )

    return result


# =============================================================================
# HISTORICAL CATALOGUE INDEXING
# =============================================================================


@shared_task(
    bind=True,
    autoretry_for=(
        ConnectionError,
        TimeoutError,
    ),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 3,
    },
)
def index_aoi_history_task(
    self,
    aoi_id: str,
    start_year: int,
    end_year: int,
    sensor: str,
    max_cloud_cover: float | None = None,
    samples_per_year: int = 1,
) -> dict[str, Any]:
    """
    Index historical catalogue metadata for one AOI.

    This task does NOT download or manufacture raster imagery.

    The provider is responsible for returning actual catalogue records.
    """

    if not aoi_id:
        return _task_error(
            "aoi_id is required.",
            task_id=self.request.id,
        )

    start_year = _safe_int(
        start_year
    )

    end_year = _safe_int(
        end_year
    )

    if (
        start_year is None
        or end_year is None
    ):
        return _task_error(
            "start_year and end_year must be integers.",
            task_id=self.request.id,
        )

    if start_year > end_year:
        return _task_error(
            "start_year cannot be later than end_year.",
            task_id=self.request.id,
        )

    if not sensor:
        return _task_error(
            "sensor is required.",
            task_id=self.request.id,
        )

    try:
        from apps.satellite.models import (
            AreaOfInterest,
        )

        aoi = AreaOfInterest.objects.get(
            id=aoi_id
        )

    except Exception:
        logger.exception(
            "Unable to resolve AOI %s.",
            aoi_id,
        )

        return _task_error(
            "The requested AOI could not be found.",
            task_id=self.request.id,
        )

    try:
        indexer = (
            HistoricalCatalogueIndexer()
        )

        result = (
            indexer.index_aoi_history(
                aoi=aoi,
                start_year=start_year,
                end_year=end_year,
                sensor=sensor,
                max_cloud_cover=max_cloud_cover,
                samples_per_year=samples_per_year,
            )
        )

        return {
            "status": "completed",
            "task_id": self.request.id,
            "aoi_id": str(
                aoi.id
            ),
            "result": _json_safe(
                result
            ),
        }

    except Exception as exc:
        logger.exception(
            "Historical catalogue indexing failed for AOI %s.",
            aoi_id,
        )

        return _task_error(
            "Historical satellite catalogue indexing failed.",
            task_id=self.request.id,
            extra={
                "aoi_id": str(
                    aoi.id
                ),
                "error_type": type(
                    exc
                ).__name__,
            },
        )


# =============================================================================
# LATEST AVAILABLE CATALOGUE SYNCHRONIZATION
# =============================================================================


@shared_task(
    bind=True,
    autoretry_for=(
        ConnectionError,
        TimeoutError,
    ),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 3,
    },
)
def sync_catalogue_task(
    self,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """
    Synchronize the latest available satellite catalogue.

    "Latest available" means records actually returned by the configured
    provider. It does not imply live satellite video or guaranteed real-time
    coverage.
    """

    lookback_days = _safe_int(
        lookback_days,
        default=7,
    )

    if lookback_days is None:
        lookback_days = 7

    if not 1 <= lookback_days <= 365:
        return _task_error(
            "lookback_days must be between 1 and 365.",
            task_id=self.request.id,
        )

    try:
        synchronizer = (
            RealtimeCatalogueSynchronizer()
        )

        result = (
            synchronizer.sync_active_aois(
                lookback_days=lookback_days
            )
        )

        return {
            "status": "completed",
            "task_id": self.request.id,
            "lookback_days": lookback_days,
            "result": _json_safe(
                result
            ),
        }

    except Exception as exc:
        logger.exception(
            "Satellite catalogue synchronization failed."
        )

        return _task_error(
            "Latest available satellite catalogue synchronization failed.",
            task_id=self.request.id,
            extra={
                "error_type": type(
                    exc
                ).__name__,
            },
        )


# =============================================================================
# COMPATIBILITY NAME
# =============================================================================


@shared_task(
    bind=True,
)
def sync_latest_available_catalogue_task(
    self,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """
    Compatibility wrapper for deployments using the longer task name.
    """

    return sync_catalogue_task.run(
        lookback_days=lookback_days
    )


# =============================================================================
# SATELLITE ACQUISITION REQUEST PROCESSING
# =============================================================================


@shared_task(
    bind=True,
    autoretry_for=(
        ConnectionError,
        TimeoutError,
    ),
    retry_backoff=True,
    retry_kwargs={
        "max_retries": 3,
    },
)
def process_acquisition_request_task(
    self,
    request_id: str,
) -> dict[str, Any]:
    """
    Process an AcquisitionRequest using the configured provider.

    The task only requests actual provider data.

    It never creates a synthetic Sentinel/EO raster when acquisition fails.
    """

    if not request_id:
        return _task_error(
            "request_id is required.",
            task_id=self.request.id,
        )

    try:
        acquisition = (
            AcquisitionRequest.objects
            .select_related(
                "session",
                "aoi",
            )
            .get(
                id=request_id
            )
        )

    except AcquisitionRequest.DoesNotExist:
        return _task_error(
            "The acquisition request was not found.",
            task_id=self.request.id,
        )

    # -------------------------------------------------------------------------
    # Provider lookup
    # -------------------------------------------------------------------------

    try:
        from apps.satellite.providers import (
            get_satellite_provider,
        )
    except ImportError:
        logger.exception(
            "Satellite provider registry is unavailable."
        )

        return _task_error(
            "Satellite provider integration is unavailable.",
            task_id=self.request.id,
        )

    sensor = getattr(
        acquisition,
        "sensor",
        None,
    )

    if not sensor:
        sensor = getattr(
            acquisition,
            "target_sensor",
            None,
        )

    if not sensor:
        return _task_error(
            "No sensor was specified for the acquisition request.",
            task_id=self.request.id,
        )

    try:
        provider = get_satellite_provider(
            sensor
        )
    except Exception:
        logger.exception(
            "Unable to initialize provider for sensor %s.",
            sensor,
        )

        return _task_error(
            "The configured satellite provider could not be initialized.",
            task_id=self.request.id,
        )

    if provider is None:
        return _task_error(
            f"No satellite provider is configured for sensor '{sensor}'.",
            task_id=self.request.id,
        )

    # -------------------------------------------------------------------------
    # Build provider request using only user/database values.
    # -------------------------------------------------------------------------

    aoi = getattr(
        acquisition,
        "aoi",
        None,
    )

    if aoi is None:
        return _task_error(
            "The acquisition request has no AOI.",
            task_id=self.request.id,
        )

    geometry = getattr(
        aoi,
        "geometry",
        None,
    )

    if not geometry:
        return _task_error(
            "The AOI has no geometry.",
            task_id=self.request.id,
        )

    start_date = getattr(
        acquisition,
        "start_date",
        None,
    )

    end_date = getattr(
        acquisition,
        "end_date",
        None,
    )

    if not (
        start_date
        and end_date
    ):
        return _task_error(
            "A valid acquisition date range is required.",
            task_id=self.request.id,
        )

    provider_kwargs = {
        "aoi_geometry": geometry,
        "start_date": start_date,
        "end_date": end_date,
    }

    max_cloud = getattr(
        acquisition,
        "max_cloud_cover",
        None,
    )

    if max_cloud is not None:
        provider_kwargs[
            "max_cloud_cover"
        ] = max_cloud

    limit = getattr(
        acquisition,
        "max_results",
        None,
    )

    if limit is not None:
        provider_kwargs[
            "limit"
        ] = limit

    # -------------------------------------------------------------------------
    # Provider search
    # -------------------------------------------------------------------------

    try:
        if hasattr(
            provider,
            "search_scenes",
        ):
            candidates = provider.search_scenes(
                **provider_kwargs
            )

        elif hasattr(
            provider,
            "search",
        ):
            candidates = provider.search(
                **provider_kwargs
            )

        else:
            return _task_error(
                "The configured satellite provider does not expose a scene-search operation.",
                task_id=self.request.id,
            )

    except Exception as exc:
        logger.exception(
            "Satellite provider search failed for acquisition %s.",
            request_id,
        )

        return _task_error(
            "Satellite provider search failed.",
            task_id=self.request.id,
            extra={
                "error_type": type(
                    exc
                ).__name__,
            },
        )

    if candidates is None:
        candidates = []

    if isinstance(
        candidates,
        dict,
    ):
        candidates = candidates.get(
            "scenes",
            candidates.get(
                "results",
                [],
            ),
        )

    try:
        candidates = list(
            candidates
        )
    except TypeError:
        candidates = []

    # -------------------------------------------------------------------------
    # Persist provider results through the indexer.
    # -------------------------------------------------------------------------

    indexer = (
        HistoricalCatalogueIndexer()
    )

    indexed = []
    errors = []

    for candidate in candidates:
        try:
            result = (
                indexer._index_candidate(
                    aoi=aoi,
                    candidate=candidate,
                )
            )

            if result is not None:
                indexed.append(
                    _json_safe(
                        result
                    )
                )

        except Exception as exc:
            logger.exception(
                "Failed to index provider candidate."
            )

            errors.append(
                {
                    "error_type": type(
                        exc
                    ).__name__,
                }
            )

    # -------------------------------------------------------------------------
    # Update acquisition status if those fields exist.
    # -------------------------------------------------------------------------

    try:
        if hasattr(
            acquisition,
            "status",
        ):
            acquisition.status = (
                "COMPLETED"
                if indexed
                else "NO_RESULTS"
            )

        if hasattr(
            acquisition,
            "completed_at",
        ):
            acquisition.completed_at = (
                timezone.now()
            )

        acquisition.save()

    except Exception:
        logger.debug(
            "Acquisition status update unavailable.",
            exc_info=True,
        )

    return {
        "status": (
            "completed"
            if indexed
            else "no_results"
        ),
        "task_id": self.request.id,
        "request_id": str(
            acquisition.id
        ),
        "sensor": sensor,
        "provider": getattr(
            provider,
            "name",
            provider.__class__.__name__,
        ),
        "provider_results": len(
            candidates
        ),
        "indexed_scenes": len(
            indexed
        ),
        "index_errors": errors,
        "results": indexed,
    }


# =============================================================================
# SCENE INGESTION COMPATIBILITY TASK
# =============================================================================


@shared_task(
    bind=True,
)
def ingest_satellite_candidate_task(
    self,
    candidate: dict[str, Any],
    aoi_id: str,
) -> dict[str, Any]:
    """
    Compatibility task for ingesting one provider candidate.

    The candidate must come from a real configured provider.
    """

    if not candidate:
        return _task_error(
            "A real provider candidate is required.",
            task_id=self.request.id,
        )

    try:
        from apps.satellite.models import (
            AreaOfInterest,
        )

        aoi = AreaOfInterest.objects.get(
            id=aoi_id
        )

    except Exception:
        return _task_error(
            "The requested AOI was not found.",
            task_id=self.request.id,
        )

    try:
        indexer = (
            HistoricalCatalogueIndexer()
        )

        result = (
            indexer._index_candidate(
                aoi=aoi,
                candidate=candidate,
            )
        )

        return {
            "status": "completed",
            "task_id": self.request.id,
            "aoi_id": str(
                aoi.id
            ),
            "result": _json_safe(
                result
            ),
        }

    except Exception as exc:
        logger.exception(
            "Satellite candidate ingestion failed."
        )

        return _task_error(
            "Satellite candidate ingestion failed.",
            task_id=self.request.id,
            extra={
                "error_type": type(
                    exc
                ).__name__,
            },
        )


# =============================================================================
# DERIVED-RASTER PLACEHOLDER / ROUTING TASK
# =============================================================================


@shared_task(
    bind=True,
)
def generate_derived_raster_task(
    self,
    scene_id: str,
    operation: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Route derived-raster generation to the actual analysis pipeline.

    This task deliberately does not create a fake NDVI/change raster.

    Supported operations must be implemented by a registered analysis agent.
    """

    if not scene_id:
        return _task_error(
            "scene_id is required.",
            task_id=self.request.id,
        )

    if not operation:
        return _task_error(
            "operation is required.",
            task_id=self.request.id,
        )

    try:
        scene = (
            SatelliteScene.objects
            .prefetch_related(
                "assets"
            )
            .get(
                id=scene_id
            )
        )

    except SatelliteScene.DoesNotExist:
        return _task_error(
            "The requested satellite scene was not found.",
            task_id=self.request.id,
        )

    if not _scene_has_assets(
        scene
    ):
        return _task_error(
            "The scene does not contain a usable imagery asset.",
            task_id=self.request.id,
        )

    # -------------------------------------------------------------------------
    # Delegate to the real agentic analysis subsystem.
    # -------------------------------------------------------------------------

    try:
        from apps.models_ai.manage import (
            model_manager,
        )

        model_id = (
            parameters or {}
        ).get(
            "model_id"
        )

        if not model_id:
            return _task_error(
                "No analysis model has been specified.",
                task_id=self.request.id,
            )

        if not model_manager.is_registered(
            model_id
        ):
            return _task_error(
                f"Analysis model '{model_id}' is not registered.",
                task_id=self.request.id,
            )

        model = model_manager.load_model(
            model_id
        )

        if model is None:
            return _task_error(
                f"Analysis model '{model_id}' could not be loaded.",
                task_id=self.request.id,
            )

        payload = {
            "operation": operation,
            "scene_id": str(
                scene.id
            ),
            "parameters": (
                parameters or {}
            ),
        }

        if hasattr(
            model,
            "predict",
        ):
            result = model.predict(
                payload
            )

        elif callable(
            model
        ):
            result = model(
                payload
            )

        else:
            return _task_error(
                "The registered analysis model cannot execute predictions.",
                task_id=self.request.id,
            )

        try:
            model_manager.mark_prediction(
                model_id
            )
        except Exception:
            logger.debug(
                "Unable to update model prediction statistics.",
                exc_info=True,
            )

        return {
            "status": "completed",
            "task_id": self.request.id,
            "scene_id": str(
                scene.id
            ),
            "operation": operation,
            "result": _json_safe(
                result
            ),
        }

    except ImportError:
        return _task_error(
            "The SatQuery-X model manager is unavailable.",
            task_id=self.request.id,
        )

    except Exception as exc:
        logger.exception(
            "Derived raster analysis failed."
        )

        return _task_error(
            "Derived raster analysis failed.",
            task_id=self.request.id,
            extra={
                "error_type": type(
                    exc
                ).__name__,
            },
        )


# =============================================================================
# EXPLICITLY DISABLED LEGACY SYNTHETIC GENERATOR
# =============================================================================


@shared_task(
    bind=True,
)
def generate_synthetic_sentinel_geotiff(
    self,
    *args,
    **kwargs,
) -> dict[str, Any]:
    """
    Legacy compatibility endpoint.

    Synthetic satellite imagery is intentionally disabled in SatQuery-X.

    Keeping this task name prevents old code/imports from crashing, while
    ensuring no synthetic scientific data can be produced.
    """

    logger.warning(
        "Blocked legacy synthetic Sentinel GeoTIFF generation."
    )

    return _task_error(
        (
            "Synthetic satellite GeoTIFF generation is disabled. "
            "SatQuery-X requires imagery from a real configured "
            "satellite data provider."
        ),
        task_id=self.request.id,
    )


# =============================================================================
# LEGACY ALIASES
# =============================================================================


index_historical_catalogue_task = (
    index_aoi_history_task
)

sync_latest_catalogue_task = (
    sync_catalogue_task
)

process_satellite_acquisition_task = (
    process_acquisition_request_task
)


__all__ = [
    "index_aoi_history_task",
    "index_historical_catalogue_task",
    "sync_catalogue_task",
    "sync_latest_catalogue_task",
    "sync_latest_available_catalogue_task",
    "process_acquisition_request_task",
    "process_satellite_acquisition_task",
    "ingest_satellite_candidate_task",
    "generate_derived_raster_task",
    "generate_synthetic_sentinel_geotiff",
]