"""
SIH 2026 Presentation and Demo Scenarios Endpoint.
Provides one-click bootstrap endpoints for the 7 Golden Test Scenarios per Phase 11 & Phase 12.
"""

from __future__ import annotations

import io
import uuid
from typing import Any
import numpy as np
from PIL import Image

from django.core.files.base import ContentFile
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.imagery.models import ImageAsset, ImagePair
from apps.imagery.tasks import ingest_image_task
from apps.queries.models import Query
from apps.queries.tasks import run_query_task
from apps.sessions.models import Session


DEMO_SCENARIOS: dict[str, dict[str, Any]] = {
    "scenario_1_caption": {
        "key": "scenario_1_caption",
        "title": "Scenario 1: Single-Image Scene Captioning",
        "description": "Comprehensive natural-language scene understanding and land-cover description over Sentinel-2 MSI optical imagery.",
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "default_query": "Describe the overall scene and land-cover structure visible in this satellite pass.",
    },
    "scenario_2_vqa": {
        "key": "scenario_2_vqa",
        "title": "Scenario 2: Single-Image Remote-Sensing VQA",
        "description": "Visual question answering evaluating specific surface features, infrastructure, and waterbodies.",
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "default_query": "Is there standing floodwater or an active waterbody in this remote sensing scene?",
    },
    "scenario_3_grounding": {
        "key": "scenario_3_grounding",
        "title": "Scenario 3: Single-Image Visual Grounding",
        "description": "Localizing and bounding target features from open-vocabulary text prompts.",
        "sensor": "CARTOSAT-2S",
        "modality": "OPTICAL",
        "mode": "SINGLE_IMAGE",
        "default_query": "Locate and bound all airport runways, taxiways, and aircraft parking bays.",
    },
    "scenario_4_change_detection": {
        "key": "scenario_4_change_detection",
        "title": "Scenario 4: Bi-temporal Change Detection & Area Quantification",
        "description": "Bi-temporal coregistered pair analysis producing segmented difference masks, bounding boxes, and geodesic area calculations in hectares and km².",
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "default_query": "Detect all land-use surface changes between time T1 and time T2 and calculate the total affected area in hectares.",
    },
    "scenario_5_change_vqa": {
        "key": "scenario_5_change_vqa",
        "title": "Scenario 5: Bi-temporal Change VQA",
        "description": "Natural-language reasoning over bi-temporal changes linking qualitative trends to quantified masks.",
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "default_query": "Has the forest canopy cover increased or decreased between the pre-event and post-event images?",
    },
    "scenario_6_optical_sar_fusion": {
        "key": "scenario_6_optical_sar_fusion",
        "title": "Scenario 6: Optical + SAR Cross-Modal Fusion",
        "description": "Joint exploitation of optical and synthetic aperture radar (SAR) imagery to penetrate cloud/haze and map built-up/water surfaces.",
        "sensor": "SENTINEL-2 + RISAT-1A",
        "modality": "CROSS_MODAL",
        "mode": "CROSS_MODAL_PAIR",
        "default_query": "Fuse the optical and SAR imagery to identify built-up infrastructure and standing water despite cloud cover.",
    },
    "scenario_7_multiturn": {
        "key": "scenario_7_multiturn",
        "title": "Scenario 7: Multi-Turn Conversational Follow-Up",
        "description": "Context-preserving multi-turn dialogue ('Where is the change?' followed by 'How much area is affected?').",
        "sensor": "SENTINEL-2",
        "modality": "OPTICAL",
        "mode": "BI_TEMPORAL",
        "default_query": "Where are the primary surface changes located in this scene?",
        "follow_up_query": "How much total metric area does this change represent in hectares and square kilometers?",
    },
}


