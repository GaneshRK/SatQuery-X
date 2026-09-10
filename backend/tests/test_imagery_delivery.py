
"""Unit tests verifying the decoupled imagery delivery pipeline, visual previews, and dedicated endpoints."""

import os
import io
import pytest
import numpy as np
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.imagery.models import ImageAsset, ImageryArtifact
from apps.imagery.services.preview import generate_rgb_preview, generate_change_mask_artifact
from apps.imagery.services.artifacts import register_imagery_artifacts, make_absolute_url


@pytest.mark.django_db
def test_generate_rgb_preview_from_numpy():
    output_dir = os.path.join(settings.MEDIA_ROOT, "test_previews")
    os.makedirs(output_dir, exist_ok=True)
    p_path = os.path.join(output_dir, "test_rgb.webp")
    t_path = os.path.join(output_dir, "test_thumb.webp")

    # 4-band simulated Sentinel-2 array (Blue, Green, Red, NIR)
    arr = np.random.randint(200, 3000, size=(128, 128, 4), dtype=np.uint16)
    res = generate_rgb_preview(arr, p_path, t_path)

    assert os.path.exists(p_path)
    assert os.path.exists(t_path)
    assert res["width"] == 128
    assert res["height"] == 128

    # Verify preview is valid image
    with Image.open(p_path) as img:
        assert img.size == (128, 128)
        assert img.mode == "RGB"


@pytest.mark.django_db
def test_generate_change_mask_artifact():
    bounds = {"west": 76.85, "south": 10.95, "east": 77.10, "north": 11.15}
    res = generate_change_mask_artifact("test_query_001", bounds)

    assert os.path.exists(res["mask_png_path"])
    assert os.path.exists(res["mask_webp_path"])
    assert os.path.exists(res["mask_tif_path"])
    assert os.path.exists(res["geojson_path"])

    with Image.open(res["mask_png_path"]) as img:
        assert img.mode == "RGBA"


@pytest.mark.django_db
def test_register_imagery_artifacts_and_dedicated_views():
    from django.contrib.auth import get_user_model
    from apps.sessions.models import Session

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="test_analyst", defaults={"email": "test@satquery.ai"})
    session = Session.objects.create(user=user, name="Imagery Test Session")

    client = APIClient()

    # Create dummy PNG asset
    img_io = io.BytesIO()
    Image.new("RGB", (64, 64), color=(50, 150, 80)).save(img_io, format="PNG")
    uploaded = SimpleUploadedFile("sample_optic.png", img_io.getvalue(), content_type="image/png")

    asset = ImageAsset.objects.create(
        session=session,
        file=uploaded,
        original_filename="sample_optic.png",
        sensor="SENTINEL-2",
        modality="OPTICAL",
        file_format="PNG",
        width=64,
        height=64,
    )

    dto = register_imagery_artifacts(asset)
    assert dto.id == str(asset.id)
    assert dto.satellite == "SENTINEL-2"
    assert dto.preview_url.endswith(".webp") or dto.preview_url.endswith(".png")

    # Test dedicated detail endpoint
    res = client.get(f"/api/imagery/{asset.id}/")
    assert res.status_code == 200
    assert res.data["id"] == str(asset.id)
    assert "geotiff_url" in res.data
    assert "preview_url" in res.data
    assert "thumbnail_url" in res.data
    assert res.data["preview_url"].endswith(".webp") or res.data["preview_url"].endswith(".png")

    # Test dedicated preview serving endpoint
    prev_res = client.get(f"/api/imagery/{asset.id}/preview/")
    assert prev_res.status_code == 200
    assert prev_res["Content-Type"] in ("image/webp", "image/png", "image/jpeg")


@pytest.mark.django_db
def test_contract_query_returns_rgb_previews_not_geotiff_for_browser():
    client = APIClient()

    res = client.post(
        "/api/analysis/query/",
        {
            "query": "Show areas where vegetation has decreased around Coimbatore in the last 6 months.",
            "location": "Coimbatore, Tamil Nadu",
            "source": "sentinel-2",
        },
        format="json",
    )

    assert res.status_code == 200
    data = res.data

    # Workflow must classify as bi-temporal change
    assert data["workflow"] in ("BI_TEMPORAL", "CHANGE_DETECTION")

    # Observations check
    assert "observations" in data
    assert "t1" in data["observations"]
    assert "t2" in data["observations"]

    t1 = data["observations"]["t1"]
    t2 = data["observations"]["t2"]

    # CRITICAL TEST: Browser preview URLs must NOT be raw GeoTIFF .tif files
    assert not t1["preview_url"].lower().endswith(".tif"), "Browser preview must not be .tif"
    assert not t2["preview_url"].lower().endswith(".tif"), "Browser preview must not be .tif"
    assert t1["preview_url"].lower().endswith(".webp") or t1["preview_url"].lower().endswith(".png")
    assert t2["preview_url"].lower().endswith(".webp") or t2["preview_url"].lower().endswith(".png")

    # Top-level backward compatibility URLs must also NOT be .tif for browser tags
    if data.get("before_image_url"):
        assert not data["before_image_url"].lower().endswith(".tif")
    if data.get("after_image_url"):
        assert not data["after_image_url"].lower().endswith(".tif")

    # Raw scientific GeoTIFF URLs must be preserved
    assert t1["geotiff_url"].lower().endswith(".tif") or ".tif" in t1["geotiff_url"].lower()
    assert t2["geotiff_url"].lower().endswith(".tif") or ".tif" in t2["geotiff_url"].lower()

    # Analysis artifacts check
    assert "analysis" in data
    assert data["analysis"]["change_mask_url"] is not None
    assert data["analysis"]["change_mask_url"].lower().endswith(".webp") or data["analysis"]["change_mask_url"].lower().endswith(".png")
    assert data["analysis"]["change_mask_geotiff_url"].lower().endswith(".tif")
    assert data["analysis"]["change_geojson_url"].lower().endswith(".geojson")

    # Confidence breakdown check
    assert "confidence_breakdown" in data
    assert "data_quality_pct" in data["confidence_breakdown"]
    assert "model_confidence_pct" in data["confidence_breakdown"]
    assert "geometry_quality_pct" in data["confidence_breakdown"]
    assert "result_confidence_pct" in data["confidence_breakdown"]
