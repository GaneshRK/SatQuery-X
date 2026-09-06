"""
SatQuery-X Query Understanding Agent.

Converts a user's natural-language request into a structured QueryIntent
that can safely be consumed by the Master Agent and Planner.

Design principles
-----------------
1. Understanding never creates scientific evidence.
2. Explicit coordinates/AOI/place references have priority over context.
3. "Here", "this place", "this area", etc. resolve from actual map/session
   context when available.
4. Uploaded imagery is treated as available input, never as evidence by
   itself until an analysis tool actually processes it.
5. Temporal ranges are extracted from the request or inherited from actual
   conversation/session context. No arbitrary scientific comparison window
   is invented.
6. Satellite retrieval is requested when real-world imagery is needed and
   usable uploaded observations are not already available.
7. Ambiguous or insufficient requests become clarification requests.
8. The module is deterministic and auditable.
9. The understanding layer never fabricates coordinates, dates, sensors,
   imagery, measurements, confidence, or scientific conclusions.
10. Map pin/AOI context is treated as first-class conversation context.
11. "Latest" means latest available catalogue observation; it does not
    invent a date.
12. Modality availability must come from actual metadata/context and is
    never inferred merely from image count.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


# ============================================================================
# Query Intent
# ============================================================================


@dataclass
class QueryIntent:
    """
    Structured representation of a user's request.

    This object describes WHAT should be done.

    It deliberately does not contain:
    - fabricated measurements
    - fabricated coordinates
    - fabricated satellite observations
    - fabricated confidence values
    - fabricated image-analysis results
    """

    intent: str = "UNKNOWN"

    target: str | None = None

    operation: str | None = None

    temporal: bool = False

    cross_modal: bool = False

    spatial_filter: dict[str, Any] = field(default_factory=dict)

    requested_output: list[str] = field(default_factory=list)

    raw_text: str = ""

    is_follow_up: bool = False

    location: dict[str, Any] = field(default_factory=dict)

    time_range: dict[str, Any] = field(default_factory=dict)

    clarification_required: bool = False

    clarification_prompt: str | None = None

    clarification_options: list[str] = field(default_factory=list)

    geo_intent: str | None = None

    missing_data: list[str] = field(default_factory=list)

    auto_search_required: bool = False

    multi_locations: list[dict[str, Any]] = field(default_factory=list)

    context_source: list[str] = field(default_factory=list)


# ============================================================================
# Vocabulary
# ============================================================================


DEICTIC_TERMS = {
    "here",
    "this place",
    "this area",
    "this location",
    "this point",
    "selected area",
    "selected location",
    "selected point",
    "current map",
    "map area",
    "that place",
    "that area",
    "that location",
    "the place",
    "the area",
    "the selected area",
    "the highlighted area",
    "this scene",
    "this map",
    "this region",
    "the region",
}

FOLLOW_UP_TERMS = {
    "it",
    "this",
    "that",
    "these",
    "those",
    "them",
    "here",
    "there",
    "same area",
    "same place",
    "same location",
    "same image",
    "same scene",
    "previous image",
    "previous scene",
    "earlier image",
    "earlier scene",
    "previous result",
    "earlier result",
    "what about",
    "and what about",
    "also",
    "again",
    "now",
    "continue",
    "compare with",
    "compared with",
}

CHANGE_TERMS = {
    "change",
    "changed",
    "changes",
    "change detection",
    "difference",
    "differences",
    "before and after",
    "earlier and now",
    "then and now",
    "compare over time",
    "temporal change",
    "land cover change",
    "landcover change",
    "construction over time",
    "growth over time",
    "deforestation",
    "urban expansion",
    "expansion over time",
    "shrink",
    "shrinking",
    "loss over time",
    "gain over time",
    "decrease over time",
    "increase over time",
    "historical comparison",
    "temporal comparison",
}

VEGETATION_TERMS = {
    "vegetation",
    "greenery",
    "green cover",
    "plant",
    "plants",
    "crop",
    "crops",
    "forest",
    "forested",
    "tree",
    "trees",
    "vegetated",
    "ndvi",
    "agriculture",
    "agricultural",
    "farmland",
    "farm",
    "forest cover",
}

WATER_TERMS = {
    "water",
    "lake",
    "lakes",
    "river",
    "rivers",
    "pond",
    "ponds",
    "reservoir",
    "reservoirs",
    "wetland",
    "wetlands",
    "coastline",
    "waterbody",
    "water bodies",
    "ndwi",
    "flood",
    "flooding",
    "flooded",
}

URBAN_TERMS = {
    "urban",
    "building",
    "buildings",
    "structure",
    "structures",
    "road",
    "roads",
    "city",
    "cities",
    "settlement",
    "settlements",
    "built up",
    "built-up",
    "construction",
    "urban area",
    "urbanization",
    "urbanisation",
    "ndbi",
    "built environment",
}

THERMAL_TERMS = {
    "thermal",
    "temperature",
    "hotspot",
    "hotspots",
    "heat",
    "heat anomaly",
    "thermal anomaly",
    "surface temperature",
    "land surface temperature",
    "lst",
    "fire hotspot",
    "thermal hotspot",
    "thermal imagery",
}

SAR_TERMS = {
    "sar",
    "synthetic aperture radar",
    "radar",
    "sentinel-1",
    "sentinel 1",
    "vv",
    "vh",
    "backscatter",
    "sar imagery",
    "sar image",
}

OPTICAL_TERMS = {
    "optical",
    "multispectral",
    "multispectral image",
    "multispectral imagery",
    "sentinel-2",
    "sentinel 2",
    "landsat",
    "true color",
    "false color",
    "rgb",
    "nir",
    "red edge",
    "optical imagery",
    "optical image",
}

GROUNDING_TERMS = {
    "where",
    "locate",
    "location of",
    "find",
    "highlight",
    "bounding box",
    "bounding boxes",
    "bbox",
    "ground",
    "grounding",
    "point out",
    "show me where",
    "mark",
    "identify where",
    "identify the location",
}

COUNT_TERMS = {
    "count",
    "counts",
    "number of",
    "how many",
    "enumerate",
    "quantity of",
}

SATELLITE_TERMS = {
    "satellite",
    "satellite image",
    "satellite imagery",
    "satellite scene",
    "satellite data",
    "earth observation",
    "earth observation data",
    "sentinel",
    "sentinel-1",
    "sentinel-2",
    "sentinel 1",
    "sentinel 2",
    "landsat",
    "modis",
    "remote sensing",
    "remote sensing image",
    "remote sensing imagery",
    "latest imagery",
    "latest satellite",
    "latest observation",
    "recent imagery",
    "recent satellite image",
    "newest imagery",
    "newest satellite",
    "near real time",
    "near-real-time",
    "earth observation imagery",
}

LATEST_TERMS = {
    "latest",
    "latest imagery",
    "latest satellite",
    "latest observation",
    "latest available",
    "most recent",
    "recent imagery",
    "recent satellite image",
    "newest imagery",
    "newest satellite",
    "near real time",
    "near-real-time",
}

WEB_KNOWLEDGE_TERMS = {
    "explain",
    "what is",
    "what are",
    "meaning of",
    "definition of",
    "how does",
    "how do",
    "why is",
    "why are",
    "learn about",
    "information about",
    "knowledge about",
    "tell me about",
    "research",
    "according to",
    "documentation",
}

CROSS_MODAL_INTENTS = {
    "OPTICAL_SAR_FUSION",
    "CROSS_MODAL_ANALYSIS",
}

CHANGE_INTENTS = {
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "REGION_COMPARISON",
}

SPATIAL_INTENTS = {
    "LOCATION_ANALYSIS",
    "MAP_ANALYSIS",
    "SATELLITE_SEARCH",
    "LATEST_OBSERVATION",
    "EARTH_OBSERVATION",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "REGION_COMPARISON",
    "VEGETATION_ANALYSIS",
    "WATER_DETECTION",
    "URBAN_ANALYSIS",
    "THERMAL_HOTSPOT",
    "SAR_ANALYSIS",
}

IMAGE_ANALYSIS_INTENTS = {
    "VQA",
    "CAPTION",
    "GROUNDING",
    "VEGETATION_ANALYSIS",
    "WATER_DETECTION",
    "URBAN_ANALYSIS",
    "THERMAL_HOTSPOT",
    "SAR_ANALYSIS",
    "OPTICAL_SAR_FUSION",
    "CROSS_MODAL_ANALYSIS",
}


# ============================================================================
# Generic helpers
# ============================================================================


def _normalise_text(text: str) -> str:
    """Normalize whitespace and casing without destroying information."""

    value = str(text or "").strip().lower()
    value = re.sub(r"\s+", " ", value)

    return value


def _unique(values: list[Any]) -> list[Any]:
    """Preserve order while removing duplicates."""

    result: list[Any] = []

    for value in values:
        if value not in result:
            result.append(value)

    return result


def _contains_any(
    text: str,
    terms: set[str],
) -> bool:
    """Case-insensitive token/phrase matching."""

    normalized = _normalise_text(text)

    for term in terms:
        term_normalized = _normalise_text(term)

        if not term_normalized:
            continue

        if (
            " " in term_normalized
            or "-" in term_normalized
        ):
            if term_normalized in normalized:
                return True

        else:
            if re.search(
                rf"\b{re.escape(term_normalized)}\b",
                normalized,
            ):
                return True

    return False


def _today() -> date:
    """Centralized date provider for deterministic testing."""

    return date.today()


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to an integer."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ============================================================================
# Session/context helpers
# ============================================================================


def _conversation_history(
    session_context: dict[str, Any],
) -> list[dict[str, Any]]:
    history = session_context.get(
        "conversation_history",
        [],
    )

    if not isinstance(history, list):
        return []

    return [
        item
        for item in history
        if isinstance(item, dict)
    ]


def _last_user_query(
    session_context: dict[str, Any],
) -> str | None:
    history = _conversation_history(
        session_context
    )

    for turn in reversed(history):
        for key in (
            "query_text",
            "text",
            "query",
            "user_query",
        ):
            value = turn.get(key)

            if (
                isinstance(value, str)
                and value.strip()
            ):
                return value.strip()

    return None


def _image_count(
    session_context: dict[str, Any],
) -> int:
    """
    Return actual image count supplied by the caller/context.

    A boolean `has_images=True` is treated as one or more images but does not
    allow the understanding layer to fabricate an exact count.
    """

    count = session_context.get(
        "image_count"
    )

    if count is not None:
        parsed = _safe_int(count)

        if parsed >= 0:
            return parsed

    for key in (
        "image_assets",
        "images",
        "uploaded_images",
        "image_ids",
    ):
        assets = session_context.get(key)

        if isinstance(
            assets,
            (list, tuple),
        ):
            return len(assets)

    if session_context.get(
        "has_images"
    ):
        return 1

    return 0


def _has_images(
    session_context: dict[str, Any],
) -> bool:
    return _image_count(
        session_context
    ) > 0


def _image_assets(
    session_context: dict[str, Any],
) -> list[Any]:
    for key in (
        "image_assets",
        "images",
        "uploaded_images",
    ):
        value = session_context.get(key)

        if isinstance(
            value,
            (list, tuple),
        ):
            return list(value)

    return []


def _viewport(
    session_context: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "current_viewport",
        "viewport",
        "map_viewport",
    ):
        value = session_context.get(key)

        if isinstance(
            value,
            dict,
        ) and value:
            return dict(value)

    return {}


def _active_aoi(
    session_context: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "active_aoi",
        "selected_aoi",
        "aoi",
    ):
        value = session_context.get(key)

        if isinstance(
            value,
            dict,
        ) and value:
            return dict(value)

    return {}


def _map_pin(
    session_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Return an actual active map pin if one exists.

    No coordinates are generated here.
    """

    for key in (
        "map_pin",
        "active_map_pin",
        "selected_pin",
        "map_point",
        "selected_point",
    ):
        value = session_context.get(key)

        if isinstance(
            value,
            dict,
        ) and value:
            return dict(value)

    return {}


