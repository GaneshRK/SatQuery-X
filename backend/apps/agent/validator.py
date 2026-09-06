"""
SatQuery-X Agent Input Validator

Validates whether a requested analysis can actually be executed with the
available evidence.

Rules:
- Never fabricate an image.
- Never fabricate an image pair.
- Zero-upload queries are allowed only when the request contains enough
  spatial/satellite-search context for the planner to retrieve real data.
- Bi-temporal analysis requires two compatible observations OR a legitimate
  satellite/catalogue matching workflow.
- Cross-modal analysis requires optical/multispectral + SAR.
- Spatially incompatible imagery is rejected when footprints are known.
- Missing metadata is not treated as proof of incompatibility.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTONOMOUS_INTENTS = {
    "SATELLITE_SEARCH",
    "LATEST_OBSERVATION",
    "LOCATION_ANALYSIS",
    "MAP_ANALYSIS",
    "EARTH_OBSERVATION",
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "VEGETATION_ANALYSIS",
    "WATER_DETECTION",
    "URBAN_ANALYSIS",
    "THERMAL_HOTSPOT",
    "SAR_ANALYSIS",
}

CHANGE_INTENTS = {
    "CHANGE_DETECTION",
    "CHANGE_VQA",
    "REGION_COMPARISON",
}

CROSS_MODAL_INTENTS = {
    "OPTICAL_SAR_FUSION",
    "CROSS_MODAL_ANALYSIS",
}

CLARIFICATION_INTENTS = {
    "CLARIFICATION",
    "AMBIGUOUS",
}

SPECIAL_VALID_MODES = {
    "CLARIFICATION",
    "FOLLOW_UP_REFINEMENT",
    "REGION_COMPARISON",
    "AUTONOMOUS_EARTH_SEARCH",
    "MODE_A_CHANGE",
    "MODE_B_SATELLITE_MATCHING",
}

SUPPORTED_FILE_FORMATS = {
    "GEOTIFF",
    "GTIFF",
    "TIFF",
    "PNG",
    "JPEG",
    "JPG",
}

OPTICAL_MODALITIES = {
    "OPTICAL",
    "MULTISPECTRAL",
    "RGB",
    "MSI",
    "OPTICAL_MULTISPECTRAL",
}

SAR_MODALITIES = {
    "SAR",
    "RADAR",
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _intent_name(intent: Any) -> str:
    value = getattr(
        intent,
        "intent",
        "",
    )

    return str(
        value or ""
    ).strip().upper()


def _has_location(intent: Any) -> bool:
    """
    Return True only when a location/context object actually exists.

    A string/name is enough for catalogue geocoding/search, while geometry,
    bbox or coordinates are even stronger forms of spatial evidence.
    """

    location = getattr(
        intent,
        "location",
        None,
    )

    if not location:
        return False

    if isinstance(location, str):
        return bool(
            location.strip()
        )

    if isinstance(location, dict):
        for key in (
            "name",
            "place",
            "location",
            "bbox",
            "geometry",
            "coordinates",
            "coords",
            "lat",
            "lon",
            "latitude",
            "longitude",
        ):
            value = location.get(key)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                return True

    return bool(location)


def _has_spatial_context(
    intent: Any,
    session_context: dict[str, Any] | None = None,
) -> bool:
    """
    Check both query-level and session/map-level spatial context.
    """

    if _has_location(intent):
        return True

    context = (
        session_context
        if isinstance(
            session_context,
            dict,
        )
        else {}
    )

    for key in (
        "active_aoi",
        "aoi_geometry",
        "active_region",
        "selected_area",
        "current_viewport",
        "active_pin",
        "selected_location",
    ):
        if context.get(key):
            return True

    visual_state = context.get(
        "current_visual_state"
    )

    if isinstance(
        visual_state,
        dict,
    ):
        for key in (
            "active_pin",
            "selected_location",
            "aoi_geometry",
            "viewport",
            "active_aoi",
        ):
            if visual_state.get(key):
                return True

    return False


def _get_modality(
    image: Any,
) -> str:
    value = getattr(
        image,
        "modality",
        None,
    )

    if value is None:
        return ""

    return str(
        value
    ).strip().upper()


def _is_optical(
    image: Any,
) -> bool:
    return _get_modality(
        image
    ) in OPTICAL_MODALITIES


def _is_sar(
    image: Any,
) -> bool:
    return _get_modality(
        image
    ) in SAR_MODALITIES


def _image_format(
    image: Any,
) -> str:
    value = getattr(
        image,
        "file_format",
        None,
    )

    if value:
        return str(
            value
        ).strip().upper()

    # Some uploaded assets may expose the extension instead.
    filename = (
        getattr(
            image,
            "original_filename",
            None,
        )
        or getattr(
            image,
            "filename",
            None,
        )
        or ""
    )

    filename = str(
        filename
    ).lower()

    if filename.endswith(
        (
            ".tif",
            ".tiff",
        )
    ):
        return "GEOTIFF"

    if filename.endswith(
        ".png"
    ):
        return "PNG"

    if filename.endswith(
        (
            ".jpg",
            ".jpeg",
        )
    ):
        return "JPEG"

    return ""


def _asset_ready(
    image: Any,
) -> bool:
    """
    Validate processing state without requiring one exact historical enum.

    Unknown status is allowed here because older database records may not
    have the same status vocabulary. Actual file loading remains the
    executor's responsibility.
    """

    status = getattr(
        image,
        "processing_status",
        None,
    )

    if status is None:
        return True

    status = str(
        status
    ).strip().upper()

    rejected = {
        "FAILED",
        "ERROR",
        "REJECTED",
        "INVALID",
        "DELETED",
    }

    return status not in rejected


def _asset_has_file(
    image: Any,
) -> bool:
    """
    Check whether an ImageAsset appears to have an actual stored file.

    This does not open the file; executor-level validation does that.
    """

    for field_name in (
        "file",
        "image",
        "raster",
        "asset_file",
        "source_file",
    ):
        field = getattr(
            image,
            field_name,
            None,
        )

        if field is None:
            continue

        try:
            if getattr(
                field,
                "name",
                None,
            ):
                return True

            if getattr(
                field,
                "path",
                None,
            ):
                return True

        except Exception:
            continue

    return False


# ---------------------------------------------------------------------------
# Bounding boxes
# ---------------------------------------------------------------------------


def _normalise_bbox(
    bbox: Any,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None

    if isinstance(
        bbox,
        dict,
    ):
        try:
            return (
                float(bbox["west"]),
                float(bbox["south"]),
                float(bbox["east"]),
                float(bbox["north"]),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    if isinstance(
        bbox,
        (list, tuple),
    ) and len(bbox) >= 4:
        try:
            return (
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    return None


def _asset_bbox(
    image: Any,
) -> Any:
    bbox = getattr(
        image,
        "bounds_wgs84",
        None,
    )

    if bbox:
        return bbox

    provenance = getattr(
        image,
        "provenance",
        None,
    )

    if isinstance(
        provenance,
        dict,
    ):
        for key in (
            "bbox",
            "bounds_wgs84",
            "footprint_bbox",
        ):
            if provenance.get(key):
                return provenance[key]

    return None


def _location_bbox(
    intent: Any,
) -> Any:
    location = getattr(
        intent,
        "location",
        None,
    )

    if not isinstance(
        location,
        dict,
    ):
        return None

    for key in (
        "bbox",
        "bounds",
        "bounds_wgs84",
    ):
        if location.get(key):
            return location[key]

    return None


def _bboxes_intersect(
    first: Any,
    second: Any,
) -> bool:
    """
    If metadata is missing or malformed, return True.

    Unknown is not the same as incompatible.
    """

    a = _normalise_bbox(
        first
    )
    b = _normalise_bbox(
        second
    )

    if a is None or b is None:
        return True

    west_a, south_a, east_a, north_a = a
    west_b, south_b, east_b, north_b = b

    if west_a > east_b:
        return False

    if east_a < west_b:
        return False

    if south_a > north_b:
        return False

    if north_a < south_b:
        return False

    return True


def _pair_overlaps(
    image_a: Any,
    image_b: Any,
) -> bool:
    bbox_a = _asset_bbox(
        image_a
    )

    bbox_b = _asset_bbox(
        image_b
    )

    return _bboxes_intersect(
        bbox_a,
        bbox_b,
    )


# ---------------------------------------------------------------------------
# Pair helpers
# ---------------------------------------------------------------------------


def _pair_images(
    image_pair: Any | None,
    image_assets: list[Any],
) -> tuple[Any | None, Any | None]:
    if image_pair is not None:
        image_a = getattr(
            image_pair,
            "image_a",
            None,
        )

        image_b = getattr(
            image_pair,
            "image_b",
            None,
        )

        if image_a is not None and image_b is not None:
            return image_a, image_b

    if len(image_assets) >= 2:
        return (
            image_assets[0],
            image_assets[1],
        )

    return None, None


def _pair_is_cross_modal(
    image_a: Any,
    image_b: Any,
) -> bool:
    return (
        (
            _is_optical(image_a)
            and _is_sar(image_b)
        )
        or (
            _is_sar(image_a)
            and _is_optical(image_b)
        )
    )


def _pair_is_temporally_valid(
    image_a: Any,
    image_b: Any,
) -> bool:
    """
    Validate chronology only when both acquisition dates exist.

    Missing dates do not automatically invalidate a pair.
    """

    date_a = getattr(
        image_a,
        "acquisition_date",
        None,
    )

    date_b = getattr(
        image_b,
        "acquisition_date",
        None,
    )

    if date_a is None or date_b is None:
        return True

    try:
        return date_a != date_b
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


def validate_agent_inputs(
    intent: Any,
    image_assets: list[Any],
    image_pair: Any | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate whether the requested agent workflow can execute.

    Returns:
        {
            "valid": bool,
            "mode": str,
            "reasons": list[str],
            "warnings": list[str],
            "image_count": int,
            "has_image_pair": bool,
            "autonomous_search_allowed": bool,
        }
    """

    reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(
        image_assets,
        list,
    ):
        image_assets = list(
            image_assets or []
        )

    intent_name = _intent_name(
        intent
    )

    session_context = (
        session_context
        if isinstance(
            session_context,
            dict,
        )
        else {}
    )

    # ---------------------------------------------------------------
    # 0. Explicit clarification
    # ---------------------------------------------------------------

    clarification_required = bool(
        getattr(
            intent,
            "clarification_required",
            False,
        )
    )

    if (
        clarification_required
        or intent_name in CLARIFICATION_INTENTS
    ):
        return {
            "valid": True,
            "mode": "CLARIFICATION",
            "reasons": [],
            "warnings": [],
            "image_count": len(
                image_assets
            ),
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": False,
        }

    # ---------------------------------------------------------------
    # 1. Special conversational intents
    # ---------------------------------------------------------------

    if intent_name == "FOLLOW_UP_REFINEMENT":
        return {
            "valid": True,
            "mode": "FOLLOW_UP_REFINEMENT",
            "reasons": [],
            "warnings": [],
            "image_count": len(
                image_assets
            ),
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": False,
        }

    if intent_name == "REGION_COMPARISON":
        # Region comparison can be a map/AOI workflow without uploaded
        # images, provided spatial context exists.
        if not image_assets and not _has_spatial_context(
            intent,
            session_context,
        ):
            return {
                "valid": False,
                "mode": "REGION_COMPARISON",
                "reasons": [
                    "Region comparison requires a map region, AOI, "
                    "location, or uploaded imagery."
                ],
                "warnings": [],
                "image_count": 0,
                "has_image_pair": image_pair is not None,
                "autonomous_search_allowed": False,
            }

        return {
            "valid": True,
            "mode": "REGION_COMPARISON",
            "reasons": [],
            "warnings": [],
            "image_count": len(
                image_assets
            ),
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": True,
        }

    # ---------------------------------------------------------------
    # 2. Determine requested analysis family
    # ---------------------------------------------------------------

    temporal_requested = bool(
        getattr(
            intent,
            "temporal",
            False,
        )
    ) or intent_name in CHANGE_INTENTS

    cross_modal_requested = bool(
        getattr(
            intent,
            "cross_modal",
            False,
        )
    ) or intent_name in CROSS_MODAL_INTENTS

    spatial_available = _has_spatial_context(
        intent,
        session_context,
    )

    satellite_search_requested = (
        intent_name
        in {
            "SATELLITE_SEARCH",
            "LATEST_OBSERVATION",
            "LOCATION_ANALYSIS",
            "MAP_ANALYSIS",
            "EARTH_OBSERVATION",
        }
    )

    # ---------------------------------------------------------------
    # 3. Determine autonomous mode
    # ---------------------------------------------------------------

    if not image_assets and image_pair is None:
        autonomous_capable = (
            satellite_search_requested
            or spatial_available
            or intent_name in AUTONOMOUS_INTENTS
        )

        if autonomous_capable:
            if temporal_requested:
                return {
                    "valid": True,
                    "mode": "MODE_A_CHANGE",
                    "reasons": [],
                    "warnings": [
                        "No uploaded image pair is available. "
                        "The planner must retrieve real observations "
                        "from a satellite/catalogue provider."
                    ],
                    "image_count": 0,
                    "has_image_pair": False,
                    "autonomous_search_allowed": True,
                }

            return {
                "valid": True,
                "mode": "AUTONOMOUS_EARTH_SEARCH",
                "reasons": [],
                "warnings": [
                    "No uploaded image is available. "
                    "The planner must obtain real satellite/catalogue "
                    "evidence before answering observation questions."
                ],
                "image_count": 0,
                "has_image_pair": False,
                "autonomous_search_allowed": True,
            }

        # Ordinary image analysis without an image cannot execute.
        return {
            "valid": False,
            "mode": "SINGLE_IMAGE",
            "reasons": [
                f"Task '{intent_name or 'UNKNOWN'}' requires an image "
                "or a resolvable satellite/map context."
            ],
            "warnings": [],
            "image_count": 0,
            "has_image_pair": False,
            "autonomous_search_allowed": False,
        }

    # ---------------------------------------------------------------
    # 4. Validate individual image assets
    # ---------------------------------------------------------------

    for index, image in enumerate(
        image_assets
    ):
        if image is None:
            reasons.append(
                f"Image input {index + 1} is empty."
            )
            continue

        if not _asset_ready(
            image
        ):
            reasons.append(
                f"Image input {index + 1} is in a failed or invalid "
                "processing state."
            )

        file_format = _image_format(
            image
        )

        if file_format and file_format not in SUPPORTED_FILE_FORMATS:
            reasons.append(
                f"Unsupported image format '{file_format}' for "
                f"image input {index + 1}."
            )

        if not _asset_has_file(
            image
        ):
            warnings.append(
                f"Image input {index + 1} has no directly visible file "
                "reference; execution may fail if the underlying asset "
                "cannot be opened."
            )

    # ---------------------------------------------------------------
    # 5. Cross-modal validation
    # ---------------------------------------------------------------

    if cross_modal_requested:
        image_a, image_b = _pair_images(
            image_pair,
            image_assets,
        )

        if image_a is None or image_b is None:
            if len(image_assets) == 1:
                return {
                    "valid": True,
                    "mode": "MODE_B_SATELLITE_MATCHING",
                    "reasons": [],
                    "warnings": [
                        "Cross-modal analysis has one uploaded image. "
                        "A real complementary satellite observation must "
                        "be retrieved before fusion."
                    ],
                    "image_count": len(
                        image_assets
                    ),
                    "has_image_pair": False,
                    "autonomous_search_allowed": True,
                }

            reasons.append(
                "Cross-modal fusion requires two observations: "
                "one optical/multispectral and one SAR."
            )

        else:
            if not _pair_is_cross_modal(
                image_a,
                image_b,
            ):
                reasons.append(
                    "Cross-modal fusion requires one "
                    "OPTICAL/MULTISPECTRAL image and one SAR image."
                )

            if not _pair_overlaps(
                image_a,
                image_b,
            ):
                reasons.append(
                    "The optical and SAR images do not geographically "
                    "overlap."
                )

        if reasons:
            return {
                "valid": False,
                "mode": "CROSS_MODAL",
                "reasons": reasons,
                "warnings": warnings,
                "image_count": len(
                    image_assets
                ),
                "has_image_pair": image_pair is not None,
                "autonomous_search_allowed": False,
            }

        return {
            "valid": True,
            "mode": "CROSS_MODAL",
            "reasons": [],
            "warnings": warnings,
            "image_count": len(
                image_assets
            ),
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": False,
        }

    # ---------------------------------------------------------------
    # 6. Bi-temporal / change validation
    # ---------------------------------------------------------------

    if temporal_requested:
        image_a, image_b = _pair_images(
            image_pair,
            image_assets,
        )

        # One uploaded image can legitimately become a catalogue-matching
        # workflow.
        if image_a is not None and image_b is None:
            return {
                "valid": True,
                "mode": "MODE_B_SATELLITE_MATCHING",
                "reasons": [],
                "warnings": [
                    "Only one observation is available. "
                    "A second observation must be retrieved from a real "
                    "satellite/catalogue source."
                ],
                "image_count": len(
                    image_assets
                ),
                "has_image_pair": False,
                "autonomous_search_allowed": True,
            }

        if image_a is None or image_b is None:
            return {
                "valid": False,
                "mode": "BI_TEMPORAL",
                "reasons": [
                    "Bi-temporal analysis requires two observations "
                    "of the same ground area."
                ],
                "warnings": warnings,
                "image_count": len(
                    image_assets
                ),
                "has_image_pair": image_pair is not None,
                "autonomous_search_allowed": False,
            }

        if not _pair_overlaps(
            image_a,
            image_b,
        ):
            reasons.append(
                "The two observations do not geographically overlap. "
                "Change detection requires the same ground footprint."
            )

        if not _pair_is_temporally_valid(
            image_a,
            image_b,
        ):
            reasons.append(
                "The two observations have the same acquisition date. "
                "A bi-temporal comparison requires different observations."
            )

        if reasons:
            return {
                "valid": False,
                "mode": "BI_TEMPORAL",
                "reasons": reasons,
                "warnings": warnings,
                "image_count": len(
                    image_assets
                ),
                "has_image_pair": image_pair is not None,
                "autonomous_search_allowed": False,
            }

        return {
            "valid": True,
            "mode": "BI_TEMPORAL",
            "reasons": [],
            "warnings": warnings,
            "image_count": len(
                image_assets
            ),
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": False,
        }

    # ---------------------------------------------------------------
    # 7. Single-image validation
    # ---------------------------------------------------------------

    if len(
        image_assets
    ) == 0:
        return {
            "valid": False,
            "mode": "SINGLE_IMAGE",
            "reasons": [
                "This analysis requires at least one image."
            ],
            "warnings": warnings,
            "image_count": 0,
            "has_image_pair": image_pair is not None,
            "autonomous_search_allowed": False,
        }

    # If an image pair exists but the intent is not temporal/cross-modal,
    # using the first image as the primary image is acceptable.
    return {
        "valid": len(
            reasons
        ) == 0,
        "mode": "SINGLE_IMAGE",
        "reasons": reasons,
        "warnings": warnings,
        "image_count": len(
            image_assets
        ),
        "has_image_pair": image_pair is not None,
        "autonomous_search_allowed": False,
    }


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------


def validate_inputs(
    intent: Any,
    image_assets: list[Any],
    image_pair: Any | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias."""

    return validate_agent_inputs(
        intent,
        image_assets,
        image_pair,
        session_context,
    )


def validate(
    intent: Any,
    image_assets: list[Any],
    image_pair: Any | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias."""

    return validate_agent_inputs(
        intent,
        image_assets,
        image_pair,
        session_context,
    )