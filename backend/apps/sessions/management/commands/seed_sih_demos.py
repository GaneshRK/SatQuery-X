"""Management command to seed 5 comprehensive SIH 2026 showcase demos.

Scenarios:
1. Assam Floods: Brahmaputra River Basin Inundation (Bi-Temporal Sentinel-2)
2. Delhi-NCR: Urban Expansion & Impervious Surface Growth (Bi-Temporal Sentinel-2)
3. Western Ghats: Rainforest Canopy Loss & Buffer Encroachment (Optical Sentinel-2)
4. Mumbai Coastal: SAR & Optical Maritime & Port Fusion (Sentinel-1 SAR + Sentinel-2)
5. Pollachi Agriculture: Plantation Canopy Health & Precision Acreage (Multispectral Sentinel-2)
"""

from __future__ import annotations

import io
import math
import uuid
import numpy as np
from PIL import Image
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sessions.models import Session
from apps.imagery.models import ImageAsset, ImagePair
from apps.queries.models import Query, ExecutionStep
from apps.evidence.models import EvidenceRegion
from apps.reports.models import Report
from apps.reports.tasks import generate_report_task

try:
    import rasterio
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

User = get_user_model()


def generate_synthetic_raster(
    width: int,
    height: int,
    bounds: tuple[float, float, float, float],
    mode: str,
) -> bytes:
    """Generate georeferenced GeoTIFF bytes for various remote-sensing modalities."""
    west, south, east, north = bounds
    x = np.linspace(0, 1, width)
    y = np.linspace(0, 1, height)
    xx, yy = np.meshgrid(x, y)

    if mode == "flood_pre":
        river = 0.5 + 0.12 * np.sin(xx * 3 * np.pi)
        dist = np.abs(yy - river)
        water = dist < 0.04
        sand = (dist >= 0.04) & (dist < 0.09)
        b1 = np.where(water, 130, np.where(sand, 160, 40)).astype(np.uint8)
        b2 = np.where(water, 110, np.where(sand, 170, 75)).astype(np.uint8)
        b3 = np.where(water, 75, np.where(sand, 165, 35)).astype(np.uint8)
        b4 = np.where(water, 20, np.where(sand, 150, 210)).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    elif mode == "flood_post":
        river = 0.5 + 0.12 * np.sin(xx * 3 * np.pi)
        dist = np.abs(yy - river)
        water = (dist < 0.12) | (np.hypot(xx - 0.7, yy - 0.7) < 0.12)
        sand = (dist >= 0.12) & (dist < 0.15)
        b1 = np.where(water, 100, np.where(sand, 140, 35)).astype(np.uint8)
        b2 = np.where(water, 90, np.where(sand, 150, 65)).astype(np.uint8)
        b3 = np.where(water, 65, np.where(sand, 140, 30)).astype(np.uint8)
        b4 = np.where(water, 15, np.where(sand, 120, 170)).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    elif mode == "urban_pre":
        # Green agricultural periphery with small urban core
        urban_core = (np.hypot(xx - 0.5, yy - 0.5) < 0.18)
        b1 = np.where(urban_core, 160, 50).astype(np.uint8)
        b2 = np.where(urban_core, 155, 90).astype(np.uint8)
        b3 = np.where(urban_core, 150, 45).astype(np.uint8)
        b4 = np.where(urban_core, 130, 200).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    elif mode == "urban_post":
        # Significant urban sprawl expansion
        urban_core = (np.hypot(xx - 0.5, yy - 0.5) < 0.35) | (np.abs(yy - 0.45) < 0.08)
        b1 = np.where(urban_core, 170, 45).astype(np.uint8)
        b2 = np.where(urban_core, 165, 80).astype(np.uint8)
        b3 = np.where(urban_core, 160, 40).astype(np.uint8)
        b4 = np.where(urban_core, 125, 180).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    elif mode == "deforestation":
        # Forest canopy with logging patches
        cleared = (xx > 0.6) & (yy > 0.4) & (xx < 0.85) & (yy < 0.7)
        b1 = np.where(cleared, 120, 35).astype(np.uint8)
        b2 = np.where(cleared, 110, 85).astype(np.uint8)
        b3 = np.where(cleared, 140, 30).astype(np.uint8)
        b4 = np.where(cleared, 70, 220).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    elif mode == "sar_sea":
        # Sentinel-1 SAR: Ocean dark, ships high return specular points
        sea = (xx < 0.65)
        b_vv = np.where(sea, 22, 140 + (np.random.rand(height, width) * 35)).astype(np.uint8)
        # Ship points
        for _ in range(12):
            sx, sy = int(np.random.randint(40, int(width * 0.6))), int(np.random.randint(40, height - 40))
            b_vv[sy-2:sy+3, sx-2:sx+3] = 255
        bands = [b_vv, (b_vv * 0.7).astype(np.uint8)]

    else:
        # Agriculture / canopy healthy
        pats = np.sin(xx * 16 * np.pi) * np.cos(yy * 16 * np.pi) > 0.1
        b1 = np.where(pats, 40, 50).astype(np.uint8)
        b2 = np.where(pats, 100, 80).astype(np.uint8)
        b3 = np.where(pats, 35, 45).astype(np.uint8)
        b4 = np.where(pats, 230, 190).astype(np.uint8)
        bands = [b1, b2, b3, b4]

    out_bytes = io.BytesIO()
    if HAS_RASTERIO:
        transform = from_bounds(west, south, east, north, width, height)
        with rasterio.open(
            out_bytes,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=len(bands),
            dtype=bands[0].dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            for idx, band in enumerate(bands, 1):
                dst.write(band, idx)
        return out_bytes.getvalue()
    else:
        rgb = np.stack([bands[0], bands[1], bands[2]], axis=-1)
        img = Image.fromarray(rgb)
        img.save(out_bytes, format="PNG")
        return out_bytes.getvalue()


class Command(BaseCommand):
    help = "Seed 5 complete SIH 2026 showcase demos across multiple remote-sensing domains."

    def handle(self, *args, **options):
        self.stdout.write("--- Seeding 5 Comprehensive SIH 2026 Showcase Demos ---")

        analyst, _ = User.objects.get_or_create(
            username="analyst",
            defaults={"email": "analyst@isro.gov.in", "role": "demo"}
        )
        judge, _ = User.objects.get_or_create(
            username="sih_judge",
            defaults={"email": "judge@sih.gov.in", "role": "judge", "is_staff": True}
        )

        for u in [analyst, judge]:
            self.seed_all_demos_for_user(u)

        self.stdout.write(self.style.SUCCESS("--- All 5 SIH 2026 Showcase Demos Seeded Successfully ---"))

    def seed_all_demos_for_user(self, user):
        self.seed_assam_demo(user)
        self.seed_delhi_demo(user)
        self.seed_westernghats_demo(user)
        self.seed_mumbai_demo(user)
        self.seed_pollachi_demo(user)

    def _save_raster_asset(self, session, filename, bounds, mode, sensor="SENTINEL-2", modality="MULTISPECTRAL"):
        raw_bytes = generate_synthetic_raster(512, 512, bounds, mode)
        file_path = default_storage.save(f"sessions/{session.id}/images/{filename}", ContentFile(raw_bytes))

        # Generate thumbnail
        thumb_io = io.BytesIO()
        rgb = np.stack([
            np.full((512, 512), 40, dtype=np.uint8),
            np.full((512, 512), 110, dtype=np.uint8),
            np.full((512, 512), 160, dtype=np.uint8)
        ], axis=-1)
        Image.fromarray(rgb).save(thumb_io, format="PNG")
        thumb_path = default_storage.save(f"previews/preview_{uuid.uuid4().hex[:8]}.png", ContentFile(thumb_io.getvalue()))

        west, south, east, north = bounds
        pixel_x = (east - west) / 512.0
        pixel_y = (north - south) / 512.0

        return ImageAsset.objects.create(
            session=session,
            file=file_path,
            original_filename=filename,
            content_type="image/tiff",
            file_format="GEOTIFF",
            width=512,
            height=512,
            band_count=4 if modality == "MULTISPECTRAL" else 2,
            dtype="uint8",
            crs="EPSG:4326",
            affine_transform=[pixel_x, 0.0, west, 0.0, -pixel_y, north],
            bounds_native={"left": west, "bottom": south, "right": east, "top": north},
            bounds_wgs84={"west": west, "south": south, "east": east, "north": north},
            resolution_m=10.0,
            sensor=sensor,
            modality=modality,
            is_georeferenced=True,
            preview_url=default_storage.url(thumb_path),
            processing_status="VALIDATED",
            validation_report={"status": "VALID", "crs": "EPSG:4326", "is_georeferenced": True},
            provenance={"sensor": sensor, "platform": "Copernicus CDSE", "resolution": "10m"},
        )

    def seed_assam_demo(self, user):
        bounds = (93.00, 26.50, 93.25, 26.75)
        session, _ = Session.objects.get_or_create(
            user=user,
            name="Assam Flood Inundation & River Dynamics (Kaziranga Basin)",
            defaults={"status": "active"}
        )
        if session.imagery_assets.count() < 2:
            img_pre = self._save_raster_asset(session, "Sentinel2_Assam_PreMonsoon.tif", bounds, "flood_pre")
            img_post = self._save_raster_asset(session, "Sentinel2_Assam_PostFlood.tif", bounds, "flood_post")
            pair = ImagePair.objects.create(
                session=session,
                image_a=img_pre,
                image_b=img_post,
                pair_type="BI_TEMPORAL",
                compatibility_status="COMPATIBLE",
                coregistration_status="DONE"
            )

            q = Query.objects.create(
                session=session,
                user=user,
                text="Detect and quantify flood inundation area across the Brahmaputra basin compared to pre-monsoon baseline.",
                image=img_post,
                image_pair=pair,
                detected_mode="BI_TEMPORAL",
                detected_task="FLOOD_INUNDATION_QUANTIFICATION",
                status="COMPLETED",
                confidence=0.94,
                answer="Bi-temporal satellite analysis identifies significant flood inundation across the Brahmaputra lowlands. Surface water extent expanded by 18.42 km² (+41.3% increase compared to baseline). 3 major contiguous flood polygons detected.",
                completed_at=timezone.now(),
            )
            ExecutionStep.objects.create(query=q, step_number=1, tool_name="validate_inputs", model_version="1.0", latency_ms=30, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=2, tool_name="compute_spectral_indices", model_version="1.0", latency_ms=120, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=3, tool_name="otsu_thresholding", model_version="1.0-baseline", latency_ms=45, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=4, tool_name="vector_polygonize", model_version="1.0", latency_ms=80, status="DONE")

            poly_coords = [[[93.05, 26.55], [93.18, 26.55], [93.20, 26.68], [93.06, 26.67], [93.05, 26.55]]]
            EvidenceRegion.objects.create(
                query=q,
                class_name="Flood Inundated Plain",
                confidence=0.94,
                area_km2=18.42,
                area_m2=18420000.0,
                geojson_geometry={"type": "Polygon", "coordinates": poly_coords},
            )

    def seed_delhi_demo(self, user):
        bounds = (76.90, 28.40, 77.15, 28.65)
        session, _ = Session.objects.get_or_create(
            user=user,
            name="Delhi-NCR Urban Sprawl & Impervious Growth (2019-2024)",
            defaults={"status": "active"}
        )
        if session.imagery_assets.count() < 2:
            img_pre = self._save_raster_asset(session, "Sentinel2_Delhi_2019.tif", bounds, "urban_pre")
            img_post = self._save_raster_asset(session, "Sentinel2_Delhi_2024.tif", bounds, "urban_post")
            pair = ImagePair.objects.create(
                session=session,
                image_a=img_pre,
                image_b=img_post,
                pair_type="BI_TEMPORAL",
                compatibility_status="COMPATIBLE",
                coregistration_status="DONE"
            )

            q = Query.objects.create(
                session=session,
                user=user,
                text="Has built-up structural area increased significantly across the south-west corridor?",
                image=img_post,
                image_pair=pair,
                detected_mode="BI_TEMPORAL",
                detected_task="URBAN_EXPANSION_ANALYSIS",
                status="COMPLETED",
                confidence=0.91,
                answer="Urban change detection reveals 14.85 km² of newly developed impervious surfaces and industrial parcels across the southern corridor, representing a 24.3% structural expansion.",
                completed_at=timezone.now(),
            )
            ExecutionStep.objects.create(query=q, step_number=1, tool_name="co_register_rasters", model_version="1.0", latency_ms=40, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=2, tool_name="detect_and_count_structures", model_version="1.0-baseline", latency_ms=180, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=3, tool_name="vector_polygonize", model_version="1.0", latency_ms=90, status="DONE")

            poly_coords = [[[76.95, 28.45], [77.10, 28.45], [77.12, 28.58], [76.97, 28.56], [76.95, 28.45]]]
            EvidenceRegion.objects.create(
                query=q,
                class_name="New Built-Up Corridors",
                confidence=0.91,
                area_km2=14.85,
                area_m2=14850000.0,
                geojson_geometry={"type": "Polygon", "coordinates": poly_coords},
            )

    def seed_westernghats_demo(self, user):
        bounds = (76.40, 11.00, 76.65, 11.25)
        session, _ = Session.objects.get_or_create(
            user=user,
            name="Western Ghats Rainforest Canopy Loss & Boundary Encroachment",
            defaults={"status": "active"}
        )
        if session.imagery_assets.count() < 1:
            img = self._save_raster_asset(session, "Sentinel2_WesternGhats_Canopy.tif", bounds, "deforestation")

            q = Query.objects.create(
                session=session,
                user=user,
                text="Measure canopy loss and flag degraded forest tracts within 5km of protected park boundary.",
                image=img,
                detected_mode="SINGLE_IMAGE",
                detected_task="DEFORESTATION_DETECTION",
                status="COMPLETED",
                confidence=0.93,
                answer="Multispectral NDVI profiling identifies 6.82 km² of fragmented and cleared rainforest canopy along the northeastern buffer perimeter.",
                completed_at=timezone.now(),
            )
            ExecutionStep.objects.create(query=q, step_number=1, tool_name="segment_vegetation", model_version="1.0-baseline", latency_ms=65, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=2, tool_name="vector_polygonize", model_version="1.0", latency_ms=75, status="DONE")

            poly_coords = [[[76.55, 11.10], [76.62, 11.10], [76.63, 11.20], [76.56, 11.19], [76.55, 11.10]]]
            EvidenceRegion.objects.create(
                query=q,
                class_name="Canopy Degradation Tract",
                confidence=0.93,
                area_km2=6.82,
                area_m2=6820000.0,
                geojson_geometry={"type": "Polygon", "coordinates": poly_coords},
            )

    def seed_mumbai_demo(self, user):
        bounds = (72.80, 18.90, 73.05, 19.15)
        session, _ = Session.objects.get_or_create(
            user=user,
            name="Mumbai Coastal SAR Radar Penetration & Maritime Monitoring",
            defaults={"status": "active"}
        )
        if session.imagery_assets.count() < 2:
            img_sar = self._save_raster_asset(session, "Sentinel1_Mumbai_SAR_GRD.tif", bounds, "sar_sea", sensor="SENTINEL-1", modality="SAR")
            img_opt = self._save_raster_asset(session, "Sentinel2_Mumbai_Optical_CloudCover.tif", bounds, "flood_pre", sensor="SENTINEL-2", modality="MULTISPECTRAL")
            pair = ImagePair.objects.create(
                session=session,
                image_a=img_opt,
                image_b=img_sar,
                pair_type="CROSS_MODAL",
                compatibility_status="COMPATIBLE",
                coregistration_status="DONE"
            )

            q = Query.objects.create(
                session=session,
                user=user,
                text="Perform fused optical-SAR coastline penetration to detect maritime vessel clusters and coastal reclamation.",
                image=img_sar,
                image_pair=pair,
                detected_mode="CROSS_MODAL_PAIR",
                detected_task="MARITIME_VESSEL_DETECTION",
                status="COMPLETED",
                confidence=0.96,
                answer="Cross-modal SAR fusion successfully penetrated dense maritime cloud cover. 12 high-reflectance anchored maritime vessels detected in outer anchorage, and 3.20 km² of reclaimed port jetty area mapped.",
                completed_at=timezone.now(),
            )
            ExecutionStep.objects.create(query=q, step_number=1, tool_name="cross_modal_fusion", model_version="1.0-baseline", latency_ms=210, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=2, tool_name="detect_and_count_structures", model_version="1.0-baseline", latency_ms=115, status="DONE")

            poly_coords = [[[72.84, 18.93], [72.95, 18.93], [72.97, 19.04], [72.85, 19.03], [72.84, 18.93]]]
            EvidenceRegion.objects.create(
                query=q,
                class_name="Reclaimed Port Infrastructure",
                confidence=0.96,
                area_km2=3.20,
                area_m2=3200000.0,
                geojson_geometry={"type": "Polygon", "coordinates": poly_coords},
            )

    def seed_pollachi_demo(self, user):
        bounds = (76.95, 10.60, 77.20, 10.85)
        session, _ = Session.objects.get_or_create(
            user=user,
            name="Pollachi Agriculture: Plantation Canopy Health & Precision Acreage",
            defaults={"status": "active"}
        )
        if session.imagery_assets.count() < 1:
            img = self._save_raster_asset(session, "Sentinel2_Pollachi_AgriCanopy.tif", bounds, "agri")

            q = Query.objects.create(
                session=session,
                user=user,
                text="Segment healthy vegetation tracts and quantify agricultural surface area in hectares.",
                image=img,
                detected_mode="SINGLE_IMAGE",
                detected_task="AGRICULTURE_MONITORING",
                status="COMPLETED",
                confidence=0.95,
                answer="Multispectral agricultural extraction confirms healthy crop and coconut canopy covering 24.20 km² (2,420 hectares). Vegetation vigor index indicates optimal irrigation levels across 88% of parcels.",
                completed_at=timezone.now(),
            )
            ExecutionStep.objects.create(query=q, step_number=1, tool_name="segment_vegetation", model_version="1.0-baseline", latency_ms=70, status="DONE")
            ExecutionStep.objects.create(query=q, step_number=2, tool_name="vector_polygonize", model_version="1.0", latency_ms=85, status="DONE")

            poly_coords = [[[77.00, 10.65], [77.15, 10.65], [77.16, 10.80], [77.02, 10.79], [77.00, 10.65]]]
            EvidenceRegion.objects.create(
                query=q,
                class_name="High Vigor Canopy Tracts",
                confidence=0.95,
                area_km2=24.20,
                area_m2=24200000.0,
                geojson_geometry={"type": "Polygon", "coordinates": poly_coords},
            )
