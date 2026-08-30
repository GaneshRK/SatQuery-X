"""Pytest fixtures for SatQuery-X test suite."""

from __future__ import annotations

import io
import uuid
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.api.app import create_app
from backend.db.store import get_datastore


@pytest.fixture
def test_app():
    return create_app()


@pytest.fixture
async def client(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c


@pytest.fixture
def clean_store():
    store = get_datastore()
    store._sessions.clear()
    store._images.clear()
    store._queries.clear()
    store._reports.clear()
    return store


@pytest.fixture
def synthetic_optical_png() -> bytes:
    """Generates a synthetic 256x256 optical RGB image."""
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:, :128, 1] = 180  # Left half green (vegetation)
    arr[:, 128:, 0] = 200  # Right half red/urban
    arr[:, 128:, 1] = 100
    arr[100:150, 100:150, 2] = 220  # Center blue pool/water
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def synthetic_sar_png() -> bytes:
    """Generates a synthetic 256x256 SAR single-band image."""
    arr = np.zeros((256, 256), dtype=np.uint8)
    arr[:, :128] = 40   # Dark vegetation (low backscatter)
    arr[:, 128:] = 210  # Bright built-up double-bounce
    arr[100:150, 100:150] = 10  # Very dark specular water
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def synthetic_bitemporal_pngs() -> tuple[bytes, bytes]:
    """Generates T1 (pre) and T2 (post) images with visible change."""
    t1_arr = np.zeros((256, 256, 3), dtype=np.uint8)
    t1_arr[:, :] = [34, 139, 34]  # All green forest at T1

    t2_arr = t1_arr.copy()
    t2_arr[50:180, 50:180] = [200, 160, 120]  # Cleared/built area at T2

    buf1 = io.BytesIO()
    Image.fromarray(t1_arr).save(buf1, format="PNG")

    buf2 = io.BytesIO()
    Image.fromarray(t2_arr).save(buf2, format="PNG")

    return buf1.getvalue(), buf2.getvalue()
