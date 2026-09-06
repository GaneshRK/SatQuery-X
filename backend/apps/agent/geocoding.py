from __future__ import annotations
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Fast-path cache for common SIH demo locations & previously resolved queries
_GEOCODE_CACHE: Dict[str, Dict[str, Any]] = {
    "chennai": {
        "name": "Chennai Metropolitan Region",
        "bbox": [80.15, 12.95, 80.35, 13.15],
        "coords": [80.2707, 13.0827],
    },
    "pollachi": {
        "name": "Pollachi Agricultural Belt",
        "bbox": [76.92, 10.58, 77.08, 10.72],
        "coords": [77.0064, 10.6582],
    },
    "kaziranga": {
        "name": "Kaziranga National Park & Brahmaputra Basin",
        "bbox": [93.05, 26.50, 93.30, 26.65],
        "coords": [93.1711, 26.5775],
    },
    "brahmaputra": {
        "name": "Brahmaputra River Basin",
        "bbox": [93.00, 26.40, 93.40, 26.80],
        "coords": [93.2000, 26.6000],
    },
    "bengaluru": {
        "name": "Bengaluru IT Corridor",
        "bbox": [77.60, 12.85, 77.78, 13.02],
        "coords": [77.6974, 12.9352],
    },
    "bangalore": {
        "name": "Bengaluru IT Corridor",
        "bbox": [77.60, 12.85, 77.78, 13.02],
        "coords": [77.6974, 12.9352],
    },
    "sundarbans": {
        "name": "Sundarbans Mangrove Delta",
        "bbox": [88.70, 21.80, 89.00, 22.10],
        "coords": [88.8532, 21.9497],
    },
    "mumbai": {
        "name": "Mumbai Metropolitan Region",
        "bbox": [72.77, 18.88, 72.99, 19.27],
        "coords": [72.8777, 19.0760],
    },
    "delhi": {
        "name": "Delhi-NCR Urban Belt",
        "bbox": [77.00, 28.40, 77.35, 28.85],
        "coords": [77.2090, 28.6139],
    },
    "delhi-ncr": {
        "name": "Delhi-NCR Urban Belt",
        "bbox": [77.00, 28.40, 77.35, 28.85],
        "coords": [77.2090, 28.6139],
    },
    "kolkata": {
        "name": "Kolkata Metropolitan Area",
        "bbox": [88.25, 22.45, 88.45, 22.65],
        "coords": [88.3639, 22.5726],
    },
    "hyderabad": {
        "name": "Hyderabad Urban Agglomeration",
        "bbox": [78.35, 17.30, 78.55, 17.50],
        "coords": [78.4867, 17.3850],
    },
    "coimbatore": {
        "name": "Coimbatore Industrial Basin",
        "bbox": [76.90, 10.95, 77.05, 11.08],
        "coords": [76.9558, 11.0168],
    },
    "thoothukudi": {
        "name": "Thoothukudi Port & Maritime Industrial Hub",
        "bbox": [78.08, 8.70, 78.22, 8.85],
        "coords": [78.1348, 8.7642],
    },
    "tuticorin": {
        "name": "Thoothukudi Port & Maritime Industrial Hub",
        "bbox": [78.08, 8.70, 78.22, 8.85],
        "coords": [78.1348, 8.7642],
    },
    "tirunelveli": {
        "name": "Tirunelveli Urban Agglomeration",
        "bbox": [77.65, 8.68, 77.80, 8.78],
        "coords": [77.7567, 8.7139],
    },
    "madurai": {
        "name": "Madurai Temple & Industrial Belt",
        "bbox": [78.05, 9.88, 78.20, 10.00],
        "coords": [78.1198, 9.9252],
    },
    "trichy": {
        "name": "Tiruchirappalli Cauvery Basin",
        "bbox": [78.60, 10.75, 78.78, 10.88],
        "coords": [78.7047, 10.7905],
    },
    "tiruchirappalli": {
        "name": "Tiruchirappalli Cauvery Basin",
        "bbox": [78.60, 10.75, 78.78, 10.88],
        "coords": [78.7047, 10.7905],
    },
    "salem": {
        "name": "Salem Steel & Mineral Belt",
        "bbox": [78.10, 11.60, 78.25, 11.72],
        "coords": [78.1460, 11.6643],
    },
    "tiruppur": {
        "name": "Tiruppur Textile Export Hub",
        "bbox": [77.30, 11.08, 77.42, 11.18],
        "coords": [77.3411, 11.1085],
    },
    "vellore": {
        "name": "Vellore Palar Valley",
        "bbox": [79.10, 12.88, 79.20, 12.98],
        "coords": [79.1325, 12.9165],
    },
    "hosur": {
        "name": "Hosur Manufacturing & Tech Corridor",
        "bbox": [77.78, 12.70, 77.88, 12.78],
        "coords": [77.8253, 12.7409],
    },
    "dindigul": {
        "name": "Dindigul Agricultural Valley",
        "bbox": [77.92, 10.32, 78.05, 10.42],
        "coords": [77.9803, 10.3673],
    },
    "erode": {
        "name": "Erode Turmeric & Textile Basin",
        "bbox": [77.68, 11.30, 77.78, 11.40],
        "coords": [77.7172, 11.3410],
    },
    "thanjavur": {
        "name": "Thanjavur Delta Granary",
        "bbox": [79.10, 10.74, 79.20, 10.84],
        "coords": [79.1378, 10.7870],
    },
    "cuddalore": {
        "name": "Cuddalore SIPCOT Coastal Belt",
        "bbox": [79.72, 11.70, 79.82, 11.80],
        "coords": [79.7714, 11.7480],
    },
    "nagapattinam": {
        "name": "Nagapattinam Coastal Delta",
        "bbox": [79.80, 10.72, 79.90, 10.82],
        "coords": [79.8428, 10.7656],
    },
    "kanyakumari": {
        "name": "Kanyakumari Peninsular Cape",
        "bbox": [77.50, 8.05, 77.60, 8.15],
        "coords": [77.5385, 8.0883],
    },
    "kochi": {
        "name": "Kochi Backwaters & Port Hub",
        "bbox": [76.22, 9.90, 76.35, 10.05],
        "coords": [76.2673, 9.9312],
    },
    "visakhapatnam": {
        "name": "Visakhapatnam Deepwater Coast",
        "bbox": [83.25, 17.65, 83.40, 17.78],
        "coords": [83.2185, 17.6868],
    },
    "mangalore": {
        "name": "Mangalore Coastal Port",
        "bbox": [74.80, 12.82, 74.92, 12.95],
        "coords": [74.8560, 12.9141],
    },
    "western ghats": {
        "name": "Western Ghats Ecological Reserve",
        "bbox": [76.80, 10.20, 77.20, 10.60],
        "coords": [77.0000, 10.4000],
    },
}


