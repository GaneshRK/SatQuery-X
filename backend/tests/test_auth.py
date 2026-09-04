import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.mark.django_db
def test_jwt_auth_flow():
    user = User.objects.create_user(username="testanalyst", password="password123", role="demo")
    client = APIClient()

    # 1. Login
    login_res = client.post("/api/v1/auth/login/", {"username": "testanalyst", "password": "password123"}, format="json")
    assert login_res.status_code == 200
    assert "access" in login_res.data
    assert "refresh" in login_res.data
    access_token = login_res.data["access"]
    refresh_token = login_res.data["refresh"]

    # 2. Get current user profile
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    me_res = client.get("/api/v1/auth/me/")
    assert me_res.status_code == 200
    assert me_res.data["username"] == "testanalyst"
    assert me_res.data["role"] == "demo"

    # 3. Refresh token
    client.credentials()  # clear
    refresh_res = client.post("/api/v1/auth/refresh/", {"refresh": refresh_token}, format="json")
    assert refresh_res.status_code == 200
    assert "access" in refresh_res.data
