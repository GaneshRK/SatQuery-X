"""Validator component verifying input compatibility per §8.3."""

from __future__ import annotations

from typing import Any


def validate_agent_inputs(
    intent: Any,
    image_assets: list[Any],
    image_pair: Any | None = None,
) -> dict[str, Any]:
    reasons = []
    mode = "SINGLE_IMAGE"

    if intent.temporal or intent.intent in ("change_detection", "change_vqa"):
        mode = "BI_TEMPORAL"
    elif intent.cross_modal or intent.intent == "optical_sar_fusion":
        mode = "CROSS_MODAL"

    # 1. Image count check
    if mode in ("BI_TEMPORAL", "CROSS_MODAL"):
        count = len(image_assets)
        if image_pair:
            count = 2
        if count < 2:
            reasons.append(
                f"Task '{intent.intent}' requires 2 images (mode: {mode}), but only {count} was provided."
            )
    else:
        if len(image_assets) < 1 and not image_pair:
            reasons.append(f"Task '{intent.intent}' requires at least 1 image asset.")

    # 2. Modality & cross-modal validation
    if mode == "CROSS_MODAL" and (len(image_assets) >= 2 or image_pair):
        img_a = image_pair.image_a if image_pair else image_assets[0]
        img_b = image_pair.image_b if image_pair else image_assets[1]

        mods = {getattr(img_a, "modality", "OPTICAL"), getattr(img_b, "modality", "SAR")}
        has_optical = any(m in ("OPTICAL", "MULTISPECTRAL") for m in mods)
        has_sar = "SAR" in mods

        if not (has_optical and has_sar):
            reasons.append(
                f"Cross-modal fusion requires 1 Optical/Multispectral and 1 SAR radar image. Provided: {img_a.modality} and {img_b.modality}."
            )

    # 3. Bi-temporal check
    if mode == "BI_TEMPORAL" and (len(image_assets) >= 2 or image_pair):
        img_a = image_pair.image_a if image_pair else image_assets[0]
        img_b = image_pair.image_b if image_pair else image_assets[1]

        # Check geographic overlap
        if getattr(img_a, "bounds_wgs84", None) and getattr(img_b, "bounds_wgs84", None):
            b_a = img_a.bounds_wgs84
            b_b = img_b.bounds_wgs84
            no_overlap = (
                b_a["west"] > b_b["east"]
                or b_a["east"] < b_b["west"]
                or b_a["south"] > b_b["north"]
                or b_a["north"] < b_b["south"]
            )
            if no_overlap:
                reasons.append(
                    "Bi-temporal images do not geographically overlap. Images must observe the same ground footprint."
                )

    # 4. File format validation
    allowed_formats = {"GEOTIFF", "TIFF", "PNG", "JPEG"}
    for img in image_assets:
        fmt = getattr(img, "file_format", "GEOTIFF")
        if fmt not in allowed_formats:
            reasons.append(
                f"Unsupported file format '{fmt}' on image '{img.original_filename}'. Supported: GeoTIFF, TIFF, PNG, JPEG."
            )

    is_valid = len(reasons) == 0

    return {
        "valid": is_valid,
        "mode": mode,
        "reasons": reasons,
    }