def parse_explicit_coordinates(text: str) -> Optional[Dict[str, Any]]:
    """
    Detect explicit coordinates in text such as:
    - [80.15, 12.95, 80.35, 13.15] (bbox)
    - 13.0827, 80.2707 or 13.0827 N, 80.2707 E (point)
    """
    # 1. Bounding box [w, s, e, n]
    bbox_match = re.search(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", text)
    if bbox_match:
        vals = [float(bbox_match.group(i)) for i in range(1, 5)]
        w, s, e, n = vals[0], vals[1], vals[2], vals[3]
        return {
            "name": f"Custom Bounding Box [{w:.3f}, {s:.3f}, {e:.3f}, {n:.3f}]",
            "bbox": [w, s, e, n],
            "coords": [(w + e) / 2.0, (s + n) / 2.0],
            "source": "explicit_bbox",
        }

    # 2. Point coordinate (lat, lon)
    pt_match = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*(?:°)?\s*([NSns])?\s*[,/ ]\s*(-?\d{1,3}(?:\.\d+)?)\s*(?:°)?\s*([EWew])?", text)
    if pt_match:
        val1 = float(pt_match.group(1))
        dir1 = pt_match.group(2)
        val2 = float(pt_match.group(3))
        dir2 = pt_match.group(4)

        if dir1 and dir1.upper() == "S":
            val1 = -val1
        if dir2 and dir2.upper() == "W":
            val2 = -val2

        # Verify lat between -90 and 90, lon between -180 and 180
        if -90 <= val1 <= 90 and -180 <= val2 <= 180:
            lat, lon = val1, val2
            delta = 0.05
            return {
                "name": f"Coordinate Location ({lat:.4f}, {lon:.4f})",
                "bbox": [lon - delta, lat - delta, lon + delta, lat + delta],
                "coords": [lon, lat],
                "source": "explicit_point",
            }

    return None


def query_nominatim(place_name: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """
    Query OpenStreetMap Nominatim for a place name to obtain bounding box and centroid.
    """
    clean_name = place_name.strip()
    cache_key = clean_name.lower()
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(clean_name)}&format=json&limit=1"
    headers = {
        "User-Agent": "SatQuery-AI/2.0 (Geospatial Intelligence Assistant; contact: satquery@example.com)",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    # Nominatim boundingbox: [south, north, west, east]
                    raw_bbox = first.get("boundingbox", [])
                    lat = float(first.get("lat", 0.0))
                    lon = float(first.get("lon", 0.0))
                    display_name = first.get("display_name", clean_name)

                    if len(raw_bbox) == 4:
                        s, n, w, e = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])
                        result = {
                            "name": display_name,
                            "bbox": [w, s, e, n],
                            "coords": [lon, lat],
                            "source": "nominatim",
                        }
                        _GEOCODE_CACHE[cache_key] = result
                        return result
                    elif lat != 0.0 or lon != 0.0:
                        delta = 0.05
                        result = {
                            "name": display_name,
                            "bbox": [lon - delta, lat - delta, lon + delta, lat + delta],
                            "coords": [lon, lat],
                            "source": "nominatim",
                        }
                        _GEOCODE_CACHE[cache_key] = result
                        return result
    except Exception as e:
        logger.warning("Nominatim geocoding request for '%s' failed: %s", place_name, e)

    return None


