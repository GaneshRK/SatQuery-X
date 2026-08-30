"""Evidence rendering, GeoJSON conversion, metric area quantification, confidence aggregation."""

from __future__ import annotations

import io
import uuid
from typing import Any

import numpy as np
from PIL import Image

from backend.geospatial.ingestion import pixel_bbox_to_geojson
from backend.registry.contracts import ModelOutput
from backend.storage.s3 import ObjectStorage


class EvidenceEngine:
    def __init__(self) -> None:
        self.storage = ObjectStorage()

    def process_output(
        self,
        output: ModelOutput,
        image_metadata: list[dict[str, Any]],
        session_id: uuid.UUID,
        query_id: uuid.UUID,
        step: int,
    ) -> dict[str, Any]:
        bboxes: list[dict] = []
        geojson: list[dict] = []
        artifact_keys: dict[str, str] = {}

        meta = image_metadata[0] if image_metadata else {}

        for box in output.boxes:
            bbox_dict = {
                "x1": box.x1,
                "y1": box.y1,
                "x2": box.x2,
                "y2": box.y2,
                "label": box.label,
                "confidence": box.confidence,
            }
            bboxes.append(bbox_dict)
            geom = pixel_bbox_to_geojson(
                [box.x1, box.y1, box.x2, box.y2],
                meta.get("affine"),
                meta.get("crs"),
                meta.get("bounds_wgs84"),
            )
            geojson.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    **bbox_dict,
                    "model_id": output.model_id,
                    "step": step,
                },
            })

        change_area_km2 = None
        change_area_ha = None
        change_pct = None

        if output.change_mask_bytes:
            key = f"sessions/{session_id}/evidence/{query_id}/step{step}_change_mask.png"
            self.storage.upload_bytes(key, output.change_mask_bytes, "image/png")
            artifact_keys["change_mask"] = self.storage.get_presigned_url(key)

            # Calculate quantified area
            try:
                mask_arr = np.array(Image.open(io.BytesIO(output.change_mask_bytes)).convert("L"))
                changed_pixels = int((mask_arr > 0).sum())
                total_pixels = mask_arr.size
                change_pct = round(float(changed_pixels / total_pixels * 100), 2)

                # Determine pixel resolution in meters
                affine = meta.get("affine")
                if affine and len(affine) >= 6:
                    pixel_size_x = abs(float(affine[1]))
                    pixel_size_y = abs(float(affine[5]))
                    if pixel_size_x < 0.001:  # likely in geographic degrees
                        # Approximate 1 deg ~ 111,320 meters at equator
                        pixel_size_x *= 111320
                        pixel_size_y *= 111320
                    pixel_area_m2 = pixel_size_x * pixel_size_y
                else:
                    # Default to 10m GSD (Sentinel-2 benchmark standard)
                    pixel_area_m2 = 100.0

                total_change_m2 = changed_pixels * pixel_area_m2
                change_area_km2 = round(total_change_m2 / 1_000_000.0, 4)
                change_area_ha = round(total_change_m2 / 10_000.0, 2)
            except Exception:
                pass

        if output.overlay_bytes:
            key = f"sessions/{session_id}/evidence/{query_id}/step{step}_overlay.png"
            self.storage.upload_bytes(key, output.overlay_bytes, "image/png")
            artifact_keys["overlay"] = self.storage.get_presigned_url(key)

        return {
            "bboxes": bboxes,
            "geojson": geojson,
            "artifact_keys": artifact_keys,
            "quantified_area_km2": change_area_km2,
            "quantified_area_hectares": change_area_ha,
            "change_percentage": change_pct,
        }

    @staticmethod
    def aggregate_confidence(confidences: list[float], strategy: str = "min") -> float:
        if not confidences:
            return 0.0
        if strategy == "min":
            return round(min(confidences), 3)
        if strategy == "mean":
            return round(sum(confidences) / len(confidences), 3)
        return round(min(confidences), 3)
