from __future__ import annotations
import logging
import os
import time
import urllib.parse
import urllib.request
import json
from typing import Any
from django.conf import settings

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


class CDSETokenManager:
    """
    Manages OAuth2 access tokens for Copernicus Data Space Ecosystem (CDSE).
    Implements token caching, expiry checking, and automatic refresh.
    Credentials remain strictly server-side.
    """
    _instance: CDSETokenManager | None = None

    def __new__(cls) -> CDSETokenManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._access_token = None
            cls._instance._refresh_token = None
            cls._instance._expires_at = 0.0
        return cls._instance

    @property
    def username(self) -> str:
        return getattr(settings, "CDSE_USERNAME", None) or os.getenv("CDSE_USERNAME", "")

    @property
    def password(self) -> str:
        return getattr(settings, "CDSE_PASSWORD", None) or os.getenv("CDSE_PASSWORD", "")

    @property
    def client_id(self) -> str:
        return getattr(settings, "CDSE_CLIENT_ID", None) or os.getenv("CDSE_CLIENT_ID", "cdse-public")

    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    def get_access_token(self) -> str | None:
        """
        Returns a valid access token. Refreshes or re-authenticates as needed.
        Returns None if credentials are not configured or authentication fails.
        """
        if not self.is_configured():
            return None

        now = time.time()
        # Return cached token if valid for at least 60 more seconds
        if self._access_token and self._expires_at > (now + 60):
            return self._access_token

        # Try refresh if we have a refresh token
        if self._refresh_token:
            token = self._refresh_token_grant()
            if token:
                return token

        # Fallback to password grant
        return self._password_grant()

    def _password_grant(self) -> str | None:
        payload = {
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
        }
        return self._request_token(payload)

    def _refresh_token_grant(self) -> str | None:
        payload = {
            "client_id": self.client_id,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }
        return self._request_token(payload)

    def _request_token(self, payload: dict[str, Any]) -> str | None:
        try:
            encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                CDSE_TOKEN_URL,
                data=encoded_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "SatQuery-AI/2.0 (CDSE Auth Manager)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    self._access_token = data.get("access_token")
                    self._refresh_token = data.get("refresh_token")
                    expires_in = float(data.get("expires_in", 300))
                    self._expires_at = time.time() + expires_in
                    logger.info("Successfully acquired CDSE access token (expires in %ds)", expires_in)
                    return self._access_token
                else:
                    logger.warning("CDSE Token request returned HTTP %s", response.status)
        except urllib.error.HTTPError as he:
            logger.warning("CDSE Token HTTP error: %s (code %s)", he.reason, he.code)
        except Exception as e:
            logger.warning("CDSE Token acquisition error: %s", str(e))

        return None

    def get_auth_headers(self) -> dict[str, str]:
        token = self.get_access_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "CDSE_USERNAME or CDSE_PASSWORD not configured in environment.",
                "healthy": False,
            }
        token = self.get_access_token()
        if token:
            return {
                "status": "healthy",
                "message": "CDSE OAuth2 authentication active.",
                "healthy": True,
            }
        return {
            "status": "unavailable",
            "message": "CDSE authentication failed or endpoint unreachable.",
            "healthy": False,
        }