def extract_location_candidate(text: str) -> Optional[str]:
    """
    Extract a location candidate string from query text using prepositional and question patterns.
    Completely case-insensitive.
    """
    q_clean = text.strip()
    patterns = [
        r"^(?:what|how)\s+about\s+([a-zA-Z0-9\s\-]{2,30})",
        r"^(?:and|what\s+of)\s+(?:in\s+)?([a-zA-Z0-9\s\-]{2,30})",
        r"(?:what\s+(?:so|is\s+the|are\s+the)?\s*changes?\s+in|what\s+changed\s+in|changes?\s+in)\s+([a-zA-Z0-9\s\-]{2,30})",
        r"(?:compare|difference between|versus|vs\.?)\s+([a-zA-Z0-9\s\-]{2,30})\s+(?:to|and|with|vs\.?)",
        r"\b(?:around|in|over|near|for|of|across|at|to)\b\s+the\s+([a-zA-Z0-9\s\-]{2,30})",
        r"\b(?:around|in|over|near|for|of|across|at|to)\b\s+([a-zA-Z0-9\s\-]{2,30})",
        r"(?:flood(?:ing)?|urban expansion|deforestation|water levels?|vegetation)\s+(?:around|in|over|near|of)\s+([a-zA-Z0-9\s\-]{3,30})",
    ]
    stopwords = {
        "the", "a", "an", "this", "that", "these", "those", "here", "there",
        "image", "satellite", "scene", "area", "region", "map", "viewport", "date",
        "dates", "two", "both", "all", "it", "them", "which", "what", "how", "why",
        "is", "are", "was", "were", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "shall", "should", "may", "might", "must", "can", "could",
        "changing", "changed", "change"
    }
    for pat in patterns:
        m = re.search(pat, q_clean, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            # Clean up punctuation/trailing question marks
            cand = re.sub(r"[\?\.\,\!]+$", "", cand).strip()
            cand_words = set(re.findall(r"\b[a-zA-Z0-9]+\b", cand.lower()))
            if not cand_words or cand_words.issubset(stopwords) or cand.lower() in stopwords:
                continue
            if len(cand) >= 3:
                return cand
    return None


def resolve_location(
    text: str,
    session_context: Optional[Dict[str, Any]] = None,
    allow_network: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Multi-stage location resolution:
    1. Parse explicit coordinates/bbox
    2. Extract explicit candidate from query text and resolve via LocationResolver (typo-tolerant)
    3. Direct full-string resolution via LocationResolver
    4. Session context active AOI / map viewport (only when query has no explicit location candidate)
    5. Nominatim live geocoding fallback
    """
    session_context = session_context or {}
    q = text.lower().strip()

    # 1. Check explicit coordinates
    coords_loc = parse_explicit_coordinates(text)
    if coords_loc:
        return coords_loc

    # 2. Extract candidate place name from query text (prioritized over session context)
    from apps.agent.location_resolver import LocationResolver
    cand = extract_location_candidate(text)
    if cand:
        resolved_cand = LocationResolver.resolve(cand, allow_fuzzy=True, allow_network=allow_network)
        if resolved_cand and resolved_cand.is_valid:
            return resolved_cand.to_dict()

        # Cache check fallback
        cand_lower = cand.lower().strip()
        if cand_lower in _GEOCODE_CACHE:
            return _GEOCODE_CACHE[cand_lower]
        for key, loc in _GEOCODE_CACHE.items():
            if re.search(rf"\b{re.escape(key)}\b", cand_lower):
                return loc

        # Query Nominatim
        if allow_network:
            geo_res = query_nominatim(cand)
            if geo_res:
                return geo_res

    # 3. Check direct query match in LocationResolver (e.g. "thoothukudi", "coimbature")
    resolved_direct = LocationResolver.resolve(q, allow_fuzzy=True, allow_network=allow_network)
    if resolved_direct and resolved_direct.is_valid:
        return resolved_direct.to_dict()

    for key, loc in _GEOCODE_CACHE.items():
        if re.search(rf"\b{re.escape(key)}\b", q):
            return loc

    # 4. Only if NO explicit location was in the query text, check active session context
    if session_context.get("active_aoi"):
        return session_context["active_aoi"]

    if session_context.get("aoi_name") and session_context.get("bbox"):
        return {
            "name": session_context["aoi_name"],
            "bbox": session_context["bbox"],
            "coords": session_context.get("centroid", [
                (session_context["bbox"][0] + session_context["bbox"][2]) / 2.0,
                (session_context["bbox"][1] + session_context["bbox"][3]) / 2.0,
            ]),
            "source": "session_context",
        }

    # Check map viewport from visual context or session
    vis_state = session_context.get("current_visual_state") or session_context.get("visual_context") or {}
    viewport = session_context.get("current_viewport") or vis_state.get("current_viewport") or session_context.get("viewport")
    if viewport and isinstance(viewport, dict):
        bbox = viewport.get("bbox")
        if not bbox and all(k in viewport for k in ("west", "south", "east", "north")):
            bbox = [float(viewport["west"]), float(viewport["south"]), float(viewport["east"]), float(viewport["north"])]
        if bbox and len(bbox) == 4:
            coords = viewport.get("center") or viewport.get("coords") or [
                (float(bbox[0]) + float(bbox[2])) / 2.0,
                (float(bbox[1]) + float(bbox[3])) / 2.0,
            ]
            return {
                "name": f"Interactive Map Viewport ({coords[1]:.3f}°N, {coords[0]:.3f}°E)",
                "bbox": [float(b) for b in bbox],
                "coords": [float(c) for c in coords],
                "source": "map_viewport",
            }

    # Check drawn AOI geometry polygon
    aoi_geom = session_context.get("aoi_geometry")
    if aoi_geom and isinstance(aoi_geom, dict):
        poly_coords = aoi_geom.get("coordinates")
        if poly_coords and isinstance(poly_coords, list) and len(poly_coords) > 0:
            ring = poly_coords[0]
            lngs = [float(p[0]) for p in ring]
            lats = [float(p[1]) for p in ring]
            bbox = [min(lngs), min(lats), max(lngs), max(lats)]
            coords = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
            return {
                "name": f"Designated Area of Interest ({coords[1]:.3f}°N, {coords[0]:.3f}°E)",
                "bbox": bbox,
                "coords": coords,
                "source": "aoi_geometry",
            }

    return None
