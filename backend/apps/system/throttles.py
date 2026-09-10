"""Scoped DRF throttles for expensive SatQuery-X operations."""
from rest_framework.throttling import UserRateThrottle


class AnalysisRateThrottle(UserRateThrottle):
    scope = "analysis"


class SatelliteSearchRateThrottle(UserRateThrottle):
    scope = "satellite_search"


class SatelliteAcquisitionRateThrottle(UserRateThrottle):
    scope = "satellite_acquisition"


class ImageryUploadRateThrottle(UserRateThrottle):
    scope = "imagery_upload"
