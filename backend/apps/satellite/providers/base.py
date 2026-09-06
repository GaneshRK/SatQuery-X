"""
SatQuery-X satellite-provider abstraction layer.

This module defines the common contract used by real Earth-observation
catalogue providers.

Design principles
-----------------
- Provider metadata must come from the provider.
- Missing scientific metadata remains None.
- No fabricated CRS, resolution, cloud percentage, footprint, dates,
  confidence, or imagery.
- Provider implementations may support catalogue search, metadata retrieval,
  asset download, and health checks.
- The provider layer does not perform remote-sensing analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence


# =============================================================================
# DATA TRANSFER OBJECTS
# =============================================================================


@dataclass(slots=True)
class SatelliteCandidateDTO:
    """
    Provider-neutral representation of one satellite catalogue item.

    Every field describing the satellite acquisition should originate from
    the provider response.

    Optional scientific metadata is intentionally represented as None when
    the provider does not supply it.
    """

    stac_item_id: str
    collection: str
    sensor: str

    acquisition_date: str | None = None

    cloud_cover_pct: float | None = None

    footprint_geom: dict[str, Any] | None = None

    thumbnail_url: str | None = None

    assets_summary: dict[str, Any] = field(
        default_factory=dict
    )

    provider: str | None = None

    # This flag exists only to identify explicitly configured test/mock data.
    # Production provider implementations must return False.
    is_synthetic: bool = False

    # Additional provider-native metadata that SatQuery-X does not need to
    # interpret itself.
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.stac_item_id = str(
            self.stac_item_id or ""
        ).strip()

        self.collection = str(
            self.collection or ""
        ).strip()

        self.sensor = str(
            self.sensor or ""
        ).strip()

        if not self.stac_item_id:
            raise ValueError(
                "SatelliteCandidateDTO requires stac_item_id."
            )

        if not self.collection:
            raise ValueError(
                "SatelliteCandidateDTO requires collection."
            )

        if not self.sensor:
            raise ValueError(
                "SatelliteCandidateDTO requires sensor."
            )

        if self.cloud_cover_pct is not None:
            try:
                self.cloud_cover_pct = float(
                    self.cloud_cover_pct
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "cloud_cover_pct must be numeric or None."
                ) from exc

            if not 0 <= self.cloud_cover_pct <= 100:
                raise ValueError(
                    "cloud_cover_pct must be between 0 and 100."
                )

        if self.footprint_geom is not None:
            if not isinstance(
                self.footprint_geom,
                Mapping,
            ):
                raise ValueError(
                    "footprint_geom must be a GeoJSON mapping or None."
                )

            self.footprint_geom = dict(
                self.footprint_geom
            )

        if not isinstance(
            self.assets_summary,
            Mapping,
        ):
            raise ValueError(
                "assets_summary must be a mapping."
            )

        self.assets_summary = dict(
            self.assets_summary
        )

        if not isinstance(
            self.metadata,
            Mapping,
        ):
            raise ValueError(
                "metadata must be a mapping."
            )

        self.metadata = dict(
            self.metadata
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the DTO to a JSON-friendly provider-neutral dictionary.
        """

        return {
            "stac_item_id": self.stac_item_id,
            "collection": self.collection,
            "sensor": self.sensor,
            "acquisition_date": self.acquisition_date,
            "cloud_cover_pct": self.cloud_cover_pct,
            "footprint_geom": self.footprint_geom,
            "thumbnail_url": self.thumbnail_url,
            "assets_summary": dict(
                self.assets_summary
            ),
            "provider": self.provider,
            "is_synthetic": self.is_synthetic,
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass(slots=True)
class SatelliteAssetDTO:
    """
    Provider-neutral description of one scene asset.

    `href` may point to a provider-hosted remote object. The provider layer
    does not assume that the asset is locally downloaded.
    """

    asset_key: str
    href: str

    asset_type: str | None = None

    title: str | None = None

    description: str | None = None

    roles: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    is_downloadable: bool | None = None

    def __post_init__(self) -> None:
        self.asset_key = str(
            self.asset_key or ""
        ).strip()

        self.href = str(
            self.href or ""
        ).strip()

        if not self.asset_key:
            raise ValueError(
                "SatelliteAssetDTO requires asset_key."
            )

        if not self.href:
            raise ValueError(
                "SatelliteAssetDTO requires href."
            )

        if not isinstance(
            self.roles,
            list,
        ):
            self.roles = list(
                self.roles or []
            )

        if not isinstance(
            self.metadata,
            Mapping,
        ):
            raise ValueError(
                "SatelliteAssetDTO.metadata must be a mapping."
            )

        self.metadata = dict(
            self.metadata
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_key": self.asset_key,
            "href": self.href,
            "type": self.asset_type,
            "title": self.title,
            "description": self.description,
            "roles": list(
                self.roles
            ),
            "metadata": dict(
                self.metadata
            ),
            "is_downloadable": self.is_downloadable,
        }


@dataclass(slots=True)
class SatelliteSceneMetadataDTO:
    """
    Detailed metadata returned for an individual scene.

    Scientific fields remain optional because not every provider exposes the
    same information.
    """

    stac_item_id: str

    provider: str | None = None

    collection: str | None = None

    sensor: str | None = None

    platform: str | None = None

    mission: str | None = None

    instrument: str | None = None

    acquisition_datetime: str | None = None

    processing_level: str | None = None

    cloud_cover_pct: float | None = None

    geometry: dict[str, Any] | None = None

    bbox: list[float] | None = None

    crs: str | None = None

    resolution_m: float | None = None

    modality: str | None = None

    assets: dict[str, SatelliteAssetDTO] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stac_item_id": self.stac_item_id,
            "provider": self.provider,
            "collection": self.collection,
            "sensor": self.sensor,
            "platform": self.platform,
            "mission": self.mission,
            "instrument": self.instrument,
            "acquisition_datetime": self.acquisition_datetime,
            "processing_level": self.processing_level,
            "cloud_cover_pct": self.cloud_cover_pct,
            "geometry": self.geometry,
            "bbox": self.bbox,
            "crs": self.crs,
            "resolution_m": self.resolution_m,
            "modality": self.modality,
            "assets": {
                key: value.to_dict()
                for key, value in self.assets.items()
            },
            "metadata": dict(
                self.metadata
            ),
        }


