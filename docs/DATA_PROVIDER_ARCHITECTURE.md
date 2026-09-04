# Data Provider & STAC Catalogue Architecture

## 1. Provider Abstraction Layer

SatQuery-X encapsulates satellite catalogue access behind a unified abstraction:

```python
class EarthObservationProvider(ABC):
    @abstractmethod
    def search_scenes(self, aoi_geometry, date_start, date_end, sensor, max_cloud, limit):
        """Query STAC or catalogue endpoint for candidate scenes."""
        pass

    @abstractmethod
    def get_scene_metadata(self, external_id):
        """Retrieve granular band, orbit, and product parameters."""
        pass

    @abstractmethod
    def download_asset(self, asset_href, destination_path, checksum=None):
        """Securely stream raster assets with checksum validation."""
        pass

    @abstractmethod
    def health_check(self):
        """Evaluate provider connectivity and authentication status."""
        pass
```

---

## 2. Supported Providers

1. **Copernicus Data Space Ecosystem (CDSE):**
   * Primary STAC endpoint: `https://stac.dataspace.copernicus.eu/v1/search`
   * OAuth2 Token endpoint: `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`
   * Managed via `apps.satellite.providers.auth.CDSETokenManager` with automatic Bearer token caching and TTL refresh.
2. **Microsoft Planetary Computer (Pluggable):**
   * STAC endpoint: `https://planetarycomputer.microsoft.com/api/stac/v1`
   * Supports Azure SAS token signing for direct COG window reads.
3. **NASA Earthdata (Pluggable):**
   * CMR STAC endpoint: `https://cmr.earthdata.nasa.gov/stac`
   * Bearer token authentication via Earthdata Login.
4. **Mock Satellite Provider (Offline & Demo Mode):**
   * Generates deterministic, scientifically valid multi-band GeoTIFFs when offline or in demonstration mode (`SATQUERY_MODE=demo`).
   * Explicitly transparently labeled as `demo_data` to ensure zero fabrication of live satellite records.