def _spatial_context_candidates(
    session_context: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Collect actual spatial context candidates.

    Ordering matters:
        active AOI
        active map pin
        selected point/AOI
        viewport
        persisted previous location
        conversation history
    """

    candidates: list[
        tuple[str, dict[str, Any]]
    ] = []

    aoi = _active_aoi(
        session_context
    )

    if aoi:
        candidates.append(
            ("active_aoi", aoi)
        )

    pin = _map_pin(
        session_context
    )

    if pin:
        candidates.append(
            ("map_pin", pin)
        )

    viewport = _viewport(
        session_context
    )

    if viewport:
        candidates.append(
            (
                "map_viewport",
                {
                    **viewport,
                    "viewport": viewport,
                },
            )
        )

    for key in (
        "last_location",
        "previous_location",
        "last_spatial_context",
    ):
        value = session_context.get(key)

        if isinstance(
            value,
            dict,
        ) and value:
            candidates.append(
                (key, dict(value))
            )

    history = _conversation_history(
        session_context
    )

    for turn in reversed(history):
        location = turn.get(
            "location"
        )

        if isinstance(
            location,
            dict,
        ) and location:
            candidates.append(
                (
                    "conversation_history",
                    dict(location),
                )
            )
            break

    return candidates


def _resolve_context_location(
    session_context: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    candidates = _spatial_context_candidates(
        session_context
    )

    if not candidates:
        return {}, []

    source, location = candidates[0]

    result = dict(location)

    result.setdefault(
        "source",
        source,
    )

    return result, [source]


def _has_spatial_context(
    session_context: dict[str, Any],
) -> bool:
    location, _ = _resolve_context_location(
        session_context
    )

    return bool(location)


def _context_modalities(
    session_context: dict[str, Any],
) -> dict[str, bool]:
    """
    Return modality availability only from explicit metadata/context.

    Example accepted structure:

        {
            "modalities": {
                "optical": True,
                "sar": False
            }
        }

    Image metadata may also provide a modality field.
    """

    result = {
        "optical": False,
        "sar": False,
        "thermal": False,
    }

    modalities = session_context.get(
        "modalities"
    )

    if isinstance(
        modalities,
        dict,
    ):
        for key in result:
            if modalities.get(key) is True:
                result[key] = True

    for asset in _image_assets(
        session_context
    ):
        if not isinstance(
            asset,
            dict,
        ):
            continue

        modality = str(
            asset.get(
                "modality",
                ""
            )
        ).strip().lower()

        sensor = str(
            asset.get(
                "sensor",
                ""
            )
        ).strip().lower()

        combined = f"{modality} {sensor}"

        if (
            "sar" in combined
            or "radar" in combined
            or "sentinel-1" in combined
        ):
            result["sar"] = True

        if (
            "optical" in combined
            or "multispectral" in combined
            or "sentinel-2" in combined
            or "landsat" in combined
        ):
            result["optical"] = True

        if "thermal" in combined:
            result["thermal"] = True

    return result


# ============================================================================
# Explicit coordinate / geometry extraction
# ============================================================================


def _extract_coordinates(
    text: str,
) -> dict[str, Any]:
    """
    Extract explicit latitude/longitude.

    Supported forms:
        11.0168, 76.9558
        lat 11.0168 lon 76.9558
        latitude: 11.0168 longitude: 76.9558
        coordinates 11.0168, 76.9558

    No coordinates are ever generated.
    """

    patterns = [
        (
            r"(?:lat(?:itude)?\s*[:=]?\s*)"
            r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)"
            r".{0,40}?"
            r"(?:lon(?:gitude)?\s*[:=]?\s*)"
            r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
        ),
        (
            r"(?:lon(?:gitude)?\s*[:=]?\s*)"
            r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
            r".{0,40}?"
            r"(?:lat(?:itude)?\s*[:=]?\s*)"
            r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)"
        ),
        (
            r"(?:coordinates?|coords?)\s*[:=]?\s*"
            r"\[?\s*"
            r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)"
            r"\s*[, ]\s*"
            r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
            r"\s*\]?"
        ),
        (
            r"(?<![\w.])"
            r"(?P<lat>[+-]?\d{1,2}\.\d+)"
            r"\s*[,;]\s*"
            r"(?P<lon>[+-]?\d{1,3}\.\d+)"
            r"(?![\w.])"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        try:
            lat = float(
                match.group("lat")
            )
            lon = float(
                match.group("lon")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if not (
            -90.0 <= lat <= 90.0
        ):
            continue

        if not (
            -180.0 <= lon <= 180.0
        ):
            continue

        return {
            "lat": lat,
            "lon": lon,
            "coordinates": [
                lon,
                lat,
            ],
            "source": (
                "explicit_query_coordinates"
            ),
        }

    return {}


def _extract_bbox(
    text: str,
) -> dict[str, Any]:
    """
    Detect explicit bbox=[west,south,east,north].

    The values must be supplied by the user.
    """

    pattern = (
        r"(?:bbox|bounding\s+box)"
        r"\s*[:=]\s*"
        r"\[?\s*"
        r"(?P<w>-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(?P<s>-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(?P<e>-?\d+(?:\.\d+)?)\s*[, ]\s*"
        r"(?P<n>-?\d+(?:\.\d+)?)"
        r"\s*\]?"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return {}

    try:
        west = float(
            match.group("w")
        )
        south = float(
            match.group("s")
        )
        east = float(
            match.group("e")
        )
        north = float(
            match.group("n")
        )
    except (
        TypeError,
        ValueError,
    ):
        return {}

    if not (
        -180.0 <= west <= 180.0
        and -180.0 <= east <= 180.0
        and -90.0 <= south <= 90.0
        and -90.0 <= north <= 90.0
    ):
        return {}

    if (
        west > east
        or south > north
    ):
        return {}

    return {
        "bbox": [
            west,
            south,
            east,
            north,
        ],
        "source": "explicit_query_bbox",
    }


# ============================================================================
# Natural-language location extraction
# ============================================================================


def _extract_location_phrase(
    text: str,
) -> str | None:
    """
    Extract a conservative candidate place phrase.

    This function does NOT geocode the phrase.

    Actual geocoding belongs to the location-resolution layer.
    """

    patterns = [
        (
            r"\b(?:in|near|around|over|at|within)\s+"
            r"([A-Za-z][A-Za-z0-9 .,'-]{1,100})"
        ),
        (
            r"\b(?:of)\s+"
            r"([A-Za-z][A-Za-z0-9 .,'-]{1,100})"
        ),
    ]

    stop_words = {
        "and",
        "with",
        "for",
        "from",
        "using",
        "during",
        "between",
        "compared",
        "compare",
        "show",
        "tell",
        "please",
        "the",
        "in",
        "on",
        "at",
        "over",
        "now",
        "today",
        "yesterday",
        "tomorrow",
        "last",
        "this",
        "that",
        "using",
        "satellite",
        "imagery",
        "image",
        "images",
    }

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        value = match.group(1).strip(
            " .,;:!?\"'"
        )

        words = value.split()

        while (
            words
            and words[-1].lower()
            in stop_words
        ):
            words.pop()

        value = " ".join(
            words
        ).strip()

        if len(value) < 2:
            continue

        if len(value.split()) > 8:
            continue

        return value

    return None


# ============================================================================
# Temporal extraction
# ============================================================================


def _parse_year_range(
    text: str,
) -> dict[str, Any]:
    """Parse explicit year ranges."""

    patterns = [
        (
            r"\b(19\d{2}|20\d{2})"
            r"\s*(?:to|-|–|—|through)"
            r"\s*(19\d{2}|20\d{2})\b"
        ),
        (
            r"\bfrom\s+"
            r"(19\d{2}|20\d{2})"
            r"\s+(?:to|until|through)\s+"
            r"(19\d{2}|20\d{2})\b"
        ),
        (
            r"\bbetween\s+"
            r"(19\d{2}|20\d{2})"
            r"\s+and\s+"
            r"(19\d{2}|20\d{2})\b"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        start_year = int(
            match.group(1)
        )
        end_year = int(
            match.group(2)
        )

        if start_year > end_year:
            start_year, end_year = (
                end_year,
                start_year,
            )

        return {
            "start": (
                f"{start_year}-01-01"
            ),
            "end": (
                f"{end_year}-12-31"
            ),
            "start_year": start_year,
            "end_year": end_year,
            "source": (
                "explicit_year_range"
            ),
        }

    return {}


def _parse_single_year(
    text: str,
) -> dict[str, Any]:
    """Parse a standalone explicit year."""

    match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        text,
    )

    if not match:
        return {}

    year = int(
        match.group(1)
    )

    return {
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "year": year,
        "source": "explicit_year",
    }


def _parse_relative_time(
    text: str,
) -> dict[str, Any]:
    """
    Resolve only user-requested relative calendar periods.

    This is not a satellite comparison-window generator.
    """

    today = _today()

    if (
        "last year" in text
        or "past year" in text
    ):
        year = today.year - 1

        return {
            "start": (
                f"{year}-01-01"
            ),
            "end": (
                f"{year}-12-31"
            ),
            "source": (
                "relative_last_year"
            ),
        }

    if "this year" in text:
        return {
            "start": (
                f"{today.year}-01-01"
            ),
            "end": (
                f"{today.year}-12-31"
            ),
            "source": (
                "relative_this_year"
            ),
        }

    if (
        "last month" in text
        or "past month" in text
    ):
        end = (
            today.replace(day=1)
            - timedelta(days=1)
        )
        start = end.replace(
            day=1
        )

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "source": (
                "relative_last_month"
            ),
        }

    if (
        "last week" in text
        or "past week" in text
    ):
        start = (
            today
            - timedelta(days=7)
        )

        return {
            "start": start.isoformat(),
            "end": today.isoformat(),
            "source": (
                "relative_last_week"
            ),
        }

    month_match = re.search(
        r"\blast\s+(\d+)\s+months?\b",
        text,
    )

    if month_match:
        months = int(
            month_match.group(1)
        )

        if 1 <= months <= 120:
            year = today.year
            month = (
                today.month - months
            )

            while month <= 0:
                month += 12
                year -= 1

            start = date(
                year,
                month,
                min(today.day, 28),
            )

            return {
                "start": (
                    start.isoformat()
                ),
                "end": (
                    today.isoformat()
                ),
                "months": months,
                "source": (
                    "relative_month_window"
                ),
            }

    day_match = re.search(
        r"\blast\s+(\d+)\s+days?\b",
        text,
    )

    if day_match:
        days = int(
            day_match.group(1)
        )

        if 1 <= days <= 3650:
            start = (
                today
                - timedelta(days=days)
            )

            return {
                "start": (
                    start.isoformat()
                ),
                "end": (
                    today.isoformat()
                ),
                "days": days,
                "source": (
                    "relative_day_window"
                ),
            }

    return {}


def _resolve_time_range(
    text: str,
    session_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Resolve temporal context in priority order:

    1. Explicit date range.
    2. Explicit year range.
    3. Relative range.
    4. Single year.
    5. Existing session temporal context.
    6. Empty.

    No arbitrary temporal window is created.
    """

    normalized = _normalise_text(
        text
    )

    date_range_patterns = [
        (
            r"\b(?:from|between)\s+"
            r"(?P<start>\d{4}-\d{2}-\d{2})"
            r"\s+(?:to|and|through|until)\s+"
            r"(?P<end>\d{4}-\d{2}-\d{2})\b"
        ),
        (
            r"\b(?P<start>\d{4}-\d{2}-\d{2})"
            r"\s*(?:to|through|until|-|–|—)"
            r"\s*(?P<end>\d{4}-\d{2}-\d{2})\b"
        ),
    ]

    for pattern in date_range_patterns:
        match = re.search(
            pattern,
            normalized,
        )

        if not match:
            continue

        start = match.group(
            "start"
        )
        end = match.group(
            "end"
        )

        try:
            start_date = date.fromisoformat(
                start
            )
            end_date = date.fromisoformat(
                end
            )
        except ValueError:
            continue

        if start_date > end_date:
            start_date, end_date = (
                end_date,
                start_date,
            )

        return {
            "start": (
                start_date.isoformat()
            ),
            "end": (
                end_date.isoformat()
            ),
            "source": (
                "explicit_date_range"
            ),
        }

    year_range = _parse_year_range(
        normalized
    )

    if year_range:
        return year_range

    relative = _parse_relative_time(
        normalized
    )

    if relative:
        return relative

    single_year = _parse_single_year(
        normalized
    )

    if single_year:
        return single_year

    for key in (
        "time_range",
        "last_time_range",
        "previous_time_range",
    ):
        value = session_context.get(
            key
        )

        if isinstance(
            value,
            dict,
        ) and value:
            return dict(value)

    history = _conversation_history(
        session_context
    )

    for turn in reversed(history):
        value = turn.get(
            "time_range"
        )

        if isinstance(
            value,
            dict,
        ) and value:
            return dict(value)

    return {}


# ============================================================================
# Sensor / modality extraction
# ============================================================================


def _extract_requested_sensor(
    text: str,
) -> str | None:
    """
    Return a sensor only when explicitly mentioned.

    No default sensor is assigned.
    """

    normalized = _normalise_text(
        text
    )

    sensor_patterns = [
        (
            r"\bsentinel[-\s]?1\b",
            "SENTINEL-1",
        ),
        (
            r"\bsentinel[-\s]?2\b",
            "SENTINEL-2",
        ),
        (
            r"\blandsat(?:[-\s]?[0-9]+)?\b",
            "LANDSAT",
        ),
        (
            r"\bmodis\b",
            "MODIS",
        ),
    ]

    for pattern, sensor in sensor_patterns:
        if re.search(
            pattern,
            normalized,
        ):
            return sensor

    return None


def _extract_requested_modality(
    text: str,
) -> str | None:
    normalized = _normalise_text(
        text
    )

    has_sar = _contains_any(
        normalized,
        SAR_TERMS,
    )

    has_optical = _contains_any(
        normalized,
        OPTICAL_TERMS,
    )

    has_thermal = _contains_any(
        normalized,
        THERMAL_TERMS,
    )

    if (
        has_sar
        and has_optical
    ):
        return "MULTIMODAL"

    if has_sar:
        return "SAR"

    if has_optical:
        return "OPTICAL"

    if has_thermal:
        return "THERMAL"

    return None


# ============================================================================
# Intent classification
# ============================================================================


def _classify_intent(
    text: str,
    has_images: bool,
    has_spatial: bool,
) -> tuple[
    str,
    str | None,
    str | None,
]:
    """
    Classify the task category.

    This does not perform analysis.
    """

    normalized = _normalise_text(
        text
    )

    has_sar = _contains_any(
        normalized,
        SAR_TERMS,
    )

    has_optical = _contains_any(
        normalized,
        OPTICAL_TERMS,
    )

    # ------------------------------------------------------------------
    # Explicit cross-modal optical + SAR
    # ------------------------------------------------------------------

    if (
        has_sar
        and has_optical
        and any(
            phrase in normalized
            for phrase in (
                "fuse",
                "fusion",
                "combine",
                "combined",
                "cross modal",
                "cross-modal",
                "together",
                "compare optical and sar",
                "optical and sar",
                "optical with sar",
            )
        )
    ):
        return (
            "OPTICAL_SAR_FUSION",
            "optical_sar",
            "fuse",
        )

    # ------------------------------------------------------------------
    # Change / temporal comparison
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        CHANGE_TERMS,
    ):
        if any(
            phrase in normalized
            for phrase in (
                "why did",
                "what caused",
                "why has",
                "explain the change",
                "explain why",
                "cause of change",
            )
        ):
            return (
                "CHANGE_VQA",
                "surface_change",
                "explain",
            )

        return (
            "CHANGE_DETECTION",
            "surface_change",
            "compare",
        )

    if (
        "compare" in normalized
        and (
            "region" in normalized
            or "area" in normalized
            or "place" in normalized
            or "location" in normalized
        )
    ):
        return (
            "REGION_COMPARISON",
            "regions",
            "compare",
        )

    # ------------------------------------------------------------------
    # Grounding
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        GROUNDING_TERMS,
    ) and any(
        phrase in normalized
        for phrase in (
            "building",
            "buildings",
            "road",
            "roads",
            "water",
            "lake",
            "river",
            "forest",
            "tree",
            "trees",
            "crop",
            "damage",
            "construction",
            "structure",
            "structures",
            "area",
            "object",
            "objects",
        )
    ):
        return (
            "GROUNDING",
            "target_object",
            "locate",
        )

    # ------------------------------------------------------------------
    # Vegetation
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        VEGETATION_TERMS,
    ):
        return (
            "VEGETATION_ANALYSIS",
            "vegetation",
            "analyze",
        )

    # ------------------------------------------------------------------
    # Water
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        WATER_TERMS,
    ):
        return (
            "WATER_DETECTION",
            "water",
            "detect",
        )

    # ------------------------------------------------------------------
    # Urban
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        URBAN_TERMS,
    ):
        if _contains_any(
            normalized,
            COUNT_TERMS,
        ):
            return (
                "URBAN_ANALYSIS",
                "structures",
                "detect_and_count",
            )

        return (
            "URBAN_ANALYSIS",
            "built_environment",
            "analyze",
        )

    # ------------------------------------------------------------------
    # Thermal
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        THERMAL_TERMS,
    ):
        return (
            "THERMAL_HOTSPOT",
            "thermal",
            "analyze",
        )

    # ------------------------------------------------------------------
    # SAR
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        SAR_TERMS,
    ):
        return (
            "SAR_ANALYSIS",
            "sar",
            "analyze",
        )

    # ------------------------------------------------------------------
    # Latest observation
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        LATEST_TERMS,
    ):
        return (
            "LATEST_OBSERVATION",
            "satellite_observation",
            "search_latest",
        )

    # ------------------------------------------------------------------
    # Satellite retrieval
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        SATELLITE_TERMS,
    ):
        return (
            "SATELLITE_SEARCH",
            "satellite_observation",
            "search",
        )

    # ------------------------------------------------------------------
    # Location / map analysis
    # ------------------------------------------------------------------

    if has_spatial and (
        "what is this" in normalized
        or "what is here" in normalized
        or "what place is this" in normalized
        or "what area is this" in normalized
        or "what is this place" in normalized
        or "what is this area" in normalized
        or "what is this location" in normalized
        or "what is the land use" in normalized
        or "what is this area used for" in normalized
        or "what is located here" in normalized
        or "what is located in this area" in normalized
    ):
        return (
            "LOCATION_ANALYSIS",
            "place",
            "interpret",
        )

    # ------------------------------------------------------------------
    # Caption
    # ------------------------------------------------------------------

    if has_images and any(
        phrase in normalized
        for phrase in (
            "caption this",
            "caption the image",
            "caption the scene",
            "describe this image",
            "describe the image",
            "describe this scene",
            "describe the scene",
            "what does the image show",
            "what is shown in the image",
        )
    ):
        return (
            "CAPTION",
            "scene",
            "describe",
        )

    # ------------------------------------------------------------------
    # Generic image question
    # ------------------------------------------------------------------

    if has_images:
        return (
            "VQA",
            "scene",
            "answer_question",
        )

    # ------------------------------------------------------------------
    # Generic map/AOI question
    # ------------------------------------------------------------------

    if has_spatial:
        return (
            "MAP_ANALYSIS",
            "map_region",
            "interpret",
        )

    # ------------------------------------------------------------------
    # Knowledge / text
    # ------------------------------------------------------------------

    if _contains_any(
        normalized,
        WEB_KNOWLEDGE_TERMS,
    ):
        return (
            "TEXT_QUERY",
            None,
            "explain",
        )

    # ------------------------------------------------------------------
    # Default
    # ------------------------------------------------------------------

    return (
        "TEXT_QUERY",
        None,
        "understand",
    )


