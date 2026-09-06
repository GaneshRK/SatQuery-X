"""
Sensor and band metadata for remote-sensing processing.

Design principles
-----------------
1. Sensor metadata is used only when it is actually known.
2. Unknown imagery is never silently treated as Sentinel-2.
3. Spectral indices require verified semantic band mappings.
4. No fabricated CRS, resolution, wavelength, or geotransform is created.
5. SAR is handled separately from optical/multispectral imagery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    from scipy import ndimage

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass(frozen=True)
class BandInfo:
    band_id: str
    name: str
    center_wavelength_um: float | None
    bandwidth_um: float | None
    typical_resolution_m: float | None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SensorProfile:
    sensor_id: str
    name: str
    modality: str
    bands: tuple[BandInfo, ...]
    native_crs_typical: str | None = None
    typical_resolution_m: float | None = None
    band_aliases: dict[str, str] = field(default_factory=dict)
    preprocessing_notes: str = ""

    def get_band_index(
        self,
        target_alias: str,
        total_bands: int,
    ) -> int | None:
        """
        Resolve a semantic band to a zero-based raster band index.

        A mapping is returned only when it can be verified against the
        profile and available band count.
        """
        if total_bands <= 0:
            return None

        alias = target_alias.strip().lower()

        matched_band_id = self.band_aliases.get(alias)

        if matched_band_id is None:
            for band in self.bands:
                aliases = {a.lower() for a in band.aliases}

                if (
                    alias == band.band_id.lower()
                    or alias == band.name.lower()
                    or alias in aliases
                ):
                    matched_band_id = band.band_id
                    break

        if matched_band_id is None:
            return None

        for index, band in enumerate(self.bands):
            if band.band_id == matched_band_id:
                if index < total_bands:
                    return index
                return None

        return None

    def supports_band(
        self,
        target_alias: str,
        total_bands: int,
    ) -> bool:
        return self.get_band_index(target_alias, total_bands) is not None


# ---------------------------------------------------------------------------
# Sentinel-2 MSI
# ---------------------------------------------------------------------------

SENTINEL_2_PROFILE = SensorProfile(
    sensor_id="SENTINEL-2",
    name="Copernicus Sentinel-2 MSI",
    modality="MULTISPECTRAL",
    bands=(
        BandInfo("B01", "Coastal Aerosol", 0.443, 0.020, 60.0, ("coastal", "aerosol")),
        BandInfo("B02", "Blue", 0.490, 0.065, 10.0, ("blue", "b")),
        BandInfo("B03", "Green", 0.560, 0.035, 10.0, ("green", "g")),
        BandInfo("B04", "Red", 0.665, 0.030, 10.0, ("red", "r")),
        BandInfo("B05", "Vegetation Red Edge 1", 0.705, 0.015, 20.0, ("rededge1", "vre1")),
        BandInfo("B06", "Vegetation Red Edge 2", 0.740, 0.015, 20.0, ("rededge2", "vre2")),
        BandInfo("B07", "Vegetation Red Edge 3", 0.783, 0.020, 20.0, ("rededge3", "vre3")),
        BandInfo("B08", "NIR", 0.842, 0.115, 10.0, ("nir", "nir1")),
        BandInfo("B8A", "Narrow NIR", 0.865, 0.020, 20.0, ("nir2", "nnir")),
        BandInfo("B09", "Water Vapour", 0.945, 0.020, 60.0, ("water_vapour",)),
        BandInfo("B10", "Cirrus", 1.375, 0.030, 60.0, ("cirrus",)),
        BandInfo("B11", "SWIR 1", 1.610, 0.090, 20.0, ("swir", "swir1")),
        BandInfo("B12", "SWIR 2", 2.190, 0.180, 20.0, ("swir2",)),
    ),
    native_crs_typical="UTM",
    typical_resolution_m=10.0,
    band_aliases={
        "blue": "B02",
        "green": "B03",
        "red": "B04",
        "nir": "B08",
        "swir": "B11",
        "swir1": "B11",
        "swir2": "B12",
    },
    preprocessing_notes=(
        "Sentinel-2 products may contain scaled reflectance values. "
        "Use product metadata to determine the actual scale/offset."
    ),
)


# ---------------------------------------------------------------------------
# Landsat 8/9 OLI
# ---------------------------------------------------------------------------

LANDSAT_OLI_PROFILE = SensorProfile(
    sensor_id="LANDSAT-OLI",
    name="Landsat 8/9 Operational Land Imager",
    modality="MULTISPECTRAL",
    bands=(
        BandInfo("B1", "Coastal Aerosol", 0.443, 0.016, 30.0, ("coastal",)),
        BandInfo("B2", "Blue", 0.482, 0.060, 30.0, ("blue", "b")),
        BandInfo("B3", "Green", 0.561, 0.057, 30.0, ("green", "g")),
        BandInfo("B4", "Red", 0.655, 0.037, 30.0, ("red", "r")),
        BandInfo("B5", "NIR", 0.865, 0.028, 30.0, ("nir",)),
        BandInfo("B6", "SWIR 1", 1.609, 0.085, 30.0, ("swir", "swir1")),
        BandInfo("B7", "SWIR 2", 2.201, 0.187, 30.0, ("swir2",)),
        BandInfo("B8", "Panchromatic", 0.590, 0.180, 15.0, ("pan",)),
    ),
    native_crs_typical="UTM",
    typical_resolution_m=30.0,
    band_aliases={
        "blue": "B2",
        "green": "B3",
        "red": "B4",
        "nir": "B5",
        "swir": "B6",
        "swir1": "B6",
        "swir2": "B7",
    },
)


# ---------------------------------------------------------------------------
# Cartosat
# ---------------------------------------------------------------------------

CARTOSAT_PROFILE = SensorProfile(
    sensor_id="CARTOSAT-2S",
    name="ISRO Cartosat-2 Series",
    modality="OPTICAL",
    bands=(
        BandInfo("PAN", "Panchromatic", None, None, 0.65, ("pan",)),
        BandInfo("B1", "Blue", None, None, 1.6, ("blue", "b")),
        BandInfo("B2", "Green", None, None, 1.6, ("green", "g")),
        BandInfo("B3", "Red", None, None, 1.6, ("red", "r")),
        BandInfo("B4", "NIR", None, None, 1.6, ("nir",)),
    ),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={
        "blue": "B1",
        "green": "B2",
        "red": "B3",
        "nir": "B4",
    },
)


# ---------------------------------------------------------------------------
# RISAT
# ---------------------------------------------------------------------------

RISAT_PROFILE = SensorProfile(
    sensor_id="RISAT",
    name="RISAT Radar Imaging Satellite",
    modality="SAR",
    bands=(
        BandInfo("HH", "HH Polarization", None, None, None, ("hh",)),
        BandInfo("HV", "HV Polarization", None, None, None, ("hv",)),
    ),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={
        "primary": "HH",
        "hh": "HH",
        "crosspol": "HV",
        "hv": "HV",
    },
    preprocessing_notes=(
        "SAR preprocessing depends on acquisition product level, "
        "calibration, incidence angle, polarization, and units."
    ),
)


# ---------------------------------------------------------------------------
# Sentinel-1
# ---------------------------------------------------------------------------

SENTINEL_1_PROFILE = SensorProfile(
    sensor_id="SENTINEL-1",
    name="Copernicus Sentinel-1 C-SAR",
    modality="SAR",
    bands=(
        BandInfo("VV", "VV Polarization", None, None, None, ("vv",)),
        BandInfo("VH", "VH Polarization", None, None, None, ("vh",)),
    ),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={
        "primary": "VV",
        "vv": "VV",
        "crosspol": "VH",
        "vh": "VH",
    },
    preprocessing_notes=(
        "SAR processing must respect product metadata, calibration state, "
        "polarization and acquisition geometry."
    ),
)


# ---------------------------------------------------------------------------
# Unknown / generic profiles
# ---------------------------------------------------------------------------

GENERIC_OPTICAL_PROFILE = SensorProfile(
    sensor_id="GENERIC-OPTICAL",
    name="Generic Optical Raster",
    modality="OPTICAL",
    bands=(),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={},
)


GENERIC_MULTISPECTRAL_PROFILE = SensorProfile(
    sensor_id="GENERIC-MULTISPECTRAL",
    name="Generic Multispectral Raster",
    modality="MULTISPECTRAL",
    bands=(),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={},
)


GENERIC_SAR_PROFILE = SensorProfile(
    sensor_id="GENERIC-SAR",
    name="Generic SAR Raster",
    modality="SAR",
    bands=(),
    native_crs_typical=None,
    typical_resolution_m=None,
    band_aliases={},
)


SENSOR_REGISTRY: dict[str, SensorProfile] = {
    "SENTINEL-2": SENTINEL_2_PROFILE,
    "LANDSAT-OLI": LANDSAT_OLI_PROFILE,
    "LANDSAT-8": LANDSAT_OLI_PROFILE,
    "LANDSAT-9": LANDSAT_OLI_PROFILE,
    "LANDSAT": LANDSAT_OLI_PROFILE,
    "CARTOSAT-2S": CARTOSAT_PROFILE,
    "RISAT": RISAT_PROFILE,
    "SENTINEL-1": SENTINEL_1_PROFILE,
    "GENERIC-OPTICAL": GENERIC_OPTICAL_PROFILE,
    "GENERIC-MULTISPECTRAL": GENERIC_MULTISPECTRAL_PROFILE,
    "GENERIC-SAR": GENERIC_SAR_PROFILE,
}


def get_sensor_profile(
    sensor_name: str | None,
    modality: str = "OPTICAL",
) -> SensorProfile:
    """
    Resolve a known sensor.

    Unknown sensor names never get mapped to a real satellite profile.
    """

    if sensor_name:
        normalized = sensor_name.strip().upper()

        if normalized in SENSOR_REGISTRY:
            return SENSOR_REGISTRY[normalized]

        for key, profile in SENSOR_REGISTRY.items():
            if normalized == key:
                return profile

    modality_upper = modality.strip().upper()

    if modality_upper == "SAR":
        return GENERIC_SAR_PROFILE

    if modality_upper in {"MULTISPECTRAL", "MULTI_SPECTRAL"}:
        return GENERIC_MULTISPECTRAL_PROFILE

    return GENERIC_OPTICAL_PROFILE


def _safe_percentile(
    values: np.ndarray,
    percentile: float,
) -> float:
    valid = values[np.isfinite(values)]

    if valid.size == 0:
        return 0.0

    return float(np.percentile(valid, percentile))


def preprocess_optical_raster(
    raster: np.ndarray,
    profile: SensorProfile | None = None,
    percentile_clip: tuple[float, float] | None = None,
    scale_factor: float | None = None,
    offset: float = 0.0,
) -> np.ndarray:
    """
    Normalize optical data when the caller knows the product scale.

    IMPORTANT:
    If scale_factor is not supplied, no arbitrary satellite DN scale is
    assumed. Values are only converted to float and finite values are
    preserved.

    percentile_clip is optional. It should be used for visualization,
    not for scientific measurements, unless explicitly requested.
    """

    arr = np.asarray(raster, dtype=np.float32).copy()

    if arr.size == 0:
        return arr

    arr = np.nan_to_num(
        arr,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    if scale_factor is not None:
        if scale_factor == 0:
            raise ValueError("scale_factor must not be zero.")

        arr = arr * float(scale_factor) + float(offset)

    if percentile_clip is not None:
        low, high = percentile_clip

        if not 0 <= low < high <= 100:
            raise ValueError(
                "percentile_clip must satisfy 0 <= low < high <= 100."
            )

        valid = arr[np.isfinite(arr)]

        if valid.size:
            p_low = np.percentile(valid, low)
            p_high = np.percentile(valid, high)

            if p_high > p_low:
                arr = np.clip(
                    (arr - p_low) / (p_high - p_low),
                    0.0,
                    1.0,
                )

    return arr


def preprocess_sar_raster(
    raster: np.ndarray,
    speckle_filter_size: int = 3,
    apply_log_transform: bool = False,
    normalize: bool = False,
) -> np.ndarray:
    """
    Conservative SAR preprocessing.

    By default:
    - converts to float32
    - removes NaN/Inf
    - does NOT invent a dB conversion
    - does NOT normalize physical backscatter

    If apply_log_transform=True, the caller must know that the input is
    linear power/intensity.
    """

    arr = np.asarray(raster, dtype=np.float32).copy()

    arr = np.nan_to_num(
        arr,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    if speckle_filter_size < 1:
        raise ValueError("speckle_filter_size must be >= 1.")

    if speckle_filter_size % 2 == 0:
        raise ValueError("speckle_filter_size must be odd.")

    if speckle_filter_size > 1:
        if not HAS_SCIPY:
            raise RuntimeError(
                "scipy is required for SAR speckle filtering."
            )

        if arr.ndim == 2:
            arr = ndimage.median_filter(
                arr,
                size=speckle_filter_size,
            )

        elif arr.ndim == 3:
            for band in range(arr.shape[0]):
                arr[band] = ndimage.median_filter(
                    arr[band],
                    size=speckle_filter_size,
                )

        else:
            raise ValueError(
                "SAR raster must be 2D or 3D."
            )

    if apply_log_transform:
        if np.any(arr < 0):
            raise ValueError(
                "Linear SAR power/intensity cannot contain negative values."
            )

        arr = 10.0 * np.log10(
            np.maximum(arr, np.finfo(np.float32).eps)
        )

    if normalize:
        valid = arr[np.isfinite(arr)]

        if valid.size:
            low, high = np.percentile(valid, (2.0, 98.0))

            if high > low:
                arr = (arr - low) / (high - low)

    return arr.astype(np.float32)