"""Tests for deterministic computer vision algorithms in geospatial/cv_engine.py."""

import numpy as np
import pytest
from apps.geospatial.cv_engine import (
    otsu_threshold,
    segment_water,
    segment_vegetation,
    detect_and_count_structures,
)


def test_otsu_threshold():
    # Continuous bimodal distribution between -1.0 and 1.0 (spectral index values)
    data = np.concatenate([np.full(500, -0.6), np.full(500, 0.7)])
    thresh = otsu_threshold(data)
    assert -0.6 < thresh < 0.7, f"Expected threshold between modes, got {thresh}"


def test_segment_water_optical():
    # 64x64x4 array (H, W, Bands): R, G, B, NIR
    r = np.full((64, 64, 1), 50, dtype=np.uint8)
    g = np.full((64, 64, 1), 100, dtype=np.uint8)
    b = np.full((64, 64, 1), 120, dtype=np.uint8)
    nir = np.full((64, 64, 1), 180, dtype=np.uint8)
    # Create distinct water region in top half (low NIR, high blue/green)
    nir[:32, :, 0] = 15
    b[:32, :, 0] = 160
    stack = np.concatenate([r, g, b, nir], axis=2)

    features = segment_water(stack)
    assert isinstance(features, list)
    assert len(features) > 0
    assert features[0].label == "water_body"
    assert features[0].pixel_count > 0


def test_segment_vegetation():
    r = np.full((64, 64, 1), 40, dtype=np.uint8)
    g = np.full((64, 64, 1), 120, dtype=np.uint8)
    b = np.full((64, 64, 1), 50, dtype=np.uint8)
    nir = np.full((64, 64, 1), 220, dtype=np.uint8)
    # Lower half non-vegetated
    nir[32:, :, 0] = 30
    r[32:, :, 0] = 170
    stack = np.concatenate([r, g, b, nir], axis=2)

    features = segment_vegetation(stack)
    assert isinstance(features, list)
    assert len(features) > 0
    assert features[0].label in ("dense_vegetation", "vegetation_canopy")
    assert features[0].pixel_count > 0


def test_detect_and_count_structures():
    # Synthetic flat grayscale image with distinct high-contrast geometric bright squares
    canvas = np.full((128, 128, 3), 60, dtype=np.uint8)
    canvas[20:45, 20:45] = 240
    canvas[60:85, 60:85] = 245

    count, features = detect_and_count_structures(canvas, min_pixels=10)
    assert count >= 1, f"Expected at least 1 structure candidate, got {count}"
    assert len(features) >= 1
    assert features[0].label == "structure_candidate"