# ============================================================================
# Output inference
# ============================================================================


def _requested_outputs(
    text: str,
    intent_name: str,
) -> list[str]:
    outputs: list[str] = []

    normalized = _normalise_text(
        text
    )

    if _contains_any(
        normalized,
        {
            "map",
            "show",
            "visualize",
            "visualise",
            "overlay",
            "highlight",
            "polygon",
            "polygons",
            "boundary",
            "boundaries",
        },
    ):
        outputs.append("map")

    if _contains_any(
        normalized,
        {
            "area",
            "size",
            "square kilometer",
            "square kilometers",
            "sq km",
            "km2",
            "hectare",
            "hectares",
            "acre",
            "acres",
        },
    ):
        outputs.append("area")

    if _contains_any(
        normalized,
        COUNT_TERMS,
    ):
        outputs.append("count")

    if _contains_any(
        normalized,
        {
            "percentage",
            "percent",
            "%",
            "proportion",
            "ratio",
        },
    ):
        outputs.append("percentage")

    if _contains_any(
        normalized,
        {
            "confidence",
            "certainty",
            "uncertainty",
        },
    ):
        outputs.append("confidence")

    if _contains_any(
        normalized,
        {
            "coordinates",
            "coordinate",
            "latitude",
            "longitude",
            "lat lon",
        },
    ):
        outputs.append("coordinates")

    if intent_name in CHANGE_INTENTS:
        outputs.extend(
            [
                "change_map",
                "change_summary",
            ]
        )

    if intent_name == "VEGETATION_ANALYSIS":
        outputs.append(
            "vegetation_analysis"
        )

    if intent_name == "WATER_DETECTION":
        outputs.append(
            "water_analysis"
        )

    if intent_name == "URBAN_ANALYSIS":
        outputs.append(
            "urban_analysis"
        )

    if intent_name == "THERMAL_HOTSPOT":
        outputs.append(
            "thermal_analysis"
        )

    if intent_name == "SAR_ANALYSIS":
        outputs.append(
            "sar_analysis"
        )

    if intent_name == "GROUNDING":
        outputs.append(
            "grounded_regions"
        )

    if intent_name in CROSS_MODAL_INTENTS:
        outputs.append(
            "cross_modal_analysis"
        )

    if intent_name in {
        "SATELLITE_SEARCH",
        "LATEST_OBSERVATION",
        "EARTH_OBSERVATION",
    }:
        outputs.append(
            "satellite_observation"
        )

    if not outputs:
        outputs.append("answer")

    return _unique(outputs)


