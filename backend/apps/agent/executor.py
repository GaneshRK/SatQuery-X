"""Executor component orchestrating specialist models per §8.4."""

from __future__ import annotations

import json
import time
from typing import Any

from django.utils import timezone
import redis

from apps.agent.contracts import ModelInput, ModelOutput
from apps.agent.registry import get_model_wrapper
from apps.evidence.models import EvidenceRegion
from apps.geospatial.math import polygonize_mask_to_geojson, quantify_mask_area
from apps.queries.models import ExecutionStep, Query


def publish_query_event(redis_client: redis.Redis | None, query_id: str, event_data: dict[str, Any]) -> None:
    if redis_client:
        try:
            channel = f"query:{query_id}:events"
            redis_client.publish(channel, json.dumps(event_data))
        except Exception:
            pass


def execute_plan(query: Query, plan: dict[str, Any], image_assets: list[Any], image_pair: Any | None = None) -> dict[str, Any]:
    from django.conf import settings

    # Connect to Redis for live SSE streaming
    redis_client = None
    try:
        redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        redis_client = redis.from_url(redis_url, socket_connect_timeout=0.1, socket_timeout=0.1)
    except Exception:
        pass

    steps = plan.get("steps", [])
    step_outputs: dict[str, Any] = {}
    confidences: list[float] = []
    final_answer = ""
    last_mask_bytes: bytes | None = None

    # Prepare image file paths
    image_paths: list[str] = []
    if image_pair:
        if image_pair.image_a and image_pair.image_a.file:
            image_paths.append(image_pair.image_a.file.path)
        if image_pair.image_b and image_pair.image_b.file:
            image_paths.append(image_pair.image_b.file.path)
    elif image_assets:
        for img in image_assets:
            if img.file:
                image_paths.append(img.file.path)

    primary_img = image_assets[0] if image_assets else (image_pair.image_a if image_pair else None)

    for item in steps:
        step_num = item["step"]
        tool_name = item["tool"]
        params = item.get("parameters", {})

        # 1. Create ExecutionStep row in RUNNING state
        step_row = ExecutionStep.objects.create(
            query=query,
            step_number=step_num,
            tool_name=tool_name,
            model_version="1.0-baseline",
            parameters=params,
            status="RUNNING",
            started_at=timezone.now(),
        )

        publish_query_event(redis_client, str(query.id), {
            "event": "STEP_STARTED",
            "query_id": str(query.id),
            "step_number": step_num,
            "tool": tool_name,
            "status": "RUNNING",
        })

        t_start = time.perf_counter()

        try:
            # Special Tool: AREA_QUANTIFIER
            if tool_name == "AREA_QUANTIFIER":
                quant_result = {}
                if last_mask_bytes is not None and primary_img:
                    import io
                    import numpy as np
                    from PIL import Image
                    mask_np = np.array(Image.open(io.BytesIO(last_mask_bytes)).convert("L"))
                    quant_result = quantify_mask_area(
                        mask_np,
                        primary_img.affine_transform,
                        primary_img.crs,
                        primary_img.bounds_wgs84,
                    )
                    # Convert to GeoJSON Evidence
                    geojson_features = polygonize_mask_to_geojson(
                        mask_np,
                        primary_img.affine_transform,
                        primary_img.crs,
                        primary_img.bounds_wgs84,
                        class_label="detected_change",
                        confidence=0.88,
                    )
                    for feat in geojson_features[:20]:
                        EvidenceRegion.objects.create(
                            query=query,
                            geojson_geometry=feat["geometry"],
                            class_name=feat["properties"]["label"],
                            confidence=feat["properties"]["confidence"],
                            area_m2=feat["properties"]["area_m2"],
                            area_km2=feat["properties"]["area_km2"],
                            source_step=step_row,
                        )

                step_row.status = "DONE"
                step_row.completed_at = timezone.now()
                step_row.latency_ms = int((time.perf_counter() - t_start) * 1000)
                step_row.output_ref = quant_result
                step_row.save()

                publish_query_event(redis_client, str(query.id), {
                    "event": "STEP_COMPLETED",
                    "query_id": str(query.id),
                    "step_number": step_num,
                    "tool": tool_name,
                    "status": "DONE",
                    "latency_ms": step_row.latency_ms,
                    "output_summary": quant_result,
                })
                continue

            # Specialist Model Execution
            model = get_model_wrapper(tool_name)
            model_input = ModelInput(
                model_id=tool_name,
                image_paths=image_paths,
                question=query.text,
                text_prompt=params.get("prompt", query.text),
                change_mask=last_mask_bytes,
                params=params,
            )

            model_out: ModelOutput = model.predict(model_input)

            if model_out.confidence is not None:
                confidences.append(model_out.confidence)
            if model_out.answer:
                final_answer = model_out.answer
            if model_out.change_mask:
                if isinstance(model_out.change_mask, (bytes, bytearray)):
                    last_mask_bytes = bytes(model_out.change_mask)

            # Record completed step
            step_row.status = "DONE" if model_out.status == "ok" else "FAILED"
            step_row.completed_at = timezone.now()
            step_row.latency_ms = model_out.latency_ms or int((time.perf_counter() - t_start) * 1000)
            step_row.output_ref = {
                "answer": model_out.answer,
                "confidence": model_out.confidence,
                "raw": model_out.raw,
                "boxes_count": len(model_out.boxes) if model_out.boxes else 0,
            }
            step_row.error = model_out.error
            step_row.save()

            publish_query_event(redis_client, str(query.id), {
                "event": "STEP_COMPLETED",
                "query_id": str(query.id),
                "step_number": step_num,
                "tool": tool_name,
                "model_version": model_out.version,
                "status": step_row.status,
                "latency_ms": step_row.latency_ms,
                "output_summary": {
                    "answer": model_out.answer,
                    "confidence": model_out.confidence,
                },
            })

        except Exception as exc:
            step_row.status = "FAILED"
            step_row.completed_at = timezone.now()
            step_row.latency_ms = int((time.perf_counter() - t_start) * 1000)
            step_row.error = str(exc)
            step_row.save()

            publish_query_event(redis_client, str(query.id), {
                "event": "STEP_FAILED",
                "query_id": str(query.id),
                "step_number": step_num,
                "tool": tool_name,
                "error": str(exc),
            })

    # Conservative confidence policy per §12
    aggregated_confidence = min(confidences) if confidences else 0.80

    return {
        "answer": final_answer or "Analysis complete.",
        "confidence": round(aggregated_confidence, 3),
        "status": "COMPLETED",
    }
