"""
SatQuery-X satellite provider package.

This package exposes the provider-neutral satellite interface and the
real Copernicus Data Space Ecosystem implementation.

Provider implementations must return real catalogue/provider data.
Synthetic or fabricated satellite observations are not supported.
"""

from __future__ import annotations

from .base import (
    SatelliteAssetDTO,
    SatelliteCandidateDTO,
    SatelliteProvider,
    SatelliteProviderAuthenticationError,
    SatelliteProviderConfigurationError,
    SatelliteProviderError,
    SatelliteProviderRequestError,
    SatelliteProviderResponseError,
    SatelliteAssetDownloadError,
    SatelliteSceneMetadataDTO,
    normalize_candidate,
    normalize_candidates,
)

from .copernicus import CopernicusProvider
from .auth import CDSETokenManager


def get_satellite_provider(
    provider_name: str | None = None,
) -> SatelliteProvider:
    """
    Return the configured real satellite provider.

    Currently supported:
        copernicus
        copernicus_cdse
        cdse
        cds

    No mock provider is returned when configuration is missing.
    """

    name = str(
        provider_name or "copernicus"
    ).strip().lower()

    aliases = {
        "copernicus": "copernicus",
        "copernicus_cdse": "copernicus",
        "cdse": "copernicus",
        "cds": "copernicus",
    }

    normalized = aliases.get(name)

    if normalized == "copernicus":
        return CopernicusProvider(
            token_manager=CDSETokenManager()
        )

    raise ValueError(
        f"Unsupported satellite provider: "
        f"{provider_name!r}. "
        f"Supported providers: copernicus."
    )


__all__ = [
    # Provider interface
    "SatelliteProvider",
    "SatelliteCandidateDTO",
    "SatelliteAssetDTO",
    "SatelliteSceneMetadataDTO",

    # Provider exceptions
    "SatelliteProviderError",
    "SatelliteProviderConfigurationError",
    "SatelliteProviderAuthenticationError",
    "SatelliteProviderRequestError",
    "SatelliteProviderResponseError",
    "SatelliteAssetDownloadError",

    # Normalization helpers
    "normalize_candidate",
    "normalize_candidates",

    # CDSE implementation
    "CopernicusProvider",
    "CDSETokenManager",

    # Provider factory
    "get_satellite_provider",
]