# ============================================================================
# Follow-up detection
# ============================================================================


def _is_follow_up(
    text: str,
    session_context: dict[str, Any],
) -> bool:
    history = _conversation_history(
        session_context
    )

    if not history:
        return False

    normalized = _normalise_text(
        text
    )

    if _contains_any(
        normalized,
        FOLLOW_UP_TERMS,
    ):
        return True

    words = normalized.split()

    if len(words) <= 7:
        previous = _last_user_query(
            session_context
        )

        if previous:
            return True

    return False


# ============================================================================
# Follow-up inheritance
# ============================================================================


def _inherit_follow_up_context(
    intent: QueryIntent,
    session_context: dict[str, Any],
) -> None:
    """
    Carry forward actual spatial/temporal context.

    Current explicit user input always has priority.
    """

    if not intent.location:
        for key in (
            "last_location",
            "previous_location",
            "last_spatial_context",
        ):
            previous_location = (
                session_context.get(key)
            )

            if isinstance(
                previous_location,
                dict,
            ) and previous_location:
                intent.location = dict(
                    previous_location
                )
                intent.context_source.append(
                    key
                )
                break

    if not intent.time_range:
        for key in (
            "last_time_range",
            "previous_time_range",
        ):
            previous_time_range = (
                session_context.get(key)
            )

            if isinstance(
                previous_time_range,
                dict,
            ) and previous_time_range:
                intent.time_range = dict(
                    previous_time_range
                )
                intent.context_source.append(
                    key
                )
                break

    if not intent.target:
        history = _conversation_history(
            session_context
        )

        for turn in reversed(history):
            previous_target = turn.get(
                "target"
            )

            if previous_target:
                intent.target = str(
                    previous_target
                )
                intent.context_source.append(
                    "previous_target"
                )
                break