# =============================================================================
# PROVIDER EXCEPTIONS
# =============================================================================


class SatelliteProviderError(
    RuntimeError
):
    """
    Base exception for satellite-provider failures.
    """


class SatelliteProviderConfigurationError(
    SatelliteProviderError
):
    """
    Provider is not configured correctly.
    """


class SatelliteProviderAuthenticationError(
    SatelliteProviderError
):
    """
    Provider authentication/token acquisition failed.
    """


class SatelliteProviderRequestError(
    SatelliteProviderError
):
    """
    Provider API/STAC request failed.
    """


class SatelliteProviderResponseError(
    SatelliteProviderError
):
    """
    Provider returned malformed or unsupported data.
    """


class SatelliteAssetDownloadError(
    SatelliteProviderError
):
    """
    A provider asset could not be downloaded.
    """


# =============================================================================
# PROVIDER INTERFACE
# =============================================================================


class SatelliteProvider(
    ABC
):
    """
    Abstract interface for Earth-observation data providers.

    Concrete implementations include providers such as Copernicus Data Space
    and other configured STAC-compatible services.

    The provider is responsible for:
        - communicating with the external catalogue;
        - authenticating when necessary;
        - returning actual provider metadata;
        - returning actual asset URLs;
        - optionally downloading provider assets.

    The provider is NOT responsible for:
        - generating synthetic satellite images;
        - calculating NDVI/change masks;
        - inventing coordinates;
        - inventing cloud cover;
        - inventing spatial resolution;
        - classifying land cover;
        - generating model confidence.
    """

    # Human-readable provider name.
    name: str = "Unnamed Satellite Provider"

    # Stable provider identifier used in persistence/provenance.
    slug: str = "unknown"

    # Optional provider website/API endpoint.
    base_url: str | None = None

    # -------------------------------------------------------------------------
    # Catalogue search
    # -------------------------------------------------------------------------

    @abstractmethod
    def search_scenes(
        self,
        aoi_geometry: dict[str, Any] | None,
        date_start: str | date | datetime,
        date_end: str | date | datetime,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float | None = None,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        """
        Search the provider's catalogue.

        Parameters
        ----------
        aoi_geometry:
            Actual GeoJSON geometry supplied by the user/application.
            None means no spatial filter.

        date_start/date_end:
            Requested acquisition date range.

        sensor:
            Requested mission/sensor identifier.

        max_cloud_cover:
            Optional provider-supported cloud filter.
            None means do not impose an artificial cloud threshold.

        limit:
            Maximum number of provider records requested.

        Returns
        -------
        list[SatelliteCandidateDTO]
            Actual provider catalogue records.

        Raises
        ------
        SatelliteProviderError
            When the provider cannot perform the search.
        """

        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Scene metadata
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_scene_metadata(
        self,
        stac_item_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve detailed metadata for one real provider scene.

        The returned dictionary should preserve provider-derived values such
        as CRS, resolution, platform, acquisition time, geometry and assets.
        """

        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Asset discovery
    # -------------------------------------------------------------------------

    def get_scene_assets(
        self,
        stac_item_id: str,
    ) -> dict[str, SatelliteAssetDTO]:
        """
        Retrieve downloadable/visual assets for a scene.

        Providers that already return complete asset information from
        `get_scene_metadata()` can use the default implementation.
        """

        metadata = self.get_scene_metadata(
            stac_item_id
        )

        raw_assets = (
            metadata.get(
                "assets"
            )
            if isinstance(
                metadata,
                Mapping,
            )
            else None
        )

        if not isinstance(
            raw_assets,
            Mapping,
        ):
            return {}

        result: dict[
            str,
            SatelliteAssetDTO,
        ] = {}

        for asset_key, raw in raw_assets.items():
            if not isinstance(
                raw,
                Mapping,
            ):
                continue

            href = raw.get(
                "href"
            )

            if not href:
                continue

            try:
                result[
                    str(asset_key)
                ] = SatelliteAssetDTO(
                    asset_key=str(
                        asset_key
                    ),
                    href=str(
                        href
                    ),
                    asset_type=(
                        raw.get(
                            "type"
                        )
                    ),
                    title=(
                        raw.get(
                            "title"
                        )
                    ),
                    description=(
                        raw.get(
                            "description"
                        )
                    ),
                    roles=list(
                        raw.get(
                            "roles"
                        )
                        or []
                    ),
                    metadata=dict(
                        raw.get(
                            "metadata"
                        )
                        or {}
                    ),
                    is_downloadable=(
                        raw.get(
                            "is_downloadable"
                        )
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):
                logger.warning(
                    "Ignoring malformed provider asset '%s'.",
                    asset_key,
                )

        return result

    # -------------------------------------------------------------------------
    # Asset download
    # -------------------------------------------------------------------------

    def download_asset(
        self,
        href: str,
        destination: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> str:
        """
        Download a provider asset.

        Concrete providers should override this method when authentication,
        signed URLs, cloud-object storage, or provider-specific transport is
        required.

        The base implementation deliberately raises instead of silently
        pretending an asset was downloaded.
        """

        raise SatelliteAssetDownloadError(
            (
                f"Provider '{self.name}' does not implement "
                "asset downloading."
            )
        )

    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return provider health information.

        Providers may override this with a lightweight endpoint check.
        """

        return {
            "provider": self.slug,
            "name": self.name,
            "status": "unknown",
            "detail": (
                "Provider does not expose a health-check implementation."
            ),
        }

    # -------------------------------------------------------------------------
    # Capabilities
    # -------------------------------------------------------------------------

    def capabilities(
        self,
    ) -> dict[str, Any]:
        """
        Describe provider capabilities.

        Concrete implementations should override this when they can expose
        accurate provider capability information.
        """

        return {
            "provider": self.slug,
            "name": self.name,
            "catalogue_search": True,
            "scene_metadata": True,
            "asset_discovery": True,
            "asset_download": False,
            "health_check": False,
        }


# =============================================================================
# NORMALIZATION HELPERS
# =============================================================================


def normalize_candidate(
    candidate: SatelliteCandidateDTO
    | Mapping[str, Any],
) -> SatelliteCandidateDTO:
    """
    Convert a provider result into SatelliteCandidateDTO.

    This helper performs structural normalization only.

    It never fills missing scientific values with defaults.
    """

    if isinstance(
        candidate,
        SatelliteCandidateDTO,
    ):
        return candidate

    if not isinstance(
        candidate,
        Mapping,
    ):
        raise SatelliteProviderResponseError(
            "Provider candidate must be a mapping or SatelliteCandidateDTO."
        )

    item_id = (
        candidate.get(
            "stac_item_id"
        )
        or candidate.get(
            "id"
        )
        or candidate.get(
            "external_id"
        )
    )

    collection = (
        candidate.get(
            "collection"
        )
        or candidate.get(
            "collection_id"
        )
    )

    sensor = (
        candidate.get(
            "sensor"
        )
        or candidate.get(
            "platform"
        )
        or candidate.get(
            "mission"
        )
    )

    if not item_id:
        raise SatelliteProviderResponseError(
            "Provider candidate does not contain a scene identifier."
        )

    if not collection:
        raise SatelliteProviderResponseError(
            "Provider candidate does not contain a collection."
        )

    if not sensor:
        raise SatelliteProviderResponseError(
            "Provider candidate does not contain a sensor."
        )

    acquisition_date = (
        candidate.get(
            "acquisition_date"
        )
        or candidate.get(
            "datetime"
        )
        or candidate.get(
            "acquisition_datetime"
        )
    )

    cloud_cover = (
        candidate.get(
            "cloud_cover_pct"
        )
        if "cloud_cover_pct" in candidate
        else candidate.get(
            "cloud_cover"
        )
    )

    footprint = (
        candidate.get(
            "footprint_geom"
        )
        or candidate.get(
            "geometry"
        )
    )

    thumbnail = (
        candidate.get(
            "thumbnail_url"
        )
        or candidate.get(
            "thumbnail"
        )
    )

    assets = (
        candidate.get(
            "assets_summary"
        )
        or candidate.get(
            "assets"
        )
        or {}
    )

    metadata = dict(
        candidate.get(
            "metadata"
        )
        or {}
    )

    return SatelliteCandidateDTO(
        stac_item_id=str(
            item_id
        ),
        collection=str(
            collection
        ),
        sensor=str(
            sensor
        ),
        acquisition_date=(
            str(
                acquisition_date
            )
            if acquisition_date is not None
            else None
        ),
        cloud_cover_pct=cloud_cover,
        footprint_geom=(
            dict(
                footprint
            )
            if isinstance(
                footprint,
                Mapping,
            )
            else None
        ),
        thumbnail_url=(
            str(
                thumbnail
            )
            if thumbnail
            else None
        ),
        assets_summary=(
            dict(
                assets
            )
            if isinstance(
                assets,
                Mapping,
            )
            else {}
        ),
        provider=(
            str(
                candidate.get(
                    "provider"
                )
            )
            if candidate.get(
                "provider"
            )
            else None
        ),
        is_synthetic=bool(
            candidate.get(
                "is_synthetic",
                False,
            )
        ),
        metadata=metadata,
    )


def normalize_candidates(
    candidates: Sequence[
        SatelliteCandidateDTO
        | Mapping[str, Any]
    ]
    | None,
) -> list[SatelliteCandidateDTO]:
    """
    Normalize a provider search response.

    Invalid provider records are rejected rather than silently converted into
    fabricated catalogue records.
    """

    if candidates is None:
        return []

    if isinstance(
        candidates,
        Mapping,
    ):
        raw_items = (
            candidates.get(
                "features"
            )
            or candidates.get(
                "results"
            )
            or candidates.get(
                "scenes"
            )
            or []
        )
    else:
        raw_items = candidates

    if isinstance(
        raw_items,
        (
            str,
            bytes,
        ),
    ):
        raise SatelliteProviderResponseError(
            "Provider returned an invalid scene collection."
        )

    normalized: list[
        SatelliteCandidateDTO
    ] = []

    for candidate in raw_items:
        normalized.append(
            normalize_candidate(
                candidate
            )
        )

    return normalized


# =============================================================================
# LOGGING
# =============================================================================


logger = __import__(
    "logging"
).getLogger(
    __name__
)


__all__ = [
    "SatelliteCandidateDTO",
    "SatelliteAssetDTO",
    "SatelliteSceneMetadataDTO",
    "SatelliteProvider",
    "SatelliteProviderError",
    "SatelliteProviderConfigurationError",
    "SatelliteProviderAuthenticationError",
    "SatelliteProviderRequestError",
    "SatelliteProviderResponseError",
    "SatelliteAssetDownloadError",
    "normalize_candidate",
    "normalize_candidates",
]