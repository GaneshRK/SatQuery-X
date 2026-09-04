from __future__ import annotations
import os
from .base import SatelliteCandidateDTO, SatelliteProvider
from .copernicus import CopernicusProvider
from .mock import MockSatelliteProvider


def get_satellite_provider(force_mock: bool = False) -> SatelliteProvider:
    if force_mock or os.getenv("SATQUERY_MOCK_SATELLITE", "False").lower() in ("true", "1"):
        return MockSatelliteProvider()
    return CopernicusProvider()