# ============================================================================
# Multi-location detection
# ============================================================================


def _extract_multiple_locations(
    text: str,
) -> list[dict[str, Any]]:
    """
    Detect simple comparison forms containing two candidate locations.

    Candidate strings are not treated as validated geographic entities.
    """

    normalized = _normalise_text(
        text
    )

    patterns = [
        (
            r"\bbetween\s+"
            r"([a-zA-Z][a-zA-Z0-9 .,'-]{1,60})"
            r"\s+and\s+"
            r"([a-zA-Z][a-zA-Z0-9 .,'-]{1,60})"
        ),
        (
            r"\bcompare\s+"
            r"([a-zA-Z][a-zA-Z0-9 .,'-]{1,60})"
            r"\s+(?:with|and|vs|versus)\s+"
            r"([a-zA-Z][a-zA-Z0-9 .,'-]{1,60})"
        ),
    ]

    stop_words = {
        "for",
        "during",
        "in",
        "on",
        "from",
        "using",
        "with",
        "over",
        "change",
        "changes",
        "imagery",
        "satellite",
        "satellite imagery",
        "the",
        "area",
        "region",
    }

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
        )

        if not match:
            continue

        first = match.group(
            1
        ).strip(
            " .,;:!?\"'"
        )

        second = match.group(
            2
        ).strip(
            " .,;:!?\"'"
        )

        first_words = [
            word
            for word in first.split()
            if word not in stop_words
        ]

        second_words = [
            word
            for word in second.split()
            if word not in stop_words
        ]

        first = " ".join(
            first_words
        ).strip()

        second = " ".join(
            second_words
        ).strip()

        if (
            len(first) >= 2
            and len(second) >= 2
        ):
            values = _unique(
                [
                    first,
                    second,
                ]
            )

            return [
                {
                    "name": value,
                    "source": (
                        "query_candidate"
                    ),
                }
                for value in values
            ]

    return []


