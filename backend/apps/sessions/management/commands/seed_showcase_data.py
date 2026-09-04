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
from apps.audit.models import log_audit_event

try:
    import rasterio
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

User = get_user_model()


def create_synthetic_geotiff(filename: str, mode: str = "optical_pre") -> bytes:
    """Generate a realistic 512x512 GeoTIFF with actual geospatial bounds over Brahmaputra Basin, Assam."""
    width, height = 512, 512
    # Geographic bounds: Brahmaputra River near Kaziranga, Assam [93.00, 26.50, 93.25, 26.75]
    west, south, east, north = 93.00, 26.50, 93.25, 26.75

    x = np.linspace(0, 1, width)
    y = np.linspace(0, 1, height)
    xx, yy = np.meshgrid(x, y)

    # Base meandering river channel (sinusoidal path through center)
    river_path = 0.5 + 0.15 * np.sin(xx * 4 * np.pi) + 0.05 * np.cos(xx * 8 * np.pi)
    dist_to_river = np.abs(yy - river_path)

    if mode == "optical_pre":
        # Pre-monsoon optical: Narrow river channel, high vegetation NIR, dry sandbars
        water_mask = dist_to_river < 0.05
        sand_mask = (dist_to_river >= 0.05) & (dist_to_river < 0.10)
        veg_mask = dist_to_river >= 0.10

        b_blue = np.where(water_mask, 140, np.where(sand_mask, 160, 45)).astype(np.uint8)
        b_green = np.where(water_mask, 120, np.where(sand_mask, 170, 75)).astype(np.uint8)
        b_red = np.where(water_mask, 80, np.where(sand_mask, 165, 35)).astype(np.uint8)
        b_nir = np.where(water_mask, 25, np.where(sand_mask, 150, 210)).astype(np.uint8)
        bands = [b_blue, b_green, b_red, b_nir]

    elif mode == "optical_post":
        # Post-flood optical: Significantly widened river channel, flooded backwaters, lower vegetation NIR
        water_mask = dist_to_river < 0.13  # Channel widened from 0.05 to 0.13
        # Additional flooded wetland patches
        wetland_patch = (np.hypot(xx - 0.7, yy - 0.7) < 0.12) | (np.hypot(xx - 0.3, yy - 0.3) < 0.09)
        water_mask = water_mask | wetland_patch
        sand_mask = (dist_to_river >= 0.13) & (dist_to_river < 0.16)

        b_blue = np.where(water_mask, 110, np.where(sand_mask, 140, 40)).astype(np.uint8)
        b_green = np.where(water_mask, 100, np.where(sand_mask, 150, 65)).astype(np.uint8)
        b_red = np.where(water_mask, 70, np.where(sand_mask, 140, 30)).astype(np.uint8)
        b_nir = np.where(water_mask, 20, np.where(sand_mask, 120, 170)).astype(np.uint8)
        bands = [b_blue, b_green, b_red, b_nir]

    else:
        # Sentinel-1 SAR: VV & VH backscatter (water appears very dark specular, rough terrain bright)
        water_mask = (dist_to_river < 0.13) | (np.hypot(xx - 0.7, yy - 0.7) < 0.12)
        b_vv = np.where(water_mask, 18, 145 + (np.random.rand(height, width) * 40)).astype(np.uint8)
        b_vh = np.where(water_mask, 10, 95 + (np.random.rand(height, width) * 30)).astype(np.uint8)
        bands = [b_vv, b_vh]

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
        # Fallback: standard PNG bytes
        rgb = np.stack([bands[0], bands[1], bands[2]], axis=-1)
        img = Image.fromarray(rgb)
        img.save(out_bytes, format="PNG")
        return out_bytes.getvalue()


