"""Pytest fixtures for SatQuery AI Django test suite."""

from __future__ import annotations

import io
import numpy as np
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from PIL import Image

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def demo_user(db):
    return User.objects.create_user(username="test_analyst", password="password123", role="demo")


@pytest.fixture
def auth_client(db, demo_user, api_client):
    login_res = api_client.post(
        "/api/v1/auth/login/",
        {"username": demo_user.username, "password": "password123"},
        format="json",
    )
    token = login_res.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def synthetic_optical_png() -> bytes:
    """Generates a synthetic 256x256 optical RGB image with green vegetation."""
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:, :] = [60, 140, 60]  # Vegetation
    arr[100:150, 100:150] = [180, 180, 180]  # Built-up
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def synthetic_sar_png() -> bytes:
    """Generates a synthetic 256x256 SAR radar image."""
    arr = np.random.randint(50, 120, (256, 256), dtype=np.uint8)
    arr[100:150, 100:150] = 220  # Bright corner reflection (built-up double bounce)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