# ============================================================================
# Missing-data analysis
# ============================================================================


def _determine_missing_data(
    intent: QueryIntent,
    has_images: bool,
    session_context: dict[str, Any],
) -> list[str]:
    missing: list[str] = []

    has_spatial = bool(
        intent.location
        or _has_spatial_context(
            session_context
        )
    )

    image_count = _image_count(
        session_context
    )

    modalities = _context_modalities(
        session_context
    )

    # ------------------------------------------------------------------
    # Spatial tasks
    # ------------------------------------------------------------------

    if intent.intent in {
        "LOCATION_ANALYSIS",
        "MAP_ANALYSIS",
    } and not has_spatial:
        missing.append(
            "spatial_context"
        )

    # Satellite search can operate only when a search target/location is
    # available. We do not force a sensor.
    if intent.intent in {
        "SATELLITE_SEARCH",
        "LATEST_OBSERVATION",
        "EARTH_OBSERVATION",
    } and not has_spatial:
        missing.append(
            "spatial_context"
        )

    # ------------------------------------------------------------------
    # Image-analysis tasks
    # ------------------------------------------------------------------

    if (
        intent.intent in IMAGE_ANALYSIS_INTENTS
        and not has_images
        and not has_spatial
    ):
        missing.append(
            "image_or_spatial_context"
        )

    # ------------------------------------------------------------------
    # Change analysis
    # ------------------------------------------------------------------

    if intent.intent in {
        "CHANGE_DETECTION",
        "CHANGE_VQA",
    }:
        if image_count >= 2:
            pass

        elif image_count == 1:
            if has_spatial:
                intent.auto_search_required = True
                missing.append(
                    "second_observation"
                )
            else:
                missing.extend(
                    [
                        "second_observation",
                        "spatial_context",
                    ]
                )

        else:
            if has_spatial:
                intent.auto_search_required = True
                missing.extend(
                    [
                        "before_observation",
                        "after_observation",
                    ]
                )
            else:
                missing.extend(
                    [
                        "before_observation",
                        "after_observation",
                        "spatial_context",
                    ]
                )

    # ------------------------------------------------------------------
    # Cross-modal
    # ------------------------------------------------------------------

    if intent.intent in CROSS_MODAL_INTENTS:
        optical_available = modalities[
            "optical"
        ]
        sar_available = modalities[
            "sar"
        ]

        if not optical_available:
            missing.append(
                "optical_observation"
            )

        if not sar_available:
            missing.append(
                "sar_observation"
            )

        if (
            has_spatial
            and (
                not optical_available
                or not sar_available
            )
        ):
            intent.auto_search_required = True

    # ------------------------------------------------------------------
    # Spatial analysis without image can use actual catalogue retrieval.
    # ------------------------------------------------------------------

    if (
        intent.intent
        in {
            "VEGETATION_ANALYSIS",
            "WATER_DETECTION",
            "URBAN_ANALYSIS",
            "THERMAL_HOTSPOT",
            "SAR_ANALYSIS",
        }
        and not has_images
        and has_spatial
    ):
        intent.auto_search_required = True

    return _unique(
        missing
    )


# ============================================================================
# Automatic satellite retrieval
# ============================================================================


def _should_auto_search(
    intent: QueryIntent,
    has_images: bool,
    session_context: dict[str, Any],
) -> bool:
    """
    Determine whether a real satellite catalogue lookup is needed.

    This function does not perform retrieval.
    """

    has_spatial = bool(
        intent.location
        or _has_spatial_context(
            session_context
        )
    )

    image_count = _image_count(
        session_context
    )

    if not has_spatial:
        return False

    if intent.intent in {
        "SATELLITE_SEARCH",
        "LATEST_OBSERVATION",
        "EARTH_OBSERVATION",
    }:
        return True

    if intent.intent in {
        "LOCATION_ANALYSIS",
        "MAP_ANALYSIS",
    } and not has_images:
        return True

    if intent.intent in {
        "CHANGE_DETECTION",
        "CHANGE_VQA",
    }:
        return image_count < 2

    if intent.intent in CROSS_MODAL_INTENTS:
        modalities = _context_modalities(
            session_context
        )

        return not (
            modalities["optical"]
            and modalities["sar"]
        )

    if (
        intent.intent
        in {
            "VEGETATION_ANALYSIS",
            "WATER_DETECTION",
            "URBAN_ANALYSIS",
            "THERMAL_HOTSPOT",
            "SAR_ANALYSIS",
        }
        and not has_images
    ):
        return True

    return False


