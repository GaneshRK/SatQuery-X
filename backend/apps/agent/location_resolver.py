"""Dedicated Location Resolver with Canonical Gazetteer, Typo Tolerance,
and Fail-Closed Geospatial Grounding per SatQuery AI Architecture.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GeographicLocation:
    canonical_name: str
    latitude: float
    longitude: float
    bbox: List[float]  # [west, south, east, north] in WGS84
    geometry: Dict[str, Any]  # GeoJSON representation
    admin_level: str  # "city", "district", "state", "port", "basin", "custom"
    state: str
    country: str
    confidence: float
    source: str  # "gazetteer_exact", "gazetteer_fuzzy", "nominatim", "explicit_coords", "viewport"
    is_valid: bool = True
    raw_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.canonical_name,
            "canonical_name": self.canonical_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "coords": [self.longitude, self.latitude],
            "bbox": self.bbox,
            "geometry": self.geometry,
            "admin_level": self.admin_level,
            "state": self.state,
            "country": self.country,
            "confidence": self.confidence,
            "source": self.source,
            "is_valid": self.is_valid,
        }


# Canonical Gazetteer of Major Indian & International Geospatial Hubs
_CANONICAL_GAZETTEER: Dict[str, Dict[str, Any]] = {
    "thoothukudi": {
        "canonical_name": "Thoothukudi Port & Maritime Industrial Hub",
        "latitude": 8.7642,
        "longitude": 78.1348,
        "bbox": [78.08, 8.70, 78.22, 8.85],
        "admin_level": "port_district",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["tuticorin", "thothukudi", "thuthukudi", "thoothukkudi", "tuticorine"],
    },
    "coimbatore": {
        "canonical_name": "Coimbatore Industrial Basin",
        "latitude": 11.0168,
        "longitude": 76.9558,
        "bbox": [76.85, 10.90, 77.10, 11.15],
        "admin_level": "city_basin",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["coimbature", "kovai", "cbe", "coimbathore", "coimbator"],
    },
    "chennai": {
        "canonical_name": "Chennai Metropolitan Region",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "bbox": [80.15, 12.95, 80.35, 13.15],
        "admin_level": "metropolis",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["madras", "chenai", "chenna"],
    },
    "madurai": {
        "canonical_name": "Madurai Cultural & Industrial Corridor",
        "latitude": 9.9252,
        "longitude": 78.1198,
        "bbox": [78.05, 9.88, 78.20, 10.00],
        "admin_level": "city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["madura", "madhura", "madhurai"],
    },
    "tirunelveli": {
        "canonical_name": "Tirunelveli Urban Agglomeration",
        "latitude": 8.7139,
        "longitude": 77.7567,
        "bbox": [77.65, 8.68, 77.80, 8.78],
        "admin_level": "district_city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["nellai", "thirunelveli", "tirunelvelli"],
    },
    "tiruchirappalli": {
        "canonical_name": "Tiruchirappalli Cauvery Basin",
        "latitude": 10.7905,
        "longitude": 78.7047,
        "bbox": [78.60, 10.75, 78.78, 10.88],
        "admin_level": "basin_city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["trichy", "tiruchi", "thiruchirapalli", "thiruchi"],
    },
    "salem": {
        "canonical_name": "Salem Mineral & Metallurgical Basin",
        "latitude": 11.6643,
        "longitude": 78.1460,
        "bbox": [78.10, 11.60, 78.25, 11.72],
        "admin_level": "city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["selam", "sailam"],
    },
    "tiruppur": {
        "canonical_name": "Tiruppur Textile Export Hub",
        "latitude": 11.1085,
        "longitude": 77.3411,
        "bbox": [77.30, 11.08, 77.42, 11.18],
        "admin_level": "export_hub",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["tirupur", "thiruppur", "thirupur"],
    },
    "erode": {
        "canonical_name": "Erode Turmeric & Textile Basin",
        "latitude": 11.3410,
        "longitude": 77.7172,
        "bbox": [77.68, 11.30, 77.78, 11.40],
        "admin_level": "city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["erodu"],
    },
    "vellore": {
        "canonical_name": "Vellore Palar Valley",
        "latitude": 12.9165,
        "longitude": 79.1325,
        "bbox": [79.10, 12.88, 79.20, 12.98],
        "admin_level": "city",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["velore", "velur"],
    },
    "hosur": {
        "canonical_name": "Hosur Manufacturing & Tech Corridor",
        "latitude": 12.7409,
        "longitude": 77.8253,
        "bbox": [77.78, 12.70, 77.88, 12.78],
        "admin_level": "industrial_hub",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["hosuru"],
    },
    "dindigul": {
        "canonical_name": "Dindigul Valley",
        "latitude": 10.3673,
        "longitude": 77.9803,
        "bbox": [77.92, 10.32, 78.05, 10.42],
        "admin_level": "district",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["thindukkal", "dindigal"],
    },
    "thanjavur": {
        "canonical_name": "Thanjavur Delta Granary",
        "latitude": 10.7870,
        "longitude": 79.1378,
        "bbox": [79.10, 10.74, 79.20, 10.84],
        "admin_level": "delta_basin",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["tanjore", "thanjai"],
    },
    "cuddalore": {
        "canonical_name": "Cuddalore SIPCOT Coastal Belt",
        "latitude": 11.7480,
        "longitude": 79.7714,
        "bbox": [79.72, 11.70, 79.82, 11.80],
        "admin_level": "coastal_district",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["kadalur"],
    },
    "nagapattinam": {
        "canonical_name": "Nagapattinam Coastal Delta",
        "latitude": 10.7656,
        "longitude": 79.8428,
        "bbox": [79.80, 10.72, 79.90, 10.82],
        "admin_level": "port_district",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["nagai", "nagapatnam"],
    },
    "kanyakumari": {
        "canonical_name": "Kanyakumari Peninsular Cape",
        "latitude": 8.0883,
        "longitude": 77.5385,
        "bbox": [77.50, 8.05, 77.60, 8.15],
        "admin_level": "cape_district",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["cape comorin", "kanniyakumari"],
    },
    "pollachi": {
        "canonical_name": "Pollachi Agricultural Basin",
        "latitude": 10.6609,
        "longitude": 77.0089,
        "bbox": [76.95, 10.60, 77.08, 10.72],
        "admin_level": "basin",
        "state": "Tamil Nadu",
        "country": "India",
        "aliases": ["polachi"],
    },
    "bengaluru": {
        "canonical_name": "Bengaluru Urban Plateau",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "bbox": [77.50, 12.85, 77.70, 13.05],
        "admin_level": "metropolis",
        "state": "Karnataka",
        "country": "India",
        "aliases": ["bangalore", "banglore", "bengalore", "blr"],
    },
    "mumbai": {
        "canonical_name": "Mumbai Metropolitan Region",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "bbox": [72.75, 18.90, 73.05, 19.25],
        "admin_level": "metropolis",
        "state": "Maharashtra",
        "country": "India",
        "aliases": ["bombay"],
    },
    "delhi": {
        "canonical_name": "National Capital Region (Delhi)",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "bbox": [77.05, 28.50, 77.35, 28.75],
        "admin_level": "ncr",
        "state": "Delhi",
        "country": "India",
        "aliases": ["new delhi", "ncr"],
    },
    "kochi": {
        "canonical_name": "Kochi Backwaters & Port Hub",
        "latitude": 9.9312,
        "longitude": 76.2673,
        "bbox": [76.22, 9.90, 76.35, 10.05],
        "admin_level": "port_city",
        "state": "Kerala",
        "country": "India",
        "aliases": ["cochin", "ernakulam"],
    },
    "visakhapatnam": {
        "canonical_name": "Visakhapatnam Deepwater Coast",
        "latitude": 17.6868,
        "longitude": 83.2185,
        "bbox": [83.25, 17.65, 83.40, 17.78],
        "admin_level": "port_city",
        "state": "Andhra Pradesh",
        "country": "India",
        "aliases": ["vizag", "vishakapatnam"],
    },
    "mangalore": {
        "canonical_name": "Mangalore Coastal Port",
        "latitude": 12.9141,
        "longitude": 74.8560,
        "bbox": [74.80, 12.82, 74.92, 12.95],
        "admin_level": "port_city",
        "state": "Karnataka",
        "country": "India",
        "aliases": ["mangaluru"],
    },
    "kaziranga": {
        "canonical_name": "Kaziranga National Park",
        "latitude": 26.6667,
        "longitude": 93.3500,
        "bbox": [93.10, 26.50, 93.50, 26.85],
        "admin_level": "national_park",
        "state": "Assam",
        "country": "India",
        "aliases": ["kaziranga park"],
    },
    "valencia": {
        "canonical_name": "Valencia Coastal Basin",
        "latitude": 39.4699,
        "longitude": -0.3763,
        "bbox": [-0.55, 39.35, -0.25, 39.60],
        "admin_level": "coastal_basin",
        "state": "Valencia",
        "country": "Spain",
        "aliases": ["valencia spain"],
    },
    "aral sea": {
        "canonical_name": "Aral Sea Desiccation Basin",
        "latitude": 45.0000,
        "longitude": 60.0000,
        "bbox": [58.50, 44.00, 61.50, 46.50],
        "admin_level": "lake_basin",
        "state": "Karakalpakstan",
        "country": "Uzbekistan",
        "aliases": ["aral", "south aral sea"],
    },
}


class LocationResolver:
    """Enterprise Location Resolver:
    - Normalizes raw place strings
    - Performs typo-tolerant fuzzy matching against canonical gazetteer
    - Queries Nominatim OpenStreetMap fallback when needed
    - Enforces fail-closed behavior (returns is_valid=False for unverifiable names)
    """

    _ALIAS_TO_KEY: Dict[str, str] = {}
    _ALL_KEYS_AND_ALIASES: List[str] = []

    @classmethod
    def _init_indices(cls):
        if cls._ALIAS_TO_KEY:
            return
        for key, data in _CANONICAL_GAZETTEER.items():
            cls._ALIAS_TO_KEY[key] = key
            for alias in data.get("aliases", []):
                cls._ALIAS_TO_KEY[alias.lower()] = key
        cls._ALL_KEYS_AND_ALIASES = list(cls._ALIAS_TO_KEY.keys())

    @classmethod
    def resolve(
        cls,
        text: str,
        allow_fuzzy: bool = True,
        allow_network: bool = True,
        fuzzy_cutoff: float = 0.70,
    ) -> Optional[GeographicLocation]:
        """Resolves a raw place string to a verified GeographicLocation."""
        cls._init_indices()
        if not text or not isinstance(text, str):
            return None

        clean = text.lower().strip()
        # Clean common surrounding punctuation
        clean = re.sub(r"[\?\.\,\!\:\;]+$", "", clean).strip()

        if len(clean) < 2:
            return None

        # 1. Direct exact match in gazetteer or aliases
        if clean in cls._ALIAS_TO_KEY:
            primary_key = cls._ALIAS_TO_KEY[clean]
            data = _CANONICAL_GAZETTEER[primary_key]
            return cls._build_location(data, source="gazetteer_exact", raw=text, confidence=1.0)

        # 2. Substring whole-word match
        for alias_key, primary_key in cls._ALIAS_TO_KEY.items():
            if re.search(rf"\b{re.escape(alias_key)}\b", clean):
                data = _CANONICAL_GAZETTEER[primary_key]
                return cls._build_location(data, source="gazetteer_word_match", raw=text, confidence=0.98)

        # 3. Fuzzy typo-tolerant matching against gazetteer aliases
        if allow_fuzzy:
            # Check individual words or the full string
            matches = difflib.get_close_matches(clean, cls._ALL_KEYS_AND_ALIASES, n=1, cutoff=fuzzy_cutoff)
            if matches:
                matched_alias = matches[0]
                primary_key = cls._ALIAS_TO_KEY[matched_alias]
                data = _CANONICAL_GAZETTEER[primary_key]
                ratio = difflib.SequenceMatcher(None, clean, matched_alias).ratio()
                return cls._build_location(data, source="gazetteer_fuzzy", raw=text, confidence=round(0.85 * ratio, 3))

            # Also try matching each word in clean (e.g. "coimbature city" -> "coimbature" -> "coimbatore")
            tokens = re.findall(r"\b[a-zA-Z]{3,20}\b", clean)
            for token in tokens:
                t_matches = difflib.get_close_matches(token, cls._ALL_KEYS_AND_ALIASES, n=1, cutoff=fuzzy_cutoff)
                if t_matches:
                    primary_key = cls._ALIAS_TO_KEY[t_matches[0]]
                    data = _CANONICAL_GAZETTEER[primary_key]
                    ratio = difflib.SequenceMatcher(None, token, t_matches[0]).ratio()
                    return cls._build_location(data, source="gazetteer_token_fuzzy", raw=text, confidence=round(0.85 * ratio, 3))

        # 4. Live Nominatim OpenStreetMap Geocoding Fallback
        if allow_network:
            nom_res = cls._query_nominatim(clean)
            if nom_res:
                return nom_res

        # 5. Fail-Closed: Cannot verify geography
        return None

    @classmethod
    def _build_location(
        cls,
        data: Dict[str, Any],
        source: str,
        raw: str,
        confidence: float,
    ) -> GeographicLocation:
        w, s, e, n = data["bbox"]
        geometry = {
            "type": "Polygon",
            "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
        }
        return GeographicLocation(
            canonical_name=data["canonical_name"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            bbox=data["bbox"],
            geometry=geometry,
            admin_level=data.get("admin_level", "city"),
            state=data.get("state", "Tamil Nadu"),
            country=data.get("country", "India"),
            confidence=confidence,
            source=source,
            is_valid=True,
            raw_query=raw,
        )

    @classmethod
    def _query_nominatim(cls, place_name: str, timeout: float = 3.0) -> Optional[GeographicLocation]:
        """Queries OpenStreetMap Nominatim for live coordinate bounds."""
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(place_name)}&format=json&limit=1"
        headers = {
            "User-Agent": "SatQuery-AI/2.0 (Geospatial Intelligence Platform; contact: satquery@example.com)",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data and isinstance(data, list) and len(data) > 0:
                        first = data[0]
                        raw_bbox = first.get("boundingbox", [])
                        lat = float(first.get("lat", 0.0))
                        lon = float(first.get("lon", 0.0))
                        display_name = first.get("display_name", place_name.title())

                        if len(raw_bbox) == 4:
                            s, n, w, e = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])
                            bbox = [w, s, e, n]
                        elif lat != 0.0 or lon != 0.0:
                            delta = 0.05
                            bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
                        else:
                            return None

                        geometry = {
                            "type": "Polygon",
                            "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]],
                        }
                        return GeographicLocation(
                            canonical_name=display_name.split(",")[0].strip(),
                            latitude=lat,
                            longitude=lon,
                            bbox=bbox,
                            geometry=geometry,
                            admin_level="nominatim_resolved",
                            state="",
                            country="",
                            confidence=0.88,
                            source="nominatim_osm",
                            is_valid=True,
                            raw_query=place_name,
                        )
        except Exception as e:
            logger.debug("Nominatim geocoding for '%s' failed: %s", place_name, e)
        return None
