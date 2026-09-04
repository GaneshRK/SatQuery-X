# Satellite Data & Ingestion Architecture

SatQuery AI integrates directly with the **Copernicus Data Space Ecosystem (CDSE)**, the official European Space Agency (ESA) Earth Observation portal.

---

## 1. Supported Sensors & Products

### Sentinel-2 MSI (Multispectral Instrument)
* **Processing Level:** Level-2A (Bottom-of-Atmosphere surface reflectance, atmospherically corrected).
* **Bands Ingested:**
  * Band 2 (Blue, 490 nm, 10m GSD)
  * Band 3 (Green, 560 nm, 10m GSD)
  * Band 4 (Red, 665 nm, 10m GSD)
  * Band 8 (NIR, 842 nm, 10m GSD)
  * Band 11 (SWIR-1, 1610 nm, 20m GSD)
* **Spectral Indices:**
  * **NDVI:** $(NIR - Red) / (NIR + Red)$
  * **NDWI:** $(Green - NIR) / (Green + NIR)$
  * **NDBI:** $(SWIR - NIR) / (SWIR + NIR)$
  * **SAVI:** $((NIR - Red) / (NIR + Red + 0.5)) \times 1.5$
  * **EVI:** $2.5 \times ((NIR - Red) / (NIR + 6 \times Red - 7.5 \times Blue + 1))$

### Sentinel-1 C-SAR (Synthetic Aperture Radar)
* **Processing Level:** Ground Range Detected (GRD), High Resolution.
* **Polarizations:**
  * **VV** (Vertical transmit, Vertical receive)
  * **VH** (Vertical transmit, Horizontal receive)
* **All-Weather Capability:** Unaffected by cloud cover or darkness, optimal for flood inundation mapping and structural change detection.

---

## 2. CDSE Authentication & STAC Protocol

CDSE requires OAuth2 Bearer authentication for product retrieval:
* **Token Endpoint:** `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`
* **STAC Endpoint:** `https://stac.dataspace.copernicus.eu/v1/search`
* **Service Layer:** `apps.satellite.providers.auth.CDSETokenManager`
  * Automates token acquisition, TTL caching, and transparent refresh.
  * Credentials never leave the Django server environment.

---

## 3. Storage & Windowed Processing

* Satellite scenes are stored in `backend/media/imagery/{session_id}/` or S3/MinIO.
* Windowed chunk I/O via `rasterio.windows.Window` prevents loading massive gigabyte-scale rasters into RAM.
* Real-time XYZ tile generator serves 256x256 tiles on demand.