# ============================================================================
# Clarification
# ============================================================================


def _build_clarification(
    intent: QueryIntent,
    text: str,
    has_images: bool,
    session_context: dict[str, Any],
) -> None:
    missing = intent.missing_data

    if not missing:
        return

    # ------------------------------------------------------------------
    # Change analysis
    # ------------------------------------------------------------------

    if intent.intent in {
        "CHANGE_DETECTION",
        "CHANGE_VQA",
    }:
        if (
            "spatial_context" in missing
            and not intent.auto_search_required
        ):
            intent.clarification_required = True
            intent.clarification_prompt = (
                "To analyze change, I need either two "
                "observations to compare or a specific "
                "map location/AOI."
            )
            intent.clarification_options = [
                "Upload two images",
                "Drop a pin on the map",
                "Select an AOI",
                "Enter a location or coordinates",
            ]
            return

        if (
            "second_observation" in missing
            and not intent.auto_search_required
        ):
            intent.clarification_required = True
            intent.clarification_prompt = (
                "I have one observation, but change analysis "
                "requires a second observation for comparison."
            )
            intent.clarification_options = [
                "Upload the second image",
                "Provide a location and time period",
            ]
            return

    # ------------------------------------------------------------------
    # Cross-modal
    # ------------------------------------------------------------------

    if intent.intent in CROSS_MODAL_INTENTS:
        if not intent.auto_search_required:
            intent.clarification_required = True
            intent.clarification_prompt = (
                "This analysis requires both optical and SAR "
                "observations."
            )
            intent.clarification_options = [
                "Upload optical and SAR imagery",
                "Provide a location so available imagery can be searched",
            ]
            return

    # ------------------------------------------------------------------
    # Image or spatial context
    # ------------------------------------------------------------------

    if "image_or_spatial_context" in missing:
        intent.clarification_required = True
        intent.clarification_prompt = (
            "I need an uploaded image or a map location/AOI "
            "before I can perform this analysis."
        )
        intent.clarification_options = [
            "Upload an image",
            "Drop a pin on the map",
            "Select an AOI",
        ]
        return

    # ------------------------------------------------------------------
    # Generic spatial context
    # ------------------------------------------------------------------

    if (
        "spatial_context" in missing
        and not intent.auto_search_required
    ):
        intent.clarification_required = True
        intent.clarification_prompt = (
            "Which location or area are you referring to?"
        )
        intent.clarification_options = [
            "Drop a pin",
            "Select an AOI",
            "Enter a location or coordinates",
        ]


# ============================================================================
# Public understanding function
# ============================================================================


