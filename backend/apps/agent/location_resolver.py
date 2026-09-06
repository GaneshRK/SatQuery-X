"""
Evidence-grounded geospatial location resolver for SatQuery-X.

Responsibilities
----------------
- Resolve explicit coordinates.
- Resolve explicit GeoJSON geometry.
- Resolve map-pin / active-AOI context.
- Resolve place names through an actual geocoding provider.
- Support provider-backed fuzzy/typo-tolerant matching.
- Preserve provider-returned bounding boxes.
- Preserve provider-returned geometry when available.
- Fail closed when geographic evidence is insufficient.

Scientific / product rules
--------------------------
1. Never hardcode city coordinates.
2. Never hardcode city bounding boxes.
3. Never invent a geographic extent around a point.
4. Never fabricate a confidence score.
5. Never convert a geocoder point into a fake polygon.
6. "Here", "this place", and "this area" must come from active
   conversation/map context.
7. Provider bounding boxes are extents, not administrative boundaries.
8. GeoJSON geometry is preserved as supplied.
9. Coordinate order must be explicit where ambiguity exists.
10. A failed geocoding operation returns None rather than guessing.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from math import isfinite
from typing import Any, Dict, List, Mapping, Optional, Tuple


logger = logging.getLogger(__name__)


# ============================================================================
# Data contract
# ============================================================================


@dataclass
class GeographicLocation:
    """
    Verified geographic location.

    bbox:
        [west, south, east, north] in WGS84 when supplied by the source.

    geometry:
        GeoJSON geometry when supplied by the source or explicitly provided.

        A point is never expanded into an arbitrary polygon.

    confidence:
        Only populated when an upstream source explicitly supplies a
        calibrated confidence value. This resolver does not invent one.
    """

    canonical_name: str
    latitude: Optional[float]
    longitude: Optional[float]

    bbox: Optional[List[float]]
    geometry: Optional[Dict[str, Any]]

    admin_level: str
    state: str
    country: str

    confidence: Optional[float]
    source: str

    is_valid: bool = True
    raw_query: str = ""

    provider: Optional[str] = None
    place_id: Optional[str] = None
    display_name: Optional[str] = None

    provider_metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        coords = None

        if (
            self.latitude is not None
            and self.longitude is not None
        ):
            coords = [
                self.longitude,
                self.latitude,
            ]

        return {
            "name": self.canonical_name,
            "canonical_name": self.canonical_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "coords": coords,
            "bbox": self.bbox,
            "geometry": self.geometry,
            "admin_level": self.admin_level,
            "state": self.state,
            "country": self.country,
            "confidence": self.confidence,
            "source": self.source,
            "is_valid": self.is_valid,
            "provider": self.provider,
            "place_id": self.place_id,
            "display_name": self.display_name,
            "raw_query": self.raw_query,
            "provider_metadata": self.provider_metadata or {},
        }


# ============================================================================
# Resolver
# ============================================================================


class LocationResolver:
    """
    Enterprise location resolver for SatQuery-X.

    Resolution priority:

        1. Explicit GeoJSON
        2. Explicit coordinates
        3. Active map/context reference
        4. Configured project geocoder
        5. Nominatim
        6. Provider-supplied contextual candidates
        7. Fail closed

    There is deliberately NO static city gazetteer.

    Static geographic values are dangerous for a remote-sensing product
    because they can silently produce incorrect AOIs.
    """

    DEFAULT_NOMINATIM_URL = (
        "https://nominatim.openstreetmap.org/search"
    )

    DEFAULT_USER_AGENT = (
        "SatQuery-X/3.0"
    )

    CONTEXT_REFERENCE_TERMS = (
        "here",
        "this place",
        "this area",
        "this location",
        "that place",
        "that area",
        "that location",
        "same place",
        "same area",
        "same location",
        "there",
        "current map",
        "selected area",
        "selected location",
        "highlighted area",
        "highlighted location",
        "map pin",
        "selected pin",
        "current pin",
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def resolve(
        cls,
        text: str,
        allow_fuzzy: bool = True,
        allow_network: bool = True,
        fuzzy_cutoff: float = 0.82,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[GeographicLocation]:
        """
        Resolve a geographic location from text and optional context.

        Parameters
        ----------
        text:
            User query or explicit place expression.

        allow_fuzzy:
            Allows fuzzy matching against provider/context candidates.
            It never enables matching against a static location database.

        allow_network:
            Allows configured external geocoding providers.

        fuzzy_cutoff:
            Text similarity threshold for provider-supplied candidates.
            This is NOT geographic confidence.

        session_context:
            Current conversation/map/session context.
        """

        if not isinstance(text, str):
            return None

        raw_query = text
        clean = cls._normalize_text(text)

        if not clean:
            return None

        context = dict(
            session_context or {}
        )

        # --------------------------------------------------------------
        # 1. Explicit GeoJSON object
        # --------------------------------------------------------------

        explicit_geojson = cls._extract_geojson_from_text(
            clean,
            raw_query,
        )

        if explicit_geojson:
            return explicit_geojson

        # --------------------------------------------------------------
        # 2. Explicit coordinates / bbox
        # --------------------------------------------------------------

        explicit_coordinates = cls._resolve_explicit_query(
            clean,
            raw_query,
        )

        if explicit_coordinates:
            return explicit_coordinates

        # --------------------------------------------------------------
        # 3. Contextual reference
        # --------------------------------------------------------------

        contextual = cls._resolve_context_reference(
            clean,
            context,
        )

        if contextual:
            return contextual

        # --------------------------------------------------------------
        # 4. Actual configured geocoder
        # --------------------------------------------------------------

        if allow_network:
            configured = cls._query_configured_geocoder(
                clean,
                context,
            )

            if configured:
                return configured

        # --------------------------------------------------------------
        # 5. Nominatim
        # --------------------------------------------------------------

        if (
            allow_network
            and cls._nominatim_enabled(context)
        ):
            nominatim = cls._query_nominatim(
                clean,
                context=context,
            )

            if nominatim:
                return nominatim

        # --------------------------------------------------------------
        # 6. Fuzzy matching against actual context candidates only
        # --------------------------------------------------------------

        if allow_fuzzy:
            candidates = cls._context_candidates(
                context
            )

            fuzzy = cls._resolve_from_candidates(
                clean,
                candidates,
                fuzzy_cutoff=fuzzy_cutoff,
            )

            if fuzzy:
                return fuzzy

        logger.info(
            "Location resolution failed closed: %r",
            raw_query,
        )

        return None

    @classmethod
    def resolve_from_context(
        cls,
        context: Optional[Dict[str, Any]],
    ) -> Optional[GeographicLocation]:
        """
        Resolve the currently selected map/AOI context.

        Useful for:

            "What changed here?"
            "Analyze this area."
            "Show vegetation in this place."
        """

        return cls._resolve_context_reference(
            "",
            dict(context or {}),
            force_context=True,
        )

    @classmethod
    def resolve_coordinates(
        cls,
        latitude: Any,
        longitude: Any,
        *,
        name: Optional[str] = None,
        raw_query: str = "",
        source: str = "explicit_coords",
    ) -> Optional[GeographicLocation]:
        """
        Resolve explicit WGS84 latitude/longitude.

        No bounding box is created.
        """

        lat = cls._optional_float(latitude)
        lon = cls._optional_float(longitude)

        if lat is None or lon is None:
            return None

        if not cls._valid_lat_lon(
            latitude=lat,
            longitude=lon,
        ):
            return None

        canonical_name = (
            str(name).strip()
            if name
            else f"{lat:.8f}, {lon:.8f}"
        )

        return GeographicLocation(
            canonical_name=canonical_name,
            latitude=lat,
            longitude=lon,
            bbox=None,
            geometry={
                "type": "Point",
                "coordinates": [
                    lon,
                    lat,
                ],
            },
            admin_level="point",
            state="",
            country="",
            confidence=None,
            source=source,
            is_valid=True,
            raw_query=raw_query,
            provider=None,
        )

    @classmethod
    def resolve_geojson(
        cls,
        geometry: Any,
        *,
        name: Optional[str] = None,
        crs: Optional[str] = None,
        raw_query: str = "",
        source: str = "explicit_geometry",
    ) -> Optional[GeographicLocation]:
        """
        Validate explicit GeoJSON.

        The original geometry remains authoritative.

        The representative coordinate is only a convenient reference point;
        it must not be interpreted as the geometry centroid.
        """

        if not isinstance(
            geometry,
            Mapping,
        ):
            return None

        geometry_type = geometry.get(
            "type"
        )

        coordinates = geometry.get(
            "coordinates"
        )

        supported_types = {
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
        }

        if geometry_type not in supported_types:
            return None

        if coordinates is None:
            return None

        if not cls._validate_geojson_coordinates(
            geometry_type,
            coordinates,
        ):
            return None

        representative = cls._representative_coordinate(
            geometry_type,
            coordinates,
        )

        if representative is None:
            return None

        lon, lat = representative

        if not cls._valid_lat_lon(
            latitude=lat,
            longitude=lon,
        ):
            return None

        normalized_geometry = {
            "type": geometry_type,
            "coordinates": coordinates,
        }

        bbox = cls._bbox_from_geometry(
            geometry_type,
            coordinates,
        )

        metadata: Dict[str, Any] = {}

        if crs:
            metadata["crs"] = str(crs)

        return GeographicLocation(
            canonical_name=(
                str(name).strip()
                if name
                else "Explicit geographic geometry"
            ),
            latitude=lat,
            longitude=lon,
            bbox=bbox,
            geometry=normalized_geometry,
            admin_level="custom",
            state="",
            country="",
            confidence=None,
            source=source,
            is_valid=True,
            raw_query=raw_query,
            provider_metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Explicit query parsing
    # ------------------------------------------------------------------

    @classmethod
    def _extract_geojson_from_text(
        cls,
        text: str,
        raw_query: str,
    ) -> Optional[GeographicLocation]:
        """
        Parse a JSON GeoJSON Point/geometry only when the entire input is
        actually a JSON object.

        This avoids accidentally interpreting arbitrary JSON-like text as
        geography.
        """

        stripped = text.strip()

        if not stripped.startswith("{"):
            return None

        try:
            parsed = json.loads(
                stripped
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(
            parsed,
            Mapping,
        ):
            return None

        geometry = parsed

        if (
            parsed.get("type") == "Feature"
            and isinstance(
                parsed.get("geometry"),
                Mapping,
            )
        ):
            geometry = parsed["geometry"]

        if not isinstance(
            geometry,
            Mapping,
        ):
            return None

        if "coordinates" not in geometry:
            return None

        return cls.resolve_geojson(
            geometry,
            name=parsed.get(
                "name"
            ),
            raw_query=raw_query,
            source="explicit_geojson",
        )

    @classmethod
    def _resolve_explicit_query(
        cls,
        clean: str,
        raw_query: str,
    ) -> Optional[GeographicLocation]:
        bbox = cls._extract_bbox(
            clean
        )

        if bbox:
            west, south, east, north = bbox

            return GeographicLocation(
                canonical_name="Explicit bounding box",
                latitude=(south + north) / 2.0,
                longitude=(west + east) / 2.0,
                bbox=bbox,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                        [west, south],
                    ]],
                },
                admin_level="custom",
                state="",
                country="",
                confidence=None,
                source="explicit_bbox",
                is_valid=True,
                raw_query=raw_query,
            )

        pair = cls._extract_coordinate_pair(
            clean
        )

        if pair is None:
            return None

        lon, lat = pair

        return cls.resolve_coordinates(
            latitude=lat,
            longitude=lon,
            raw_query=raw_query,
            source="explicit_coords",
        )

    @classmethod
    def _extract_coordinate_pair(
        cls,
        text: str,
    ) -> Optional[Tuple[float, float]]:
        """
        Extract an explicit coordinate pair.

        Supported:

            lon 76.9558 lat 11.0168
            longitude: 76.9558 latitude: 11.0168

        A standalone pair is accepted only when the entire input is clearly
        coordinate syntax.

        For a standalone pair where both values are inside the valid
        latitude range, longitude/latitude ordering is inherently ambiguous.
        Therefore the parser prefers explicit labels.
        """

        named_match = re.search(
            r"\b(?:lon|longitude)\s*[:=]?\s*"
            r"(-?\d+(?:\.\d+)?)"
            r".{0,40}?"
            r"\b(?:lat|latitude)\s*[:=]?\s*"
            r"(-?\d+(?:\.\d+)?)",
            text,
            flags=re.IGNORECASE,
        )

        if named_match:
            lon = float(
                named_match.group(1)
            )

            lat = float(
                named_match.group(2)
            )

            if cls._valid_lat_lon(
                latitude=lat,
                longitude=lon,
            ):
                return lon, lat

        reverse_named_match = re.search(
            r"\b(?:lat|latitude)\s*[:=]?\s*"
            r"(-?\d+(?:\.\d+)?)"
            r".{0,40}?"
            r"\b(?:lon|longitude)\s*[:=]?\s*"
            r"(-?\d+(?:\.\d+)?)",
            text,
            flags=re.IGNORECASE,
        )

        if reverse_named_match:
            lat = float(
                reverse_named_match.group(1)
            )

            lon = float(
                reverse_named_match.group(2)
            )

            if cls._valid_lat_lon(
                latitude=lat,
                longitude=lon,
            ):
                return lon, lat

        # A standalone pair is safe only if one value cannot possibly be a
        # latitude. In that situation the larger-magnitude value must be
        # longitude.
        simple_match = re.fullmatch(
            r"\s*\(?\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*[,;]\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*\)?\s*",
            text,
        )

        if not simple_match:
            return None

        first = float(
            simple_match.group(1)
        )

        second = float(
            simple_match.group(2)
        )

        first_is_lat = (
            -90.0 <= first <= 90.0
        )

        second_is_lat = (
            -90.0 <= second <= 90.0
        )

        first_is_lon = (
            -180.0 <= first <= 180.0
        )

        second_is_lon = (
            -180.0 <= second <= 180.0
        )

        # First cannot be latitude, so it must be longitude.
        if (
            not first_is_lat
            and first_is_lon
            and second_is_lat
        ):
            return first, second

        # Second cannot be latitude, so it must be longitude.
        if (
            first_is_lat
            and not second_is_lat
            and second_is_lon
        ):
            return second, first

        # If both interpretations are possible, do not guess.
        return None

    @classmethod
    def _extract_bbox(
        cls,
        text: str,
    ) -> Optional[List[float]]:
        """
        Parse explicit:

            bbox: [west, south, east, north]

        The ordering is deliberately documented and enforced.
        """

        match = re.search(
            r"(?:bbox|bounding\s+box|extent)"
            r"\s*[:=]?\s*"
            r"\[?\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*[, ]\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*[, ]\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*[, ]\s*"
            r"(-?\d+(?:\.\d+)?)"
            r"\s*\]?",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        try:
            west = float(
                match.group(1)
            )
            south = float(
                match.group(2)
            )
            east = float(
                match.group(3)
            )
            north = float(
                match.group(4)
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        bbox = [
            west,
            south,
            east,
            north,
        ]

        if not cls._valid_bbox(
            bbox
        ):
            return None

        return bbox

    # ------------------------------------------------------------------
    # Context resolution
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_context_reference(
        cls,
        text: str,
        context: Dict[str, Any],
        force_context: bool = False,
    ) -> Optional[GeographicLocation]:
        if not force_context and not cls._is_context_reference(
            text
        ):
            return None

        priority_keys = (
            "active_map_pin",
            "map_pin",
            "selected_pin",
            "active_aoi",
            "selected_aoi",
            "current_aoi",
            "map_context",
            "resolved_location",
            "current_viewport",
            "conversation_location",
            "previous_aoi",
        )

        for key in priority_keys:
            candidate = context.get(
                key
            )

            location = cls._location_from_context_value(
                candidate,
                source=f"context:{key}",
            )

            if location:
                return location

        return None

    @classmethod
    def _location_from_context_value(
        cls,
        value: Any,
        source: str,
    ) -> Optional[GeographicLocation]:
        if value is None:
            return None

        if isinstance(
            value,
            GeographicLocation,
        ):
            value.source = source
            return value

        if not isinstance(
            value,
            Mapping,
        ):
            return None

        # --------------------------------------------------------------
        # Nested active map pin
        # --------------------------------------------------------------

        for nested_key in (
            "active_pin",
            "pin",
            "selected_pin",
            "location",
            "aoi",
            "viewport",
        ):
            nested = value.get(
                nested_key
            )

            if nested is None:
                continue

            location = cls._location_from_context_value(
                nested,
                source=f"{source}:{nested_key}",
            )

            if location:
                return location

        # --------------------------------------------------------------
        # Explicit GeoJSON geometry
        # --------------------------------------------------------------

        geometry = value.get(
            "geometry"
        )

        if isinstance(
            geometry,
            Mapping,
        ):
            location = cls.resolve_geojson(
                geometry,
                name=(
                    value.get("canonical_name")
                    or value.get("name")
                    or value.get("label")
                ),
                raw_query=str(
                    value.get(
                        "raw_query",
                        "",
                    )
                ),
                source=source,
            )

            if location:
                location.state = str(
                    value.get(
                        "state",
                        "",
                    )
                )

                location.country = str(
                    value.get(
                        "country",
                        "",
                    )
                )

                location.admin_level = str(
                    value.get(
                        "admin_level",
                        location.admin_level,
                    )
                )

                location.confidence = cls._optional_confidence(
                    value.get(
                        "confidence"
                    )
                )

                location.provider = (
                    str(
                        value["provider"]
                    )
                    if value.get(
                        "provider"
                    ) is not None
                    else None
                )

                location.place_id = (
                    str(
                        value["place_id"]
                    )
                    if value.get(
                        "place_id"
                    ) is not None
                    else None
                )

                return location

        # --------------------------------------------------------------
        # Explicit WGS84 bbox
        # --------------------------------------------------------------

        bbox = cls._normalize_bbox(
            value.get(
                "bbox"
            )
        )

        if bbox:
            west, south, east, north = bbox

            return GeographicLocation(
                canonical_name=str(
                    value.get(
                        "canonical_name",
                        value.get(
                            "name",
                            value.get(
                                "label",
                                "Active map area",
                            ),
                        ),
                    )
                ),
                latitude=(south + north) / 2.0,
                longitude=(west + east) / 2.0,
                bbox=bbox,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                        [west, south],
                    ]],
                },
                admin_level=str(
                    value.get(
                        "admin_level",
                        "custom",
                    )
                ),
                state=str(
                    value.get(
                        "state",
                        "",
                    )
                ),
                country=str(
                    value.get(
                        "country",
                        "",
                    )
                ),
                confidence=cls._optional_confidence(
                    value.get(
                        "confidence"
                    )
                ),
                source=source,
                is_valid=True,
                raw_query=str(
                    value.get(
                        "raw_query",
                        "",
                    )
                ),
                provider=(
                    str(
                        value["provider"]
                    )
                    if value.get(
                        "provider"
                    ) is not None
                    else None
                ),
                place_id=(
                    str(
                        value["place_id"]
                    )
                    if value.get(
                        "place_id"
                    ) is not None
                    else None
                ),
                display_name=(
                    str(
                        value["display_name"]
                    )
                    if value.get(
                        "display_name"
                    ) is not None
                    else None
                ),
            )

        # --------------------------------------------------------------
        # Explicit lat/lon map pin
        # --------------------------------------------------------------

        latitude = value.get(
            "latitude",
            value.get("lat"),
        )

        longitude = value.get(
            "longitude",
            value.get("lon"),
        )

        if (
            latitude is not None
            and longitude is not None
        ):
            return cls.resolve_coordinates(
                latitude=latitude,
                longitude=longitude,
                name=(
                    value.get(
                        "canonical_name"
                    )
                    or value.get(
                        "name"
                    )
                    or value.get(
                        "label"
                    )
                ),
                raw_query=str(
                    value.get(
                        "raw_query",
                        "",
                    )
                ),
                source=source,
            )

        # --------------------------------------------------------------
        # Explicit coordinate array
        # --------------------------------------------------------------

        coords = value.get(
            "coords"
        )

        if isinstance(
            coords,
            (list, tuple),
        ) and len(coords) >= 2:
            order = str(
                value.get(
                    "coordinate_order",
                    value.get(
                        "coords_order",
                        "",
                    ),
                )
            ).lower()

            if order in {
                "lon_lat",
                "longitude_latitude",
                "xy",
            }:
                return cls.resolve_coordinates(
                    latitude=coords[1],
                    longitude=coords[0],
                    name=(
                        value.get(
                            "canonical_name"
                        )
                        or value.get(
                            "name"
                        )
                    ),
                    raw_query=str(
                        value.get(
                            "raw_query",
                            "",
                        )
                    ),
                    source=source,
                )

            if order in {
                "lat_lon",
                "latitude_longitude",
                "yx",
            }:
                return cls.resolve_coordinates(
                    latitude=coords[0],
                    longitude=coords[1],
                    name=(
                        value.get(
                            "canonical_name"
                        )
                        or value.get(
                            "name"
                        )
                    ),
                    raw_query=str(
                        value.get(
                            "raw_query",
                            "",
                        )
                    ),
                    source=source,
                )

        return None

    @classmethod
    def _is_context_reference(
        cls,
        text: str,
    ) -> bool:
        clean = cls._normalize_text(
            text
        )

        return any(
            re.search(
                rf"\b{re.escape(term)}\b",
                clean,
            )
            for term in cls.CONTEXT_REFERENCE_TERMS
        )

    # ------------------------------------------------------------------
    # Configured geocoder
    # ------------------------------------------------------------------

    @classmethod
    def _query_configured_geocoder(
        cls,
        place_name: str,
        context: Dict[str, Any],
    ) -> Optional[GeographicLocation]:
        """
        Use an explicitly configured application geocoder when available.

        The resolver accepts only returned geographic evidence.
        """

        callable_geocoder = context.get(
            "geocoder"
        )

        if callable(
            callable_geocoder
        ):
            try:
                result = callable_geocoder(
                    place_name
                )

                location = cls._location_from_provider_result(
                    result,
                    raw_query=place_name,
                    source="configured_geocoder",
                )

                if location:
                    return location

            except Exception as exc:
                logger.debug(
                    "Configured geocoder failed: %s",
                    exc,
                )

        # Optional project integration.
        #
        # This is deliberately imported dynamically because the geocoding
        # module may itself depend on LocationResolver.
        try:
            from apps.agent.geocoding import geocode_location

            result = geocode_location(
                place_name
            )

            location = cls._location_from_provider_result(
                result,
                raw_query=place_name,
                source="project_geocoder",
            )

            if location:
                return location

        except (
            ImportError,
            AttributeError,
        ):
            pass

        except Exception as exc:
            logger.debug(
                "Project geocoder failed: %s",
                exc,
            )

        return None

    @classmethod
    def _location_from_provider_result(
        cls,
        result: Any,
        raw_query: str,
        source: str,
    ) -> Optional[GeographicLocation]:
        if result is None:
            return None

        if isinstance(
            result,
            GeographicLocation,
        ):
            result.raw_query = raw_query
            result.source = source
            return result

        if not isinstance(
            result,
            Mapping,
        ):
            return None

        geometry = result.get(
            "geometry"
        )

        if isinstance(
            geometry,
            Mapping,
        ):
            location = cls.resolve_geojson(
                geometry,
                name=(
                    result.get(
                        "canonical_name"
                    )
                    or result.get(
                        "name"
                    )
                    or result.get(
                        "display_name"
                    )
                ),
                raw_query=raw_query,
                source=source,
            )

            if location:
                location.state = str(
                    result.get(
                        "state",
                        "",
                    )
                )

                location.country = str(
                    result.get(
                        "country",
                        "",
                    )
                )

                location.admin_level = str(
                    result.get(
                        "admin_level",
                        location.admin_level,
                    )
                )

                location.confidence = cls._optional_confidence(
                    result.get(
                        "confidence"
                    )
                )

                location.provider = (
                    str(
                        result["provider"]
                    )
                    if result.get(
                        "provider"
                    ) is not None
                    else None
                )

                location.place_id = (
                    str(
                        result["place_id"]
                    )
                    if result.get(
                        "place_id"
                    ) is not None
                    else None
                )

                location.display_name = (
                    str(
                        result["display_name"]
                    )
                    if result.get(
                        "display_name"
                    ) is not None
                    else None
                )

                return location

        latitude = result.get(
            "latitude",
            result.get("lat"),
        )

        longitude = result.get(
            "longitude",
            result.get("lon"),
        )

        if (
            latitude is None
            or longitude is None
        ):
            return None

        lat = cls._optional_float(
            latitude
        )

        lon = cls._optional_float(
            longitude
        )

        if lat is None or lon is None:
            return None

        if not cls._valid_lat_lon(
            latitude=lat,
            longitude=lon,
        ):
            return None

        bbox = cls._normalize_bbox(
            result.get(
                "bbox"
            )
        )

        if bbox:
            west, south, east, north = bbox

            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]],
            }

        else:
            geometry = {
                "type": "Point",
                "coordinates": [
                    lon,
                    lat,
                ],
            }

        metadata = {}

        provider_metadata = result.get(
            "provider_metadata"
        )

        if isinstance(
            provider_metadata,
            Mapping,
        ):
            metadata.update(
                dict(provider_metadata)
            )

        return GeographicLocation(
            canonical_name=str(
                result.get(
                    "canonical_name",
                    result.get(
                        "name",
                        result.get(
                            "display_name",
                            raw_query,
                        ),
                    ),
                )
            ).strip(),
            latitude=lat,
            longitude=lon,
            bbox=bbox,
            geometry=geometry,
            admin_level=str(
                result.get(
                    "admin_level",
                    "geocoded_location",
                )
            ),
            state=str(
                result.get(
                    "state",
                    "",
                )
            ),
            country=str(
                result.get(
                    "country",
                    "",
                )
            ),
            confidence=cls._optional_confidence(
                result.get(
                    "confidence"
                )
            ),
            source=source,
            is_valid=True,
            raw_query=raw_query,
            provider=(
                str(
                    result["provider"]
                )
                if result.get(
                    "provider"
                ) is not None
                else None
            ),
            place_id=(
                str(
                    result["place_id"]
                )
                if result.get(
                    "place_id"
                ) is not None
                else None
            ),
            display_name=(
                str(
                    result["display_name"]
                )
                if result.get(
                    "display_name"
                ) is not None
                else None
            ),
            provider_metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Nominatim
    # ------------------------------------------------------------------

    @classmethod
    def _nominatim_enabled(
        cls,
        context: Dict[str, Any],
    ) -> bool:
        return bool(
            context.get(
                "allow_nominatim",
                context.get(
                    "nominatim_enabled",
                    True,
                ),
            )
        )

    @classmethod
    def _query_nominatim(
        cls,
        place_name: str,
        timeout: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[GeographicLocation]:
        """
        Query OpenStreetMap Nominatim.

        Provider response:

            lat/lon -> actual point
            boundingbox -> actual provider extent
            geojson -> actual provider geometry, when requested

        No artificial extent is created.
        """

        context = dict(
            context or {}
        )

        endpoint = str(
            context.get(
                "nominatim_url",
                os.getenv(
                    "SATQUERY_NOMINATIM_URL",
                    cls.DEFAULT_NOMINATIM_URL,
                ),
            )
        )

        if not cls._valid_http_endpoint(
            endpoint
        ):
            logger.warning(
                "Invalid Nominatim endpoint configured."
            )
            return None

        if timeout is None:
            timeout = cls._configured_timeout()

        params = {
            "q": place_name,
            "format": "jsonv2",
            "limit": "1",
            "addressdetails": "1",
            "polygon_geojson": "1",
        }

        url = (
            f"{endpoint}?"
            f"{urllib.parse.urlencode(params)}"
        )

        user_agent = str(
            context.get(
                "user_agent",
                os.getenv(
                    "SATQUERY_NOMINATIM_USER_AGENT",
                    cls.DEFAULT_USER_AGENT,
                ),
            )
        )

        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

        try:
            request = urllib.request.Request(
                url,
                headers=headers,
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    return None

                payload = response.read().decode(
                    "utf-8"
                )

            data = json.loads(
                payload
            )

            if (
                not isinstance(data, list)
                or not data
            ):
                return None

            result = data[0]

            if not isinstance(
                result,
                Mapping,
            ):
                return None

            latitude = cls._optional_float(
                result.get("lat")
            )

            longitude = cls._optional_float(
                result.get("lon")
            )

            if (
                latitude is None
                or longitude is None
            ):
                return None

            if not cls._valid_lat_lon(
                latitude=latitude,
                longitude=longitude,
            ):
                return None

            # ----------------------------------------------------------
            # Provider bounding box
            # ----------------------------------------------------------

            bbox = None

            raw_bbox = result.get(
                "boundingbox"
            )

            if (
                isinstance(
                    raw_bbox,
                    (list, tuple),
                )
                and len(raw_bbox) == 4
            ):
                try:
                    south = float(
                        raw_bbox[0]
                    )
                    north = float(
                        raw_bbox[1]
                    )
                    west = float(
                        raw_bbox[2]
                    )
                    east = float(
                        raw_bbox[3]
                    )

                    candidate_bbox = [
                        west,
                        south,
                        east,
                        north,
                    ]

                    if cls._valid_bbox(
                        candidate_bbox
                    ):
                        bbox = candidate_bbox

                except (
                    TypeError,
                    ValueError,
                ):
                    bbox = None

            # ----------------------------------------------------------
            # Provider geometry
            # ----------------------------------------------------------

            provider_geometry = result.get(
                "geojson"
            )

            geometry = None
            geometry_source = None

            if isinstance(
                provider_geometry,
                Mapping,
            ):
                provider_type = provider_geometry.get(
                    "type"
                )

                provider_coordinates = provider_geometry.get(
                    "coordinates"
                )

                if (
                    provider_type
                    and provider_coordinates is not None
                    and cls._validate_geojson_coordinates(
                        provider_type,
                        provider_coordinates,
                    )
                ):
                    geometry = {
                        "type": provider_type,
                        "coordinates": provider_coordinates,
                    }

                    geometry_source = (
                        "nominatim_geojson"
                    )

            if geometry is None:
                geometry = {
                    "type": "Point",
                    "coordinates": [
                        longitude,
                        latitude,
                    ],
                }

                geometry_source = (
                    "geocoder_point"
                )

            address = result.get(
                "address"
            )

            if not isinstance(
                address,
                Mapping,
            ):
                address = {}

            metadata: Dict[str, Any] = {
                "geometry_source": geometry_source,
            }

            for key in (
                "osm_type",
                "osm_id",
                "place_id",
                "place_rank",
                "category",
                "type",
                "addresstype",
                "licence",
                "importance",
                "display_name",
            ):
                if key in result:
                    metadata[key] = result[key]

            # Nominatim's importance is provider ranking metadata, not a
            # calibrated confidence probability. It is therefore stored as
            # provider metadata rather than exposed as confidence.
            canonical_name = (
                result.get(
                    "name"
                )
                or result.get(
                    "display_name"
                )
                or place_name
            )

            return GeographicLocation(
                canonical_name=str(
                    canonical_name
                ).strip(),
                latitude=latitude,
                longitude=longitude,
                bbox=bbox,
                geometry=geometry,
                admin_level=cls._infer_admin_level(
                    result,
                    address,
                ),
                state=str(
                    address.get(
                        "state",
                        "",
                    )
                ),
                country=str(
                    address.get(
                        "country",
                        "",
                    )
                ),
                confidence=None,
                source="nominatim_osm",
                is_valid=True,
                raw_query=place_name,
                provider="OpenStreetMap Nominatim",
                place_id=(
                    str(
                        result["place_id"]
                    )
                    if result.get(
                        "place_id"
                    ) is not None
                    else None
                ),
                display_name=(
                    str(
                        result["display_name"]
                    )
                    if result.get(
                        "display_name"
                    ) is not None
                    else None
                ),
                provider_metadata=metadata,
            )

        except Exception as exc:
            logger.debug(
                "Nominatim resolution failed for %r: %s",
                place_name,
                exc,
            )

        return None

    # ------------------------------------------------------------------
    # Context candidate fuzzy matching
    # ------------------------------------------------------------------

    @classmethod
    def _context_candidates(
        cls,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Return only candidates supplied by the application/provider.

        There is no local city database.
        """

        raw_candidates = context.get(
            "location_candidates",
            context.get(
                "geocoder_candidates",
                [],
            ),
        )

        if not isinstance(
            raw_candidates,
            list,
        ):
            return []

        candidates = []

        for candidate in raw_candidates:
            if not isinstance(
                candidate,
                Mapping,
            ):
                continue

            name = candidate.get(
                "name",
                candidate.get(
                    "display_name"
                ),
            )

            if isinstance(
                name,
                str,
            ) and name.strip():
                candidates.append(
                    dict(candidate)
                )

        return candidates

    @classmethod
    def _resolve_from_candidates(
        cls,
        query: str,
        candidates: List[Dict[str, Any]],
        fuzzy_cutoff: float,
    ) -> Optional[GeographicLocation]:
        if not candidates:
            return None

        names = []

        for candidate in candidates:
            name = candidate.get(
                "name",
                candidate.get(
                    "display_name"
                ),
            )

            if isinstance(
                name,
                str,
            ) and name.strip():
                names.append(
                    name.strip()
                )

        if not names:
            return None

        matches = difflib.get_close_matches(
            query,
            names,
            n=1,
            cutoff=fuzzy_cutoff,
        )

        if not matches:
            return None

        matched_name = matches[0]

        for candidate in candidates:
            candidate_name = candidate.get(
                "name",
                candidate.get(
                    "display_name"
                ),
            )

            if (
                isinstance(
                    candidate_name,
                    str,
                )
                and candidate_name.strip().lower()
                == matched_name.strip().lower()
            ):
                return cls._location_from_provider_result(
                    candidate,
                    raw_query=query,
                    source="context_candidate_fuzzy",
                )

        return None

    # ------------------------------------------------------------------
    # GeoJSON validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate_geojson_coordinates(
        cls,
        geometry_type: str,
        coordinates: Any,
    ) -> bool:
        try:
            if geometry_type == "Point":
                return cls._valid_position(
                    coordinates
                )

            if geometry_type == "MultiPoint":
                return (
                    isinstance(
                        coordinates,
                        list,
                    )
                    and len(coordinates) > 0
                    and all(
                        cls._valid_position(
                            position
                        )
                        for position in coordinates
                    )
                )

            if geometry_type == "LineString":
                return (
                    isinstance(
                        coordinates,
                        list,
                    )
                    and len(coordinates) >= 2
                    and all(
                        cls._valid_position(
                            position
                        )
                        for position in coordinates
                    )
                )

            if geometry_type == "MultiLineString":
                return (
                    isinstance(
                        coordinates,
                        list,
                    )
                    and len(coordinates) > 0
                    and all(
                        isinstance(
                            line,
                            list,
                        )
                        and len(line) >= 2
                        and all(
                            cls._valid_position(
                                position
                            )
                            for position in line
                        )
                        for line in coordinates
                    )
                )

            if geometry_type == "Polygon":
                return (
                    isinstance(
                        coordinates,
                        list,
                    )
                    and len(coordinates) > 0
                    and all(
                        cls._valid_ring(
                            ring
                        )
                        for ring in coordinates
                    )
                )

            if geometry_type == "MultiPolygon":
                return (
                    isinstance(
                        coordinates,
                        list,
                    )
                    and len(coordinates) > 0
                    and all(
                        cls._validate_geojson_coordinates(
                            "Polygon",
                            polygon,
                        )
                        for polygon in coordinates
                    )
                )

        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            return False

        return False

    @classmethod
    def _valid_ring(
        cls,
        ring: Any,
    ) -> bool:
        if not isinstance(
            ring,
            list,
        ):
            return False

        if len(ring) < 4:
            return False

        if not all(
            cls._valid_position(
                position
            )
            for position in ring
        ):
            return False

        # GeoJSON linear rings must be closed.
        first = ring[0]
        last = ring[-1]

        try:
            return (
                float(first[0])
                == float(last[0])
                and float(first[1])
                == float(last[1])
            )
        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            return False

    @classmethod
    def _valid_position(
        cls,
        position: Any,
    ) -> bool:
        if not isinstance(
            position,
            (list, tuple),
        ):
            return False

        if len(position) < 2:
            return False

        try:
            longitude = float(
                position[0]
            )
            latitude = float(
                position[1]
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        return cls._valid_lat_lon(
            latitude=latitude,
            longitude=longitude,
        )

    @staticmethod
    def _valid_lat_lon(
        latitude: float,
        longitude: float,
    ) -> bool:
        try:
            latitude = float(
                latitude
            )
            longitude = float(
                longitude
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        if not (
            isfinite(latitude)
            and isfinite(longitude)
        ):
            return False

        return (
            -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        )

    # ------------------------------------------------------------------
    # Geometry utilities
    # ------------------------------------------------------------------

    @classmethod
    def _representative_coordinate(
        cls,
        geometry_type: str,
        coordinates: Any,
    ) -> Optional[Tuple[float, float]]:
        """
        Return one actual coordinate from the supplied geometry.

        This is intentionally NOT called a centroid.

        For polygon geometries, the first coordinate is returned only as a
        representative point.
        """

        try:
            if geometry_type == "Point":
                return (
                    float(coordinates[0]),
                    float(coordinates[1]),
                )

            if geometry_type in {
                "MultiPoint",
                "LineString",
            }:
                if not coordinates:
                    return None

                return (
                    float(coordinates[0][0]),
                    float(coordinates[0][1]),
                )

            if geometry_type == "MultiLineString":
                if (
                    not coordinates
                    or not coordinates[0]
                ):
                    return None

                return (
                    float(
                        coordinates[0][0][0]
                    ),
                    float(
                        coordinates[0][0][1]
                    ),
                )

            if geometry_type == "Polygon":
                if (
                    not coordinates
                    or not coordinates[0]
                ):
                    return None

                return (
                    float(
                        coordinates[0][0][0]
                    ),
                    float(
                        coordinates[0][0][1]
                    ),
                )

            if geometry_type == "MultiPolygon":
                if (
                    not coordinates
                    or not coordinates[0]
                    or not coordinates[0][0]
                ):
                    return None

                return (
                    float(
                        coordinates[0][0][0][0]
                    ),
                    float(
                        coordinates[0][0][0][1]
                    ),
                )

        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            return None

        return None

    @classmethod
    def _bbox_from_geometry(
        cls,
        geometry_type: str,
        coordinates: Any,
    ) -> Optional[List[float]]:
        points = list(
            cls._iter_positions(
                geometry_type,
                coordinates,
            )
        )

        if not points:
            return None

        longitudes = [
            point[0]
            for point in points
        ]

        latitudes = [
            point[1]
            for point in points
        ]

        bbox = [
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes),
        ]

        if (
            bbox[0] == bbox[2]
            and bbox[1] == bbox[3]
        ):
            # A point's bbox should not be treated as an area.
            return None

        if cls._valid_bbox(
            bbox
        ):
            return bbox

        return None

    @classmethod
    def _iter_positions(
        cls,
        geometry_type: str,
        coordinates: Any,
    ):
        if geometry_type == "Point":
            yield (
                float(coordinates[0]),
                float(coordinates[1]),
            )
            return

        if geometry_type in {
            "MultiPoint",
            "LineString",
        }:
            for position in coordinates:
                yield (
                    float(position[0]),
                    float(position[1]),
                )

            return

        if geometry_type == "MultiLineString":
            for line in coordinates:
                for position in line:
                    yield (
                        float(position[0]),
                        float(position[1]),
                    )

            return

        if geometry_type == "Polygon":
            for ring in coordinates:
                for position in ring:
                    yield (
                        float(position[0]),
                        float(position[1]),
                    )

            return

        if geometry_type == "MultiPolygon":
            for polygon in coordinates:
                for ring in polygon:
                    for position in ring:
                        yield (
                            float(position[0]),
                            float(position[1]),
                        )

    # ------------------------------------------------------------------
    # Validation / normalization
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_bbox(
        cls,
        bbox: Any,
    ) -> Optional[List[float]]:
        if not isinstance(
            bbox,
            (list, tuple),
        ):
            return None

        if len(bbox) != 4:
            return None

        try:
            normalized = [
                float(value)
                for value in bbox
            ]
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not cls._valid_bbox(
            normalized
        ):
            return None

        return normalized

    @staticmethod
    def _valid_bbox(
        bbox: List[float],
    ) -> bool:
        if len(bbox) != 4:
            return False

        try:
            west = float(
                bbox[0]
            )
            south = float(
                bbox[1]
            )
            east = float(
                bbox[2]
            )
            north = float(
                bbox[3]
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        if not all(
            isfinite(value)
            for value in (
                west,
                south,
                east,
                north,
            )
        ):
            return False

        return (
            -180.0 <= west <= 180.0
            and -180.0 <= east <= 180.0
            and -90.0 <= south <= 90.0
            and -90.0 <= north <= 90.0
            and west < east
            and south < north
        )

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None

        try:
            result = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not isfinite(
            result
        ):
            return None

        return result

    @classmethod
    def _optional_confidence(
        cls,
        value: Any,
    ) -> Optional[float]:
        """
        Preserve only a supplied confidence in [0, 1].

        This function does not calculate confidence.
        """

        result = cls._optional_float(
            value
        )

        if result is None:
            return None

        if not (
            0.0 <= result <= 1.0
        ):
            return None

        return result

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:
        clean = text.strip().lower()

        clean = re.sub(
            r"[\x00-\x1f]+",
            " ",
            clean,
        )

        clean = re.sub(
            r"\s+",
            " ",
            clean,
        )

        return clean.strip()

    @staticmethod
    def _valid_http_endpoint(
        endpoint: str,
    ) -> bool:
        try:
            parsed = urllib.parse.urlparse(
                endpoint
            )
        except Exception:
            return False

        return (
            parsed.scheme in {
                "http",
                "https",
            }
            and bool(
                parsed.netloc
            )
        )

    @classmethod
    def _configured_timeout(
        cls,
    ) -> float:
        raw = os.getenv(
            "SATQUERY_GEOCODER_TIMEOUT_SECONDS",
            "5",
        )

        try:
            timeout = float(
                raw
            )
        except (
            TypeError,
            ValueError,
        ):
            return 5.0

        if (
            not isfinite(timeout)
            or timeout <= 0
        ):
            return 5.0

        return timeout

    @staticmethod
    def _infer_admin_level(
        result: Mapping[str, Any],
        address: Mapping[str, Any],
    ) -> str:
        for key in (
            "addresstype",
            "type",
            "class",
        ):
            value = result.get(
                key
            )

            if value:
                return str(
                    value
                )

        for key in (
            "city",
            "town",
            "municipality",
            "village",
            "county",
            "state",
            "country",
        ):
            if address.get(
                key
            ):
                return key

        return "geocoded_location"


# ============================================================================
# Compatibility wrappers
# ============================================================================


def resolve_location(
    text: str,
    session_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Compatibility wrapper used by existing SatQuery-X agent code.
    """

    location = LocationResolver.resolve(
        text=text,
        session_context=session_context,
    )

    if location is None:
        return None

    return location.to_dict()


def resolve_coordinates(
    latitude: Any,
    longitude: Any,
    *,
    name: Optional[str] = None,
    raw_query: str = "",
) -> Optional[Dict[str, Any]]:
    location = LocationResolver.resolve_coordinates(
        latitude=latitude,
        longitude=longitude,
        name=name,
        raw_query=raw_query,
    )

    if location is None:
        return None

    return location.to_dict()


def resolve_geometry(
    geometry: Dict[str, Any],
    *,
    name: Optional[str] = None,
    raw_query: str = "",
) -> Optional[Dict[str, Any]]:
    location = LocationResolver.resolve_geojson(
        geometry=geometry,
        name=name,
        raw_query=raw_query,
    )

    if location is None:
        return None

    return location.to_dict()


__all__ = [
    "GeographicLocation",
    "LocationResolver",
    "resolve_location",
    "resolve_coordinates",
    "resolve_geometry",
]