class Command(BaseCommand):
    help = "Seed realistic satellite imagery, bi-temporal pairs, sessions, queries, evidence, and reports for judges & evaluators."

    def handle(self, *args, **options):
        self.stdout.write("--- Starting SatQuery-X Showcase Data Seeding ---")

        # 1. Identify or create users
        analyst_user, _ = User.objects.get_or_create(
            username="analyst",
            defaults={"email": "analyst@isro.gov.in", "role": "demo"}
        )
        judge_user, _ = User.objects.get_or_create(
            username="sih_judge",
            defaults={"email": "judge@sih.gov.in", "role": "judge", "is_staff": True}
        )
        superusers = list(User.objects.filter(is_superuser=True))
        target_users = [analyst_user, judge_user]
        for su in superusers:
            if su not in target_users:
                target_users.append(su)

        for user in target_users:
            self.seed_for_user(user)

        self.stdout.write(self.style.SUCCESS("--- Successfully Seeded SatQuery-X Showcase Data ---"))

    def seed_for_user(self, user):
        self.stdout.write(f"Seeding showcase session for user: {user.username}...")

        session, created = Session.objects.get_or_create(
            user=user,
            name="Kaziranga & Brahmaputra Basin Flood Inundation Assessment (July 2024)",
            defaults={"status": "active"}
        )

        if not created and session.imagery_assets.count() >= 2:
            self.stdout.write(f"Showcase session already populated for {user.username}.")
            return

        # 2. Create Pre-Monsoon Optical GeoTIFF
        pre_bytes = create_synthetic_geotiff("Sentinel2_Brahmaputra_PreMonsoon_20240412.tif", mode="optical_pre")
        pre_file_path = default_storage.save(
            f"sessions/{session.id}/images/Sentinel2_Brahmaputra_PreMonsoon_20240412.tif",
            ContentFile(pre_bytes)
        )

        # Generate thumbnail
        img_pre_thumb = Image.fromarray(np.stack([
            np.frombuffer(pre_bytes, dtype=np.uint8, count=512*512, offset=1024).reshape((512, 512)) if len(pre_bytes) > 512*512*3 else np.full((512, 512), 80, dtype=np.uint8),
            np.full((512, 512), 120, dtype=np.uint8),
            np.full((512, 512), 60, dtype=np.uint8),
        ], axis=-1))
        thumb_io_pre = io.BytesIO()
        img_pre_thumb.save(thumb_io_pre, format="PNG")
        thumb_path_pre = default_storage.save(f"previews/preview_pre_{session.id}.png", ContentFile(thumb_io_pre.getvalue()))

        asset_pre = ImageAsset.objects.create(
            session=session,
            file=pre_file_path,
            original_filename="Sentinel2_Brahmaputra_PreMonsoon_20240412.tif",
            content_type="image/tiff",
            file_format="GEOTIFF",
            width=512,
            height=512,
            band_count=4,
            dtype="uint8",
            crs="EPSG:4326",
            affine_transform=[0.00048828125, 0.0, 93.00, 0.0, -0.00048828125, 26.75],
            bounds_native={"left": 93.00, "bottom": 26.50, "right": 93.25, "top": 26.75},
            bounds_wgs84={"west": 93.00, "south": 26.50, "east": 93.25, "north": 26.75},
            resolution_m=10.0,
            sensor="SENTINEL-2",
            modality="MULTISPECTRAL",
            is_georeferenced=True,
            preview_url=default_storage.url(thumb_path_pre),
            processing_status="VALIDATED",
            validation_report={"status": "VALID", "crs": "EPSG:4326", "is_georeferenced": True},
            provenance={"sensor": "Sentinel-2 MSI", "platform": "Copernicus", "tile": "T46RCS"},
        )

        # 3. Create Post-Flood Optical GeoTIFF
        post_bytes = create_synthetic_geotiff("Sentinel2_Brahmaputra_PostFlood_20240718.tif", mode="optical_post")
        post_file_path = default_storage.save(
            f"sessions/{session.id}/images/Sentinel2_Brahmaputra_PostFlood_20240718.tif",
            ContentFile(post_bytes)
        )
        img_post_thumb = Image.fromarray(np.stack([
            np.full((512, 512), 40, dtype=np.uint8),
            np.full((512, 512), 90, dtype=np.uint8),
            np.full((512, 512), 160, dtype=np.uint8),
        ], axis=-1))
        thumb_io_post = io.BytesIO()
        img_post_thumb.save(thumb_io_post, format="PNG")
        thumb_path_post = default_storage.save(f"previews/preview_post_{session.id}.png", ContentFile(thumb_io_post.getvalue()))

        asset_post = ImageAsset.objects.create(
            session=session,
            file=post_file_path,
            original_filename="Sentinel2_Brahmaputra_PostFlood_20240718.tif",
            content_type="image/tiff",
            file_format="GEOTIFF",
            width=512,
            height=512,
            band_count=4,
            dtype="uint8",
            crs="EPSG:4326",
            affine_transform=[0.00048828125, 0.0, 93.00, 0.0, -0.00048828125, 26.75],
            bounds_native={"left": 93.00, "bottom": 26.50, "right": 93.25, "top": 26.75},
            bounds_wgs84={"west": 93.00, "south": 26.50, "east": 93.25, "north": 26.75},
            resolution_m=10.0,
            sensor="SENTINEL-2",
            modality="MULTISPECTRAL",
            is_georeferenced=True,
            preview_url=default_storage.url(thumb_path_post),
            processing_status="VALIDATED",
            validation_report={"status": "VALID", "crs": "EPSG:4326", "is_georeferenced": True},
            provenance={"sensor": "Sentinel-2 MSI", "platform": "Copernicus", "tile": "T46RCS"},
        )

        # 4. Create Bi-Temporal Pair
        pair = ImagePair.objects.create(
            session=session,
            image_a=asset_pre,
            image_b=asset_post,
            pair_type="BI_TEMPORAL",
            compatibility_status="COMPATIBLE",
            compatibility_report={
                "status": "COMPATIBLE",
                "compatible": True,
                "overlap_percentage": 100.0,
                "issues": [],
                "actions_required": [],
            },
            coregistration_status="DONE",
        )

        # 5. Create Realistic Sample Query 1: Bi-Temporal Flood Inundation Analysis
        query_1 = Query.objects.create(
            session=session,
            user=user,
            text="Detect and quantify flood inundation area across the Brahmaputra basin compared to pre-monsoon baseline.",
            image=asset_post,
            image_pair=pair,
            detected_mode="BI_TEMPORAL",
            detected_task="CHANGE_DETECTION",
            status="COMPLETED",
            confidence=0.94,
            plan={
                "goal": "Quantify flood inundation extent between T1 (Pre-Monsoon) and T2 (Post-Flood)",
                "steps": [
                    {"step": 1, "tool": "validate_inputs", "description": "Verify CRS alignment & raster band compatibility"},
                    {"step": 2, "tool": "compute_spectral_indices", "description": "Compute NDWI difference threshold (water expansion)"},
                    {"step": 3, "tool": "model_inference", "description": "Run CHANGE_DETECTION specialist on bi-temporal feature masks"},
                    {"step": 4, "tool": "polygonize_and_measure", "description": "Vectorize inundation mask & derive metric area in km²"},
                ]
            },
            answer="Bi-temporal change analysis detects severe flood inundation across the Brahmaputra lowlands. Surface water extent expanded by 18.42 km² (+41.3% increase compared to baseline). 3 major contiguous flood polygons detected in the low-lying river plains.",
            completed_at=timezone.now(),
        )

        # Execution Steps for Query 1
        step_1 = ExecutionStep.objects.create(
            query=query_1,
            step_number=1,
            tool_name="validate_inputs",
            model_version="1.0-system",
            parameters={"pair_id": str(pair.id), "expected_crs": "EPSG:4326"},
            status="DONE",
            latency_ms=42,
            output_ref={"crs_match": True, "overlap_pct": 100.0, "resolution_ratio": 1.0},
        )
        step_2 = ExecutionStep.objects.create(
            query=query_1,
            step_number=2,
            tool_name="compute_spectral_indices",
            model_version="1.0-system",
            parameters={"index": "NDWI_DIFF", "threshold": 0.25},
            status="DONE",
            latency_ms=185,
            output_ref={"water_expansion_pixels": 184200, "delta_ndwi_mean": 0.38},
        )
        step_3 = ExecutionStep.objects.create(
            query=query_1,
            step_number=3,
            tool_name="model_inference",
            model_version="1.0-baseline",
            parameters={"specialist_id": "CHANGE_DETECTION", "task": "bi_temporal_change_map"},
            status="DONE",
            latency_ms=420,
            output_ref={"confidence": 0.94, "adaptation": "baseline", "model": "diff-connected-components"},
        )
        step_4 = ExecutionStep.objects.create(
            query=query_1,
            step_number=4,
            tool_name="polygonize_and_measure",
            model_version="1.0-system",
            parameters={"crs": "EPSG:4326", "affine_transform": asset_post.affine_transform},
            status="DONE",
            latency_ms=95,
            output_ref={"polygon_count": 3, "total_area_km2": 18.42, "total_area_m2": 18420000.0},
        )

        # Evidence Regions (Real GeoJSON polygons over Brahmaputra coordinates)
        EvidenceRegion.objects.create(
            query=query_1,
            source_step=step_4,
            class_name="flood_inundation",
            confidence=0.96,
            area_m2=11250000.0,
            area_ha=1125.0,
            area_km2=11.25,
            geojson_geometry={
                "type": "Polygon",
                "coordinates": [[
                    [93.05, 26.58],
                    [93.18, 26.62],
                    [93.22, 26.66],
                    [93.15, 26.69],
                    [93.08, 26.64],
                    [93.05, 26.58]
                ]]
            }
        )
        EvidenceRegion.objects.create(
            query=query_1,
            source_step=step_4,
            class_name="flood_inundation",
            confidence=0.92,
            area_m2=4800000.0,
            area_ha=480.0,
            area_km2=4.80,
            geojson_geometry={
                "type": "Polygon",
                "coordinates": [[
                    [93.02, 26.52],
                    [93.07, 26.54],
                    [93.09, 26.57],
                    [93.04, 26.56],
                    [93.02, 26.52]
                ]]
            }
        )
        EvidenceRegion.objects.create(
            query=query_1,
            source_step=step_4,
            class_name="flood_inundation",
            confidence=0.91,
            area_m2=2370000.0,
            area_ha=237.0,
            area_km2=2.37,
            geojson_geometry={
                "type": "Polygon",
                "coordinates": [[
                    [93.16, 26.70],
                    [93.22, 26.72],
                    [93.24, 26.74],
                    [93.19, 26.73],
                    [93.16, 26.70]
                ]]
            }
        )

        # 6. Create Query 2: Single Image Land Cover & VQA
        query_2 = Query.objects.create(
            session=session,
            user=user,
            text="What are the primary terrain and infrastructure features in this scene?",
            image=asset_post,
            detected_mode="SINGLE_IMAGE",
            detected_task="VQA",
            status="COMPLETED",
            confidence=0.91,
            plan={
                "goal": "Identify and classify land cover features and infrastructure",
                "steps": [
                    {"step": 1, "tool": "validate_inputs", "description": "Verify spectral resolution & cloud cover"},
                    {"step": 2, "tool": "compute_spectral_indices", "description": "Calculate NDVI and NDBI layers"},
                    {"step": 3, "tool": "model_inference", "description": "Execute RS_VQA specialist for semantic feature recognition"},
                ]
            },
            answer="The scene is characterized by dense riverine vegetation (NDVI > 0.62 covering 58.4 km²), alluvial sandbanks (14.2 km²), and transport infrastructure corridors along the southern perimeter.",
            completed_at=timezone.now(),
        )

        # 7. Create and compile PDF Report
        report = Report.objects.create(
            session=session,
            query=query_1,
            format="PDF",
            status="GENERATING",
        )
        try:
            generate_report_task(str(report.id))
            self.stdout.write(f"Report PDF generated for {user.username}.")
        except Exception as e:
            self.stdout.write(f"Report generation note: {e}")

        # 8. Add Audit Logs
        log_audit_event(user, "SESSION_CREATED", "Session", str(session.id), {"name": session.name})
        log_audit_event(user, "IMAGE_INGESTED", "ImageAsset", str(asset_pre.id), {"filename": asset_pre.original_filename})
        log_audit_event(user, "IMAGE_INGESTED", "ImageAsset", str(asset_post.id), {"filename": asset_post.original_filename})
        log_audit_event(user, "QUERY_EXECUTED", "Query", str(query_1.id), {"mode": "BI_TEMPORAL", "area_km2": 18.42})