def understand_query(
    text: str,
    session_context: dict[str, Any] | None = None,
) -> QueryIntent:
    """
    Understand a natural-language SatQuery-X request.

    Parameters
    ----------
    text:
        User's natural-language request.

    session_context:
        Persisted session state containing actual information such as:
        - conversation_history
        - active_aoi
        - map_pin
        - current_viewport
        - uploaded image count/assets
        - previous location
        - previous time range
        - modality availability

    Returns
    -------
    QueryIntent
        Structured intent consumed by the Master Agent and Planner.
    """

    if not isinstance(
        session_context,
        dict,
    ):
        session_context = {}

    raw_text = str(
        text or ""
    ).strip()

    normalized = _normalise_text(
        raw_text
    )

    # ------------------------------------------------------------------
    # Empty request
    # ------------------------------------------------------------------

    if not normalized:
        return QueryIntent(
            intent="CLARIFICATION",
            raw_text=raw_text,
            clarification_required=True,
            clarification_prompt=(
                "What would you like me to analyze?"
            ),
            clarification_options=[
                "Analyze an uploaded image",
                "Analyze a map location",
                "Compare observations",
                "Search satellite imagery",
            ],
        )

    has_images = _has_images(
        session_context
    )

    image_count = _image_count(
        session_context
    )

    # ------------------------------------------------------------------
    # Existing spatial context
    # ------------------------------------------------------------------

    (
        context_location,
        context_sources,
    ) = _resolve_context_location(
        session_context
    )

    has_spatial = bool(
        context_location
    )

    # ------------------------------------------------------------------
    # Classify intent
    # ------------------------------------------------------------------

    (
        intent_name,
        target,
        operation,
    ) = _classify_intent(
        normalized,
        has_images,
        has_spatial,
    )

    # ------------------------------------------------------------------
    # Explicit spatial input
    # ------------------------------------------------------------------

    location_sources: list[str] = []

    explicit_coordinates = (
        _extract_coordinates(
            normalized
        )
    )

    explicit_bbox = _extract_bbox(
        normalized
    )

    explicit_location_phrase = (
        _extract_location_phrase(
            normalized
        )
    )

    if explicit_coordinates:
        location = explicit_coordinates
        location_sources.append(
            "explicit_query_coordinates"
        )

    elif explicit_bbox:
        location = explicit_bbox
        location_sources.append(
            "explicit_query_bbox"
        )

    elif explicit_location_phrase:
        location = {
            "name": explicit_location_phrase,
            "source": (
                "explicit_query_location"
            ),
        }
        location_sources.append(
            "explicit_query_location"
        )

    else:
        references_map = (
            _contains_any(
                normalized,
                DEICTIC_TERMS,
            )
            or _contains_any(
                normalized,
                {
                    "map",
                    "pin",
                    "point",
                    "aoi",
                    "region",
                    "area",
                    "selected",
                    "highlighted",
                },
            )
        )

        if (
            references_map
            and context_location
        ):
            location = dict(
                context_location
            )
            location_sources.extend(
                context_sources
            )

        elif (
            _is_follow_up(
                normalized,
                session_context,
            )
            and context_location
        ):
            location = dict(
                context_location
            )
            location_sources.extend(
                context_sources
            )

        else:
            location = {}

    if location:
        has_spatial = True

    # ------------------------------------------------------------------
    # Temporal context
    # ------------------------------------------------------------------

    time_range = _resolve_time_range(
        normalized,
        session_context,
    )

    # ------------------------------------------------------------------
    # Follow-up
    # ------------------------------------------------------------------

    follow_up = _is_follow_up(
        normalized,
        session_context,
    )

    # ------------------------------------------------------------------
    # Temporal flag
    # ------------------------------------------------------------------

    temporal = (
        intent_name
        in {
            "CHANGE_DETECTION",
            "CHANGE_VQA",
            "REGION_COMPARISON",
        }
        or bool(time_range)
    )

    # ------------------------------------------------------------------
    # Cross-modal flag
    # ------------------------------------------------------------------

    cross_modal = (
        intent_name
        in CROSS_MODAL_INTENTS
        or (
            _contains_any(
                normalized,
                SAR_TERMS,
            )
            and (
                "optical" in normalized
                or "multispectral"
                in normalized
            )
        )
    )

    # ------------------------------------------------------------------
    # Geo intent
    # ------------------------------------------------------------------

    geo_intent: str | None = None

    if location:
        if (
            location.get("lat")
            is not None
            or location.get("lon")
            is not None
        ):
            geo_intent = "POINT"

        elif location.get(
            "bbox"
        ):
            geo_intent = "BBOX"

        elif location.get(
            "geometry"
        ):
            geo_intent = "AOI"

        elif location.get(
            "viewport"
        ):
            geo_intent = "VIEWPORT"

        elif location.get(
            "name"
        ):
            geo_intent = "PLACE"

    # ------------------------------------------------------------------
    # Spatial filter
    # ------------------------------------------------------------------

    spatial_filter: dict[
        str,
        Any,
    ] = {}

    if location:
        spatial_filter = dict(
            location
        )

    # Context geometry/viewport may be retained when it is actually
    # supplied by the active context.
    if context_location:
        if (
            "geometry"
            in context_location
            and "geometry"
            not in spatial_filter
        ):
            spatial_filter[
                "geometry"
            ] = context_location[
                "geometry"
            ]

        if (
            "viewport"
            in context_location
            and "viewport"
            not in spatial_filter
        ):
            spatial_filter[
                "viewport"
            ] = context_location[
                "viewport"
            ]

    # ------------------------------------------------------------------
    # Requested outputs
    # ------------------------------------------------------------------

    requested_output = (
        _requested_outputs(
            normalized,
            intent_name,
        )
    )

    # ------------------------------------------------------------------
    # Multiple locations
    # ------------------------------------------------------------------

    multi_locations = (
        _extract_multiple_locations(
            normalized
        )
    )

    if multi_locations:
        context_sources.append(
            "multiple_location_candidates"
        )

    # ------------------------------------------------------------------
    # Context source
    # ------------------------------------------------------------------

    context_source = _unique(
        context_sources
        + location_sources
    )

    if follow_up:
        context_source.append(
            "conversation_history"
        )

    if has_images:
        context_source.append(
            "uploaded_imagery"
        )

    if image_count >= 2:
        context_source.append(
            "multiple_uploaded_images"
        )

    if _viewport(
        session_context
    ):
        context_source.append(
            "map_viewport"
        )

    if _map_pin(
        session_context
    ):
        context_source.append(
            "map_pin"
        )

    if _active_aoi(
        session_context
    ):
        context_source.append(
            "active_aoi"
        )

    # ------------------------------------------------------------------
    # Build structured intent
    # ------------------------------------------------------------------

    intent = QueryIntent(
        intent=intent_name,
        target=target,
        operation=operation,
        temporal=temporal,
        cross_modal=cross_modal,
        spatial_filter=spatial_filter,
        requested_output=requested_output,
        raw_text=raw_text,
        is_follow_up=follow_up,
        location=location,
        time_range=time_range,
        geo_intent=geo_intent,
        multi_locations=multi_locations,
        context_source=_unique(
            context_source
        ),
    )

    # ------------------------------------------------------------------
    # Explicit sensor/modality metadata is stored in spatial_filter only
    # when requested, so the planner can use it without assuming defaults.
    # ------------------------------------------------------------------

    requested_sensor = (
        _extract_requested_sensor(
            normalized
        )
    )

    requested_modality = (
        _extract_requested_modality(
            normalized
        )
    )

    if requested_sensor:
        intent.spatial_filter[
            "requested_sensor"
        ] = requested_sensor

    if requested_modality:
        intent.spatial_filter[
            "requested_modality"
        ] = requested_modality

    # ------------------------------------------------------------------
    # Follow-up inheritance
    # ------------------------------------------------------------------

    if follow_up:
        _inherit_follow_up_context(
            intent,
            session_context,
        )

        if intent.location:
            if not intent.spatial_filter:
                intent.spatial_filter = dict(
                    intent.location
                )

            if not intent.geo_intent:
                if (
                    intent.location.get(
                        "lat"
                    )
                    is not None
                    or intent.location.get(
                        "lon"
                    )
                    is not None
                ):
                    intent.geo_intent = (
                        "POINT"
                    )

                elif intent.location.get(
                    "bbox"
                ):
                    intent.geo_intent = (
                        "BBOX"
                    )

                elif intent.location.get(
                    "geometry"
                ):
                    intent.geo_intent = (
                        "AOI"
                    )

                elif intent.location.get(
                    "viewport"
                ):
                    intent.geo_intent = (
                        "VIEWPORT"
                    )

                elif intent.location.get(
                    "name"
                ):
                    intent.geo_intent = (
                        "PLACE"
                    )

    # ------------------------------------------------------------------
    # Automatic satellite retrieval
    # ------------------------------------------------------------------

    intent.auto_search_required = (
        _should_auto_search(
            intent,
            has_images,
            session_context,
        )
    )

    # ------------------------------------------------------------------
    # Missing data
    # ------------------------------------------------------------------

    intent.missing_data = (
        _determine_missing_data(
            intent,
            has_images,
            session_context,
        )
    )

    # ------------------------------------------------------------------
    # If catalogue retrieval can satisfy missing observations, do not
    # incorrectly force the user to upload them.
    # ------------------------------------------------------------------

    if intent.auto_search_required:
        intent.missing_data = [
            item
            for item in intent.missing_data
            if item
            not in {
                "second_observation",
                "before_observation",
                "after_observation",
                "optical_observation",
                "sar_observation",
            }
        ]

    # ------------------------------------------------------------------
    # Clarification
    # ------------------------------------------------------------------

    _build_clarification(
        intent,
        normalized,
        has_images,
        session_context,
    )

    # ------------------------------------------------------------------
    # Temporal provenance
    # ------------------------------------------------------------------

    if time_range:
        intent.context_source.append(
            "time_context"
        )

    if requested_sensor:
        intent.context_source.append(
            "explicit_sensor_constraint"
        )

    if requested_modality:
        intent.context_source.append(
            "explicit_modality_constraint"
        )

    intent.context_source = _unique(
        intent.context_source
    )

    return intent


# ============================================================================
# Serialization
# ============================================================================


def intent_to_dict(
    intent: QueryIntent,
) -> dict[str, Any]:
    """Convert QueryIntent to a JSON-safe dictionary."""

    data = asdict(
        intent
    )

    return _json_safe(
        data
    )


def _json_safe(
    value: Any,
) -> Any:
    """
    Recursively convert common Python/numpy values into JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _json_safe(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    try:
        import numpy as np

        if isinstance(
            value,
            np.ndarray,
        ):
            return value.tolist()

        if isinstance(
            value,
            np.generic,
        ):
            return value.item()

    except ImportError:
        pass

    try:
        return str(value)
    except Exception:
        return None


# ============================================================================
# Compatibility aliases
# ============================================================================


def parse_query(
    text: str,
    session_context: dict[str, Any] | None = None,
) -> QueryIntent:
    """Compatibility alias for older callers."""

    return understand_query(
        text,
        session_context,
    )


def classify_query(
    text: str,
    session_context: dict[str, Any] | None = None,
) -> QueryIntent:
    """Compatibility alias for older callers."""

    return understand_query(
        text,
        session_context,
    )


__all__ = [
    "QueryIntent",
    "understand_query",
    "parse_query",
    "classify_query",
    "intent_to_dict",
]