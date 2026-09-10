"""Runtime modality/relationship routing for SatQuery-X.

The router makes analysis selection from *actual asset metadata*. It never
infers a sensor from image position alone. Unknown modality remains unknown.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _modality(record: dict[str, Any]) -> str:
    explicit = _norm(record.get("modality"))
    if explicit in {"optical", "sar", "thermal", "multispectral", "hyperspectral", "radar"}:
        return "sar" if explicit == "radar" else ("optical" if explicit == "multispectral" else explicit)
    sensor = _norm(record.get("sensor"))
    platform = _norm(record.get("platform"))
    text = f"{sensor} {platform}"
    if any(x in text for x in ("sentinel-1", "sentinel 1", "sar", "synthetic aperture", "radar")):
        return "sar"
    if any(x in text for x in ("sentinel-2", "sentinel 2", "landsat", "planet", "optical")):
        return "optical"
    return "unknown"


def resolve_analysis_route(records: list[dict[str, Any]], requested_relationship: str = "") -> dict[str, Any]:
    records = [r for r in records if isinstance(r, dict)]
    rel = _norm(requested_relationship).upper()
    modalities = [_modality(r) for r in records]
    dates = [_norm(r.get("acquisition_date")) for r in records]

    groups: dict[str, list[int]] = defaultdict(list)
    for i, modality in enumerate(modalities):
        groups[modality].append(i)

    optical = groups.get("optical", [])
    sar = groups.get("sar", [])
    known = [m for m in modalities if m != "unknown"]

    if len(records) == 1:
        route = "SINGLE_IMAGE"
        specialist = "RS_VQA"
    elif len(optical) == 1 and len(sar) == 1:
        route = "CROSS_MODAL_OPTICAL_SAR"
        specialist = "OPTICAL_SAR_FUSION"
    elif len(optical) >= 2 and len(sar) >= 2 and rel in {"BI_TEMPORAL", "TEMPORAL_CROSS_MODAL"}:
        route = "BI_TEMPORAL_OPTICAL_SAR"
        specialist = "COMPOSED_TEMPORAL_MULTIMODAL"
    elif len(records) >= 2 and len(set(known)) == 1 and known and rel in {"BI_TEMPORAL", "TEMPORAL"}:
        route = "BI_TEMPORAL_SAME_MODALITY"
        specialist = "CHANGE_DETECTION"
    elif len(records) >= 2 and len(set(known)) > 1:
        route = "MIXED_MODALITY_UNRESOLVED"
        specialist = None
    elif len(records) >= 2 and not known:
        route = "MULTI_IMAGE_MODALITY_UNKNOWN"
        specialist = None
    else:
        route = rel or "UNKNOWN"
        specialist = None

    return {
        "status": "resolved" if specialist or route in {"SINGLE_IMAGE", "BI_TEMPORAL_SAME_MODALITY", "CROSS_MODAL_OPTICAL_SAR"} else "needs_resolution",
        "route": route,
        "specialist": specialist,
        "asset_count": len(records),
        "modalities": modalities,
        "indices": {
            "optical": optical,
            "sar": sar,
        },
        "acquisition_dates": dates,
        "requested_relationship": rel or None,
        "metadata_only": False,
        "scientific_guard": "unknown modality is never guessed from list position",
    }
