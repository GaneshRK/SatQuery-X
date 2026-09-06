from __future__ import annotations
import os
from .base import SatelliteCandidateDTO, SatelliteProvider
from .copernicus import CopernicusProvider
from .mock import MockSatelliteProvider


def get_satellite_provider(force_mock: bool | None = None) -> SatelliteProvider:
    if force_mock is True:
        return MockSatelliteProvider()
    if force_mock is False:
        return CopernicusProvider()
    if os.getenv("SATQUERY_MOCK_SATELLITE", "False").lower() in ("true", "1"):
        return MockSatelliteProvider()
    return CopernicusProvider()
