"""Sensor Profile System per §23, §24, §25, §26.

Defines sensor profiles for Sentinel-2, Landsat, Cartosat-2S, RISAT-1,
Generic Optical, and Generic SAR imagery, including wavelengths, resolution,
band aliases, and sensor-specific preprocessing (SAR backscatter/speckle filtering,
optical band reflectance normalization).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class BandInfo:
    band_id: str
    name: str
    center_wavelength_um: float
    bandwidth_um: float
    typical_resolution_m: float
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SensorProfile:
    sensor_id: str
    name: str
    modality: str  # "OPTICAL", "MULTISPECTRAL", "SAR"
    bands: tuple[BandInfo, ...]
    native_crs_typical: str
    typical_resolution_m: float
    band_aliases: dict[str, str] = field(default_factory=dict)
    preprocessing_notes: str = ""

    def get_band_index(self, target_alias: str, total_bands: int) -> int | None:
        """
        Resolves band index (0-based) given a semantic alias like 'red', 'green', 'blue', 'nir', 'swir'.
        Never assumes default band indices without verifying against profile band count.
        """
        alias_lower = target_alias.lower().strip()
        matched_band_id = self.band_aliases.get(alias_lower)
        if not matched_band_id:
            for b in self.bands:
                if alias_lower == b.name.lower() or alias_lower in [a.lower() for a in b.aliases]:
                    matched_band_id = b.band_id
                    break

        if matched_band_id:
            for idx, b in enumerate(self.bands):
                if b.band_id == matched_band_id:
                    return idx if idx < total_bands else None

        # Safe optical fallback for standard RGB
        if total_bands >= 3 and alias_lower in ("red", "r"):
            return 0
        if total_bands >= 3 and alias_lower in ("green", "g"):
            return 1
        if total_bands >= 3 and alias_lower in ("blue", "b"):
            return 2
        return None


# 1. Sentinel-2 MSI Profile (13 Spectral Bands)
SENTINEL_2_PROFILE = SensorProfile(
    sensor_id="SENTINEL-2",
    name="Copernicus Sentinel-2 Multi-Spectral Instrument (MSI)",
    modality="MULTISPECTRAL",
    bands=(
        BandInfo("B01", "Coastal aerosol", 0.443, 0.020, 60.0, ("coastal", "aerosol")),
        BandInfo("B02", "Blue", 0.490, 0.065, 10.0, ("blue", "b")),
        BandInfo("B03", "Green", 0.560, 0.035, 10.0, ("green", "g")),
        BandInfo("B04", "Red", 0.665, 0.030, 10.0, ("red", "r")),
        BandInfo("B05", "Vegetation Red Edge 1", 0.705, 0.015, 20.0, ("vre1", "rededge1")),
        BandInfo("B06", "Vegetation Red Edge 2", 0.740, 0.015, 20.0, ("vre2", "rededge2")),
        BandInfo("B07", "Vegetation Red Edge 3", 0.783, 0.020, 20.0, ("vre3", "rededge3")),
        BandInfo("B08", "Near Infrared (NIR)", 0.842, 0.115, 10.0, ("nir", "nir1")),
        BandInfo("B8A", "Narrow NIR", 0.865, 0.020, 20.0, ("nnir", "nir2")),
        BandInfo("B09", "Water vapour", 0.945, 0.020, 60.0, ("watervapour",)),
        BandInfo("B10", "SWIR - Cirrus", 1.375, 0.030, 60.0, ("cirrus",)),
        BandInfo("B11", "SWIR 1", 1.610, 0.090, 20.0, ("swir1", "swir")),
        BandInfo("B12", "SWIR 2", 2.190, 0.180, 20.0, ("swir2",)),
    ),
    native_crs_typical="UTM WGS84",
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
    preprocessing_notes="Digital numbers (DN) scale by 1/10000 for top-of-atmosphere/surface reflectance.",
)

# 2. Landsat 8/9 OLI Profile
LANDSAT_OLI_PROFILE = SensorProfile(
    sensor_id="LANDSAT-OLI",
    name="Landsat 8/9 Operational Land Imager (OLI)",
    modality="MULTISPECTRAL",
    bands=(
        BandInfo("B1", "Coastal aerosol", 0.443, 0.016, 30.0, ("coastal",)),
        BandInfo("B2", "Blue", 0.482, 0.060, 30.0, ("blue", "b")),
        BandInfo("B3", "Green", 0.561, 0.057, 30.0, ("green", "g")),
        BandInfo("B4", "Red", 0.655, 0.037, 30.0, ("red", "r")),
        BandInfo("B5", "Near Infrared", 0.865, 0.028, 30.0, ("nir",)),
        BandInfo("B6", "SWIR 1", 1.609, 0.085, 30.0, ("swir1", "swir")),
        BandInfo("B7", "SWIR 2", 2.201, 0.187, 30.0, ("swir2",)),
        BandInfo("B8", "Panchromatic", 0.590, 0.180, 15.0, ("pan",)),
    ),
    native_crs_typical="UTM WGS84",
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

# 3. Cartosat-2S Profile (High-Resolution ISRO Optical)
CARTOSAT_PROFILE = SensorProfile(
    sensor_id="CARTOSAT-2S",
    name="ISRO Cartosat-2 Series Panchromatic & Multispectral",
    modality="OPTICAL",
    bands=(
        BandInfo("PAN", "Panchromatic", 0.650, 0.350, 0.65, ("pan",)),
        BandInfo("B1", "Blue", 0.485, 0.060, 1.6, ("blue", "b")),
        BandInfo("B2", "Green", 0.560, 0.060, 1.6, ("green", "g")),
        BandInfo("B3", "Red", 0.660, 0.060, 1.6, ("red", "r")),
        BandInfo("B4", "NIR", 0.825, 0.100, 1.6, ("nir",)),
    ),
    native_crs_typical="UTM WGS84",
    typical_resolution_m=0.65,
    band_aliases={"blue": "B1", "green": "B2", "red": "B3", "nir": "B4"},
    preprocessing_notes="Panchromatic sub-meter resolution; multispectral 1.6m.",
)

# 4. RISAT-1 / 1A (ISRO SAR Radar Profile)
RISAT_PROFILE = SensorProfile(
    sensor_id="RISAT",
    name="ISRO Radar Imaging Satellite (C-Band SAR)",
    modality="SAR",
    bands=(
        BandInfo("HH", "Single-Look Complex HH", 5.35e6, 0.0, 3.0, ("hh",)),
        BandInfo("HV", "Single-Look Complex HV", 5.35e6, 0.0, 3.0, ("hv",)),
    ),
    native_crs_typical="Ground Range Detected / UTM",
    typical_resolution_m=3.0,
    band_aliases={"primary": "HH", "crosspol": "HV"},
    preprocessing_notes="C-band active radar; requires speckle filtering and log-amplitude transformation.",
)

# 5. Sentinel-1 C-SAR Profile
SENTINEL_1_PROFILE = SensorProfile(
    sensor_id="SENTINEL-1",
    name="Copernicus Sentinel-1 C-Band SAR",
    modality="SAR",
    bands=(
        BandInfo("VV", "Vertical transmit, Vertical receive", 5.405e6, 0.0, 10.0, ("vv",)),
        BandInfo("VH", "Vertical transmit, Horizontal receive", 5.405e6, 0.0, 10.0, ("vh",)),
    ),
    native_crs_typical="WGS84 / UTM",
    typical_resolution_m=10.0,
    band_aliases={"primary": "VV", "crosspol": "VH"},
    preprocessing_notes="Level-1 GRD backscatter intensity with thermal noise removal and terrain calibration.",
)

# 6. Generic Optical Fallback
GENERIC_OPTICAL_PROFILE = SensorProfile(
    sensor_id="GENERIC-OPTICAL",
    name="Generic Multi-Spectral / RGB Optical",
    modality="OPTICAL",
    bands=(
        BandInfo("B1", "Red", 0.650, 0.050, 10.0, ("red", "r")),
        BandInfo("B2", "Green", 0.550, 0.050, 10.0, ("green", "g")),
        BandInfo("B3", "Blue", 0.480, 0.050, 10.0, ("blue", "b")),
        BandInfo("B4", "Near Infrared", 0.850, 0.050, 10.0, ("nir",)),
    ),
    native_crs_typical="EPSG:4326",
    typical_resolution_m=10.0,
    band_aliases={"red": "B1", "green": "B2", "blue": "B3", "nir": "B4"},
)

# 7. Generic SAR Fallback
GENERIC_SAR_PROFILE = SensorProfile(
    sensor_id="GENERIC-SAR",
    name="Generic Synthetic Aperture Radar",
    modality="SAR",
    bands=(
        BandInfo("SAR1", "Amplitude / Intensity", 0.0, 0.0, 10.0, ("intensity", "amp")),
    ),
    native_crs_typical="EPSG:4326",
    typical_resolution_m=10.0,
    band_aliases={"primary": "SAR1"},
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
    "GENERIC-SAR": GENERIC_SAR_PROFILE,
}


def get_sensor_profile(sensor_name: str | None, modality: str = "OPTICAL") -> SensorProfile:
    """Selects appropriate SensorProfile by name, alias, or modality fallback."""
    if sensor_name:
        s_upper = sensor_name.upper()
        for k, v in SENSOR_REGISTRY.items():
            if k in s_upper or s_upper in k:
                return v

    if modality.upper() == "SAR":
        return GENERIC_SAR_PROFILE
    return GENERIC_OPTICAL_PROFILE


# ==============================================================================
# SPECIALIST PREPROCESSING PIPELINES (§23 & §24)
# ==============================================================================

def preprocess_optical_raster(
    raster: np.ndarray,
    profile: SensorProfile | None = None,
    percentile_clip: tuple[float, float] = (2.0, 98.0),
) -> np.ndarray:
    """
    Normalizes optical remote sensing imagery per §24:
    - Normalizes float/uint reflectance
    - Clips extreme atmospheric outliers
    - Scales smoothly into [0.0, 1.0] range
    """
    arr = raster.astype(np.float32)
    # Filter nodata or NaNs
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)

    if arr.max() > 255.0:
        # 16-bit satellite product (e.g. Sentinel-2 DN)
        arr = arr / 10000.0  # Reflectance scaling
        p_low, p_high = np.percentile(arr[arr > 0], percentile_clip) if np.any(arr > 0) else (0.0, 1.0)
        arr = np.clip((arr - p_low) / max(1e-5, p_high - p_low), 0.0, 1.0)
    elif arr.max() > 1.0:
        # Standard 8-bit RGB
        arr = arr / 255.0

    return np.clip(arr, 0.0, 1.0)


def preprocess_sar_raster(
    raster: np.ndarray,
    speckle_filter_size: int = 3,
    apply_log_transform: bool = True,
) -> np.ndarray:
    """
    Normalizes Synthetic Aperture Radar (SAR) imagery per §23:
    - Speckle noise suppression (median/box filter)
    - Intensity / logarithmic decibel transform: 10 * log10(I + 1e-6)
    - Backscatter normalization into standard [0.0, 1.0] range
    - Never treats SAR as ordinary RGB imagery
    """
    arr = raster.astype(np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    arr = np.maximum(arr, 0.0)

    # 1. Speckle-aware noise reduction using median filtering
    if speckle_filter_size > 1:
        if arr.ndim == 2:
            arr = ndimage.median_filter(arr, size=speckle_filter_size)
        elif arr.ndim == 3:
            for c in range(arr.shape[0]):
                arr[c] = ndimage.median_filter(arr[c], size=speckle_filter_size)

    # 2. Logarithmic transformation for radar backscatter
    if apply_log_transform:
        # Convert power / intensity to decibel-like range
        arr = 10.0 * np.log10(arr + 1e-5)
        p_min, p_max = np.percentile(arr, (2.0, 98.0))
        if p_max > p_min:
            arr = (arr - p_min) / (p_max - p_min)
        else:
            arr = np.zeros_like(arr)

    return np.clip(arr, 0.0, 1.0)
