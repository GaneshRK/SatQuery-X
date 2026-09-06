"""
Copernicus Data Space Ecosystem provider for SatQuery-X.

This provider talks to the real Copernicus Data Space Ecosystem (CDSE)
STAC catalogue.

Design principles:
- Never fabricate satellite scenes.
- Never fabricate footprints, dates, cloud cover, CRS, resolution, or assets.
- Return only metadata actually supplied by CDSE.
- Authentication is handled server-side by CDSETokenManager.
- Network failures are surfaced as provider errors.
- No mock/synthetic fallback is used here.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from .auth import CDSETokenManager
from .base import (
    SatelliteAssetDTO,
    SatelliteCandidateDTO,
    SatelliteProvider,
    SatelliteProviderAuthenticationError,
    SatelliteProviderRequestError,
    SatelliteProviderResponseError,
)

logger = logging.getLogger(__name__)


class CopernicusProvider(SatelliteProvider):
    """
    Real Copernicus Data Space Ecosystem STAC provider.

    Supported catalogue products:
        Sentinel-2 L2A
        Sentinel-1 GRD

    Authentication:
        OAuth2 credentials are managed by CDSETokenManager.
    """

    name = "Copernicus Data Space Ecosystem"

    PRIMARY_STAC_SEARCH_URL = (
        "https://stac.dataspace.copernicus.eu/v1/search"
    )

    FALLBACK_STAC_SEARCH_URL = (
        "https://catalogue.dataspace.copernicus.eu/stac/search"
    )

    PRIMARY_STAC_ROOT_URL = (
        "https://stac.dataspace.copernicus.eu/v1"
    )

    FALLBACK_STAC_ROOT_URL = (
        "https://catalogue.dataspace.copernicus.eu/stac"
    )

    USER_AGENT = (
        "SatQuery-X/1.0 "
        "(Copernicus Data Space Ecosystem STAC Client)"
    )

    REQUEST_TIMEOUT = 20.0

    SENTINEL_2_COLLECTIONS = (
        "sentinel-2-l2a",
        "SENTINEL-2",
        "sentinel-2",
    )

    SENTINEL_1_COLLECTIONS = (
        "sentinel-1-grd",
        "SENTINEL-1",
        "sentinel-1",
    )

    def __init__(
        self,
        token_manager: CDSETokenManager | None = None,
        timeout: float | None = None,
    ) -> None:
        self.token_manager = token_manager or CDSETokenManager()

        if timeout is not None:
            self.timeout = max(1.0, float(timeout))
        else:
            self.timeout = self.REQUEST_TIMEOUT

    # ------------------------------------------------------------------
    # Sensor / collection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_sensor(sensor: str | None) -> str:
        value = str(sensor or "").strip().upper()

        if value in {
            "S2",
            "SENTINEL2",
            "SENTINEL-2",
            "SENTINEL 2",
            "SENTINEL_2",
            "SENTINEL-2A",
            "SENTINEL-2B",
        }:
            return "SENTINEL-2"

        if value in {
            "S1",
            "SENTINEL1",
            "SENTINEL-1",
            "SENTINEL 1",
            "SENTINEL_1",
            "SENTINEL-1A",
            "SENTINEL-1B",
        }:
            return "SENTINEL-1"

        if "SENTINEL-2" in value or "SENTINEL2" in value:
            return "SENTINEL-2"

        if "SENTINEL-1" in value or "SENTINEL1" in value:
            return "SENTINEL-1"

        raise ValueError(
            f"Unsupported Copernicus sensor: {sensor!r}. "
            "Supported sensors are SENTINEL-1 and SENTINEL-2."
        )

    @classmethod
    def _collection_for_sensor(cls, sensor: str) -> str:
        normalized = cls._normalise_sensor(sensor)

        if normalized == "SENTINEL-2":
            return "sentinel-2-l2a"

        if normalized == "SENTINEL-1":
            return "sentinel-1-grd"

        raise ValueError(
            f"No CDSE collection configured for sensor {sensor!r}."
        )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> str:
        value = str(value).strip()

        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must use YYYY-MM-DD format; "
                f"received {value!r}."
            ) from exc

        return value

    @staticmethod
    def _validate_geometry(
        geometry: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if geometry is None:
            return None

        if not isinstance(geometry, dict):
            raise ValueError(
                "AOI geometry must be a GeoJSON geometry object."
            )

        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if not geometry_type:
            raise ValueError(
                "AOI geometry is missing the GeoJSON 'type' field."
            )

        if coordinates is None:
            raise ValueError(
                "AOI geometry is missing GeoJSON coordinates."
            )

        return geometry

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a JSON HTTP request against CDSE.

        No response data is invented if CDSE fails.
        """

        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }

        body: bytes | None = None

        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8")

        if authenticated:
            try:
                auth_headers = self.token_manager.get_auth_headers()
            except Exception as exc:
                raise SatelliteProviderAuthenticationError(
                    "Unable to obtain CDSE authentication headers."
                ) from exc

            headers.update(auth_headers)

        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw = response.read()

                if response.status < 200 or response.status >= 300:
                    raise SatelliteProviderRequestError(
                        f"CDSE returned HTTP {response.status}."
                    )

        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise SatelliteProviderAuthenticationError(
                    f"CDSE authentication/authorization failed "
                    f"(HTTP {exc.code})."
                ) from exc

            raise SatelliteProviderRequestError(
                f"CDSE HTTP request failed with status {exc.code}."
            ) from exc

        except urllib.error.URLError as exc:
            raise SatelliteProviderRequestError(
                f"Unable to reach CDSE: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise SatelliteProviderRequestError(
                "CDSE request timed out."
            ) from exc

        except OSError as exc:
            raise SatelliteProviderRequestError(
                f"CDSE network request failed: {exc}"
            ) from exc

        try:
            decoded = raw.decode("utf-8")
            data = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SatelliteProviderResponseError(
                "CDSE returned a response that is not valid JSON."
            ) from exc

        if not isinstance(data, dict):
            raise SatelliteProviderResponseError(
                "CDSE returned a JSON response that is not an object."
            )

        return data

    # ------------------------------------------------------------------
    # STAC candidate parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_acquisition_date(
        properties: dict[str, Any],
    ) -> str | None:
        """
        Return the provider supplied acquisition datetime/date.

        No date fallback is generated.
        """

        raw_datetime = properties.get("datetime")

        if raw_datetime:
            value = str(raw_datetime)

            try:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
                return parsed.isoformat()
            except ValueError:
                # Preserve the provider value if it is non-standard rather
                # than silently replacing it with another date.
                return value

        for key in (
            "start_datetime",
            "end_datetime",
            "dtr:start_datetime",
            "dtr:end_datetime",
        ):
            value = properties.get(key)

            if value:
                return str(value)

        return None

    @staticmethod
    def _parse_cloud_cover(
        properties: dict[str, Any],
    ) -> float | None:
        """
        Read cloud cover only when CDSE actually provides it.
        """

        candidates = (
            properties.get("eo:cloud_cover"),
            properties.get("cloud_cover"),
            properties.get("s2:cloud_cover"),
        )

        for value in candidates:
            if value is None:
                continue

            try:
                result = float(value)
            except (TypeError, ValueError):
                continue

            if result < 0:
                continue

            return result

        return None

    @staticmethod
    def _asset_summary(
        assets: Any,
    ) -> dict[str, Any]:
        """
        Preserve useful STAC asset metadata without downloading assets.
        """

        if not isinstance(assets, dict):
            return {}

        result: dict[str, Any] = {}

        for key, raw_asset in assets.items():
            if not isinstance(raw_asset, dict):
                continue

            href = raw_asset.get("href")

            if not href:
                continue

            entry: dict[str, Any] = {
                "href": str(href),
            }

            for field in (
                "type",
                "title",
                "description",
                "roles",
                "file:size",
                "gsd",
                "eo:bands",
            ):
                if field in raw_asset:
                    entry[field] = raw_asset[field]

            result[str(key)] = entry

        return result

    @classmethod
    def _candidate_from_feature(
        cls,
        feature: dict[str, Any],
        requested_sensor: str,
        collection: str,
    ) -> SatelliteCandidateDTO | None:
        if not isinstance(feature, dict):
            return None

        item_id = feature.get("id")

        if not item_id:
            logger.warning(
                "Ignoring CDSE STAC feature without an item id."
            )
            return None

        properties = feature.get("properties")

        if not isinstance(properties, dict):
            properties = {}

        geometry = feature.get("geometry")

        # A STAC item without geometry is still useful metadata, but we do
        # not substitute the AOI geometry for it.
        if geometry is not None and not isinstance(geometry, dict):
            geometry = None

        acquisition_date = cls._parse_acquisition_date(
            properties
        )

        cloud_cover = cls._parse_cloud_cover(
            properties
        )

        assets = cls._asset_summary(
            feature.get("assets")
        )

        thumbnail_url: str | None = None

        preferred_thumbnail_keys = (
            "thumbnail",
            "visual",
            "preview",
            "rendered_preview",
        )

        for key in preferred_thumbnail_keys:
            candidate_asset = assets.get(key)

            if isinstance(candidate_asset, dict):
                href = candidate_asset.get("href")

                if href:
                    thumbnail_url = str(href)
                    break

        metadata: dict[str, Any] = {}

        # Preserve provider metadata needed later for provenance and
        # scene ingestion without fabricating scientific values.
        for key in (
            "platform",
            "constellation",
            "instruments",
            "processing:level",
            "s2:product_uri",
            "s1:product_type",
            "sar:instrument_mode",
            "sat:orbit_state",
            "sat:relative_orbit",
            "sat:absolute_orbit",
            "proj:epsg",
            "proj:shape",
            "proj:transform",
            "gsd",
            "created",
            "updated",
        ):
            if key in properties:
                metadata[key] = properties[key]

        return SatelliteCandidateDTO(
            stac_item_id=str(item_id),
            collection=str(
                feature.get("collection") or collection
            ),
            sensor=requested_sensor,
            acquisition_date=acquisition_date,
            cloud_cover_pct=cloud_cover,
            footprint_geom=geometry,
            thumbnail_url=thumbnail_url,
            assets_summary=assets,
            provider="copernicus_cdse",
            is_synthetic=False,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_scenes(
        self,
        aoi_geometry: dict[str, Any],
        date_start: str,
        date_end: str,
        sensor: str = "SENTINEL-2",
        max_cloud_cover: float | None = None,
        limit: int = 10,
    ) -> list[SatelliteCandidateDTO]:
        """
        Search the live CDSE STAC catalogue.

        Spatial filtering:
            GeoJSON intersects geometry.

        Temporal filtering:
            date_start -> date_end.

        Cloud filtering:
            Applied only when explicitly supplied and relevant.

        Returns:
            Actual provider catalogue candidates only.
        """

        geometry = self._validate_geometry(
            aoi_geometry
        )

        start = self._validate_date(
            date_start,
            "date_start",
        )

        end = self._validate_date(
            date_end,
            "date_end",
        )

        if start > end:
            raise ValueError(
                "date_start cannot be later than date_end."
            )

        try:
            requested_limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "limit must be an integer."
            ) from exc

        if requested_limit < 1:
            raise ValueError(
                "limit must be greater than zero."
            )

        requested_limit = min(
            requested_limit,
            100,
        )

        requested_sensor = self._normalise_sensor(
            sensor
        )

        collection = self._collection_for_sensor(
            requested_sensor
        )

        payload: dict[str, Any] = {
            "collections": [collection],
            "datetime": (
                f"{start}T00:00:00Z/"
                f"{end}T23:59:59Z"
            ),
            "limit": requested_limit,
        }

        if geometry is not None:
            payload["intersects"] = geometry

        # Cloud cover is an explicit user/system constraint. We never
        # insert a default cloud threshold here.
        if (
            requested_sensor == "SENTINEL-2"
            and max_cloud_cover is not None
        ):
            cloud_limit = float(max_cloud_cover)

            if not 0 <= cloud_limit <= 100:
                raise ValueError(
                    "max_cloud_cover must be between 0 and 100."
                )

            payload["query"] = {
                "eo:cloud_cover": {
                    "lte": cloud_limit
                }
            }

        endpoints = (
            self.PRIMARY_STAC_SEARCH_URL,
            self.FALLBACK_STAC_SEARCH_URL,
        )

        last_error: Exception | None = None

        for endpoint in endpoints:
            try:
                response = self._request_json(
                    endpoint,
                    method="POST",
                    payload=payload,
                    authenticated=False,
                )

                features = response.get("features", [])

                if not isinstance(features, list):
                    raise SatelliteProviderResponseError(
                        "CDSE STAC response contains an invalid "
                        "'features' field."
                    )

                candidates: list[
                    SatelliteCandidateDTO
                ] = []

                for feature in features:
                    candidate = (
                        self._candidate_from_feature(
                            feature=feature,
                            requested_sensor=requested_sensor,
                            collection=collection,
                        )
                    )

                    if candidate is not None:
                        candidates.append(candidate)

                return candidates[:requested_limit]

            except SatelliteProviderAuthenticationError:
                # STAC catalogue search normally permits public metadata
                # access. Do not silently replace authentication failures
                # with synthetic results.
                raise

            except (
                SatelliteProviderRequestError,
                SatelliteProviderResponseError,
            ) as exc:
                last_error = exc

                logger.warning(
                    "CDSE STAC endpoint failed: %s: %s",
                    endpoint,
                    exc,
                )

                continue

        if last_error is not None:
            raise last_error

        raise SatelliteProviderRequestError(
            "All configured CDSE STAC endpoints failed."
        )

    # ------------------------------------------------------------------
    # Scene metadata
    # ------------------------------------------------------------------

    def _scene_urls(
        self,
        stac_item_id: str,
    ) -> list[str]:
        encoded_id = urllib.parse.quote(
            str(stac_item_id),
            safe="",
        )

        return [
            (
                f"{self.PRIMARY_STAC_ROOT_URL}"
                f"/collections/sentinel-2-l2a/items/"
                f"{encoded_id}"
            ),
            (
                f"{self.PRIMARY_STAC_ROOT_URL}"
                f"/collections/sentinel-1-grd/items/"
                f"{encoded_id}"
            ),
            (
                f"{self.FALLBACK_STAC_ROOT_URL}"
                f"/collections/sentinel-2-l2a/items/"
                f"{encoded_id}"
            ),
            (
                f"{self.FALLBACK_STAC_ROOT_URL}"
                f"/collections/sentinel-1-grd/items/"
                f"{encoded_id}"
            ),
        ]

    def get_scene_metadata(
        self,
        stac_item_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve the complete provider STAC item for a scene.

        The returned metadata contains only fields supplied by CDSE.
        """

        item_id = str(stac_item_id).strip()

        if not item_id:
            raise ValueError(
                "stac_item_id is required."
            )

        last_error: Exception | None = None

        for url in self._scene_urls(item_id):
            try:
                data = self._request_json(
                    url,
                    method="GET",
                    authenticated=False,
                )

                if not data.get("id"):
                    data["id"] = item_id

                return data

            except (
                SatelliteProviderRequestError,
                SatelliteProviderResponseError,
            ) as exc:
                last_error = exc

                logger.debug(
                    "Unable to retrieve scene metadata "
                    "from %s: %s",
                    url,
                    exc,
                )

                continue

        if last_error is not None:
            raise last_error

        raise SatelliteProviderRequestError(
            f"Unable to retrieve CDSE metadata for scene "
            f"{item_id!r}."
        )

    # ------------------------------------------------------------------
    # Scene assets
    # ------------------------------------------------------------------

    def get_scene_assets(
        self,
        stac_item_id: str,
    ) -> list[SatelliteAssetDTO]:
        """
        Return asset references from the live STAC item.

        This method does not download the raster.
        """

        item = self.get_scene_metadata(
            stac_item_id
        )

        assets = item.get("assets")

        if not isinstance(assets, dict):
            return []

        result: list[SatelliteAssetDTO] = []

        for asset_key, raw_asset in assets.items():
            if not isinstance(raw_asset, dict):
                continue

            href = raw_asset.get("href")

            if not href:
                continue

            result.append(
                SatelliteAssetDTO(
                    asset_key=str(asset_key),
                    href=str(href),
                    asset_type=(
                        str(raw_asset["type"])
                        if raw_asset.get("type")
                        else None
                    ),
                    title=(
                        str(raw_asset["title"])
                        if raw_asset.get("title")
                        else None
                    ),
                    roles=(
                        raw_asset.get("roles")
                        if isinstance(
                            raw_asset.get("roles"),
                            list,
                        )
                        else []
                    ),
                    metadata={
                        key: value
                        for key, value in raw_asset.items()
                        if key
                        not in {
                            "href",
                            "type",
                            "title",
                            "roles",
                        }
                    },
                )
            )

        return result

    # ------------------------------------------------------------------
    # Asset download
    # ------------------------------------------------------------------

    def download_asset(
        self,
        href: str,
        destination: str,
    ) -> dict[str, Any]:
        """
        Download a real CDSE asset.

        Authentication headers are included when CDSE credentials are
        configured. The caller is responsible for validating the downloaded
        raster before making it available for analysis.
        """

        if not href:
            raise ValueError(
                "Asset href is required."
            )

        if not destination:
            raise ValueError(
                "Destination path is required."
            )

        import os

        destination = os.path.abspath(
            os.path.expanduser(destination)
        )

        os.makedirs(
            os.path.dirname(destination),
            exist_ok=True,
        )

        headers = {
            "Accept": "*/*",
            "User-Agent": self.USER_AGENT,
        }

        try:
            headers.update(
                self.token_manager.get_auth_headers()
            )
        except Exception as exc:
            raise SatelliteProviderAuthenticationError(
                "Unable to obtain CDSE authentication "
                "headers for asset download."
            ) from exc

        request = urllib.request.Request(
            url=str(href),
            headers=headers,
            method="GET",
        )

        total_bytes = 0

        try:
            with urllib.request.urlopen(
                request,
                timeout=max(
                    self.timeout,
                    60.0,
                ),
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise SatelliteProviderRequestError(
                        f"CDSE asset download returned "
                        f"HTTP {response.status}."
                    )

                with open(
                    destination,
                    "wb",
                ) as output:
                    while True:
                        chunk = response.read(
                            1024 * 1024
                        )

                        if not chunk:
                            break

                        output.write(chunk)
                        total_bytes += len(chunk)

        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise SatelliteProviderAuthenticationError(
                    f"CDSE asset download authorization "
                    f"failed (HTTP {exc.code})."
                ) from exc

            raise SatelliteProviderRequestError(
                f"CDSE asset download failed "
                f"(HTTP {exc.code})."
            ) from exc

        except urllib.error.URLError as exc:
            raise SatelliteProviderRequestError(
                f"Unable to download CDSE asset: "
                f"{exc.reason}"
            ) from exc

        except OSError as exc:
            raise SatelliteProviderRequestError(
                f"Unable to write downloaded CDSE asset: "
                f"{exc}"
            ) from exc

        if total_bytes <= 0:
            try:
                os.remove(destination)
            except OSError:
                pass

            raise SatelliteProviderResponseError(
                "CDSE returned an empty asset."
            )

        return {
            "status": "DOWNLOADED",
            "href": str(href),
            "destination": destination,
            "bytes": total_bytes,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """
        Report live CDSE catalogue/authentication status.

        Health information is diagnostic only and does not fabricate
        satellite availability.
        """

        auth = self.token_manager.health_check()

        endpoint_status: dict[str, Any] = {
            "reachable": False,
            "endpoint": self.PRIMARY_STAC_ROOT_URL,
        }

        try:
            request = urllib.request.Request(
                url=self.PRIMARY_STAC_ROOT_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.USER_AGENT,
                },
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=5.0,
            ) as response:
                endpoint_status["reachable"] = (
                    200 <= response.status < 300
                )
                endpoint_status["http_status"] = (
                    response.status
                )

        except urllib.error.HTTPError as exc:
            endpoint_status["http_status"] = exc.code
            endpoint_status["error"] = (
                "HTTP error from CDSE catalogue."
            )

        except Exception:
            endpoint_status["error"] = (
                "CDSE catalogue endpoint is unreachable."
            )

        reachable = bool(
            endpoint_status["reachable"]
        )

        if reachable:
            status = (
                "healthy"
                if auth.get("healthy", False)
                else "degraded"
            )
        else:
            status = "unavailable"

        return {
            "name": self.name,
            "status": status,
            "catalogue": endpoint_status,
            "authentication": auth,
            "capabilities": self.capabilities(),
        }

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "copernicus_cdse",
            "catalogue": "STAC",
            "live_catalogue": True,
            "synthetic_fallback": False,
            "supported_sensors": [
                "SENTINEL-1",
                "SENTINEL-2",
            ],
            "supported_products": [
                "sentinel-1-grd",
                "sentinel-2-l2a",
            ],
            "supports": {
                "spatial_search": True,
                "temporal_search": True,
                "cloud_filter": True,
                "scene_metadata": True,
                "asset_listing": True,
                "asset_download": True,
            },
        }


__all__ = [
    "CopernicusProvider",
]