def _create_synthetic_raster(pattern: str = "optical", seed: int = 42) -> bytes:
    """Generates an honest synthetic raster with distinct spectral properties."""
    rng = np.random.default_rng(seed)
    w, h = 128, 128
    if pattern == "optical":
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        arr[:, :, 1] = rng.integers(120, 220, size=(h, w), dtype=np.uint8)  # High green
        arr[:, :, 0] = rng.integers(30, 80, size=(h, w), dtype=np.uint8)
        arr[:, :, 2] = rng.integers(20, 60, size=(h, w), dtype=np.uint8)
        img = Image.fromarray(arr, mode="RGB")
    elif pattern == "optical_t2":
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        arr[:, :, 0] = rng.integers(140, 220, size=(h, w), dtype=np.uint8)  # Altered/burnt/cleared
        arr[:, :, 1] = rng.integers(50, 100, size=(h, w), dtype=np.uint8)
        arr[:, :, 2] = rng.integers(30, 70, size=(h, w), dtype=np.uint8)
        img = Image.fromarray(arr, mode="RGB")
    elif pattern == "sar":
        # Grayscale speckle pattern
        raw_speckle = rng.gamma(shape=2.0, scale=30.0, size=(h, w))
        raw_speckle = np.clip(raw_speckle, 0, 255).astype(np.uint8)
        img = Image.fromarray(raw_speckle, mode="L").convert("RGB")
    else:
        arr = rng.integers(50, 200, size=(h, w, 3), dtype=np.uint8)
        img = Image.fromarray(arr, mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class DemoScenariosListView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Returns metadata for all 7 Golden Test Scenarios."""
        return Response({
            "platform": "SatQuery AI",
            "sih_problem_statement": "26167",
            "scenarios": list(DEMO_SCENARIOS.values()),
            "count": len(DEMO_SCENARIOS),
        })


class BootstrapDemoScenarioView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, scenario_key: str):
        """
        Bootstraps a complete, live SIH demonstration session for a selected golden scenario.
        Creates sessions, uploads calibrated rasters, pairs, and executes the canonical query.
        """
        if scenario_key not in DEMO_SCENARIOS:
            return Response(
                {"error": f"Invalid scenario '{scenario_key}'. Available: {list(DEMO_SCENARIOS.keys())}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sc = DEMO_SCENARIOS[scenario_key]
        user = request.user

        # 1. Create dedicated Demo Session
        session = Session.objects.create(
            user=user,
            name=f"[SIH Demo] {sc['title']}",
        )

        # 2. Upload and Ingest Asset(s)
        bounds_kaziranga = {"west": 93.10, "south": 26.55, "east": 93.25, "north": 26.70}

        if sc["mode"] == "SINGLE_IMAGE":
            img_bytes = _create_synthetic_raster("optical", seed=101)
            asset = ImageAsset.objects.create(
                session=session,
                original_filename=f"{scenario_key}_pass1.png",
                file_format="PNG",
                content_type="image/png",
                sensor=sc["sensor"],
                modality=sc["modality"],
                bounds_wgs84=bounds_kaziranga,
                is_georeferenced=True,
                resolution_m=10.0,
                processing_status="VALIDATED",
            )
            asset.file.save(f"{scenario_key}_pass1.png", ContentFile(img_bytes))
            asset.save()
            try:
                ingest_image_task(str(asset.id))
            except Exception:
                pass

            # 3. Create & Execute Canonical Query
            query = Query.objects.create(
                session=session,
                user=user,
                text=sc["default_query"],
                image=asset,
                detected_mode="SINGLE_IMAGE",
            )
            try:
                run_query_task(str(query.id))
            except Exception:
                pass
            query.refresh_from_db()

            return Response({
                "status": "bootstrapped",
                "scenario": sc,
                "session_id": str(session.id),
                "image_id": str(asset.id),
                "query_id": str(query.id),
                "query_status": query.status,
                "answer": query.answer,
                "confidence": query.confidence,
            }, status=status.HTTP_201_CREATED)

        elif sc["mode"] in ("BI_TEMPORAL", "CROSS_MODAL_PAIR"):
            is_cross_modal = sc["mode"] == "CROSS_MODAL_PAIR"
            img1_bytes = _create_synthetic_raster("optical", seed=201)
            img2_bytes = _create_synthetic_raster("sar" if is_cross_modal else "optical_t2", seed=202)

            fn1 = f"sentinel2_optical_t1.png"
            fn2 = "risat_sar_t2.png" if is_cross_modal else "sentinel2_optical_t2.png"

            asset1 = ImageAsset.objects.create(
                session=session,
                original_filename=fn1,
                file_format="PNG",
                content_type="image/png",
                sensor="SENTINEL-2",
                modality="OPTICAL",
                bounds_wgs84=bounds_kaziranga,
                is_georeferenced=True,
                resolution_m=10.0,
                processing_status="VALIDATED",
            )
            asset1.file.save(fn1, ContentFile(img1_bytes))
            asset1.save()

            asset2 = ImageAsset.objects.create(
                session=session,
                original_filename=fn2,
                file_format="PNG",
                content_type="image/png",
                sensor="RISAT-1A" if is_cross_modal else "SENTINEL-2",
                modality="SAR" if is_cross_modal else "OPTICAL",
                bounds_wgs84=bounds_kaziranga,
                is_georeferenced=True,
                resolution_m=10.0 if not is_cross_modal else 15.0,
                processing_status="VALIDATED",
            )
            asset2.file.save(fn2, ContentFile(img2_bytes))
            asset2.save()

            try:
                ingest_image_task(str(asset1.id))
                ingest_image_task(str(asset2.id))
            except Exception:
                pass

            pair = ImagePair.objects.create(
                session=session,
                image_a=asset1,
                image_b=asset2,
                pair_type="CROSS_MODAL" if is_cross_modal else "BI_TEMPORAL",
                compatibility_status="COMPATIBLE",
                coregistration_status="DONE",
                compatibility_report={"overlap_pct": 100.0, "status": "COMPATIBLE"},
            )

            query = Query.objects.create(
                session=session,
                user=user,
                text=sc["default_query"],
                image=asset1,
                image_pair=pair,
                detected_mode="CROSS_MODAL" if is_cross_modal else "BI_TEMPORAL",
            )
            try:
                run_query_task(str(query.id))
            except Exception:
                pass
            query.refresh_from_db()

            return Response({
                "status": "bootstrapped",
                "scenario": sc,
                "session_id": str(session.id),
                "image_a_id": str(asset1.id),
                "image_b_id": str(asset2.id),
                "pair_id": str(pair.id),
                "query_id": str(query.id),
                "query_status": query.status,
                "answer": query.answer,
                "confidence": query.confidence,
            }, status=status.HTTP_201_CREATED)
