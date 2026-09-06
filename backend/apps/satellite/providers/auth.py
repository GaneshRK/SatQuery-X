"""
Copernicus Data Space Ecosystem authentication for SatQuery-X.

Responsibilities:
- Obtain OAuth2 access tokens from CDSE.
- Cache access and refresh tokens in process memory.
- Refresh tokens before they expire.
- Keep credentials strictly server-side.
- Expose authentication status for provider health checks.
- Never fabricate authentication success.

Environment variables / Django settings:
    CDSE_USERNAME
    CDSE_PASSWORD
    CDSE_CLIENT_ID       Optional; defaults to "cdse-public"

The token endpoint is the official CDSE Keycloak endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/"
    "protocol/openid-connect/token"
)

DEFAULT_CLIENT_ID = "cdse-public"

DEFAULT_TIMEOUT_SECONDS = 15.0

TOKEN_REFRESH_MARGIN_SECONDS = 60.0

USER_AGENT = (
    "SatQuery-X/1.0 "
    "(Copernicus Data Space Ecosystem Authentication Client)"
)


class CDSETokenManager:
    """
    Thread-safe OAuth2 token manager for Copernicus Data Space Ecosystem.

    The manager is intentionally process-local.

    Access tokens are:
    - never stored in the database,
    - never returned to the frontend,
    - never written into logs,
    - cached only in memory.

    Authentication behavior:

        valid cached token
                ↓
        refresh token grant
                ↓
        password grant
                ↓
        authentication failure

    No fake token or offline authentication state is generated.
    """

    _instance: CDSETokenManager | None = None
    _instance_lock = threading.Lock()

    def __new__(
        cls,
    ) -> CDSETokenManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)

                    instance._access_token = None
                    instance._refresh_token = None
                    instance._expires_at = 0.0
                    instance._token_lock = threading.RLock()
                    instance._last_error = None

                    cls._instance = instance

        return cls._instance

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @staticmethod
    def _setting_or_environment(
        setting_name: str,
        environment_name: str | None = None,
        default: str = "",
    ) -> str:
        """
        Read configuration from Django settings first, then environment.

        Empty settings do not override a populated environment variable.
        """

        environment_name = (
            environment_name or setting_name
        )

        try:
            value = getattr(
                settings,
                setting_name,
                None,
            )
        except Exception:
            value = None

        if value is not None:
            value = str(value).strip()

            if value:
                return value

        return str(
            os.getenv(
                environment_name,
                default,
            )
            or ""
        ).strip()

    @property
    def username(self) -> str:
        return self._setting_or_environment(
            "CDSE_USERNAME"
        )

    @property
    def password(self) -> str:
        return self._setting_or_environment(
            "CDSE_PASSWORD"
        )

    @property
    def client_id(self) -> str:
        return self._setting_or_environment(
            "CDSE_CLIENT_ID",
            default=DEFAULT_CLIENT_ID,
        ) or DEFAULT_CLIENT_ID

    @property
    def token_url(self) -> str:
        configured = self._setting_or_environment(
            "CDSE_TOKEN_URL",
            default=CDSE_TOKEN_URL,
        )

        return configured or CDSE_TOKEN_URL

    @property
    def timeout(self) -> float:
        raw = self._setting_or_environment(
            "CDSE_AUTH_TIMEOUT",
            default=str(
                DEFAULT_TIMEOUT_SECONDS
            ),
        )

        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = DEFAULT_TIMEOUT_SECONDS

        return max(1.0, value)

    def is_configured(self) -> bool:
        """
        Return whether the minimum CDSE credentials are configured.

        Client ID is optional because CDSE's public client ID is used by
        default.
        """

        return bool(
            self.username
            and self.password
            and self.client_id
        )

    # ------------------------------------------------------------------
    # Token state
    # ------------------------------------------------------------------

    def _cached_token_is_valid(
        self,
    ) -> bool:
        return bool(
            self._access_token
            and self._expires_at
            > (
                time.time()
                + TOKEN_REFRESH_MARGIN_SECONDS
            )
        )

    def _clear_tokens(
        self,
    ) -> None:
        self._access_token = None
        self._refresh_token = None
        self._expires_at = 0.0

    def clear(
        self,
    ) -> None:
        """
        Explicitly clear cached authentication state.
        """

        with self._token_lock:
            self._clear_tokens()
            self._last_error = None

    # ------------------------------------------------------------------
    # Public token API
    # ------------------------------------------------------------------

    def get_access_token(
        self,
    ) -> str | None:
        """
        Return a valid CDSE access token.

        Returns None when:
        - credentials are not configured,
        - refresh fails,
        - password authentication fails,
        - CDSE is unreachable,
        - CDSE returns an invalid response.

        No placeholder token is ever returned.
        """

        with self._token_lock:
            if self._cached_token_is_valid():
                return self._access_token

            if not self.is_configured():
                self._last_error = (
                    "CDSE credentials are not configured."
                )
                return None

            # ----------------------------------------------------------
            # Refresh an existing token first.
            # ----------------------------------------------------------

            if self._refresh_token:
                refreshed = (
                    self._refresh_token_grant()
                )

                if refreshed:
                    return refreshed

            # ----------------------------------------------------------
            # Fall back to password grant.
            # ----------------------------------------------------------

            return self._password_grant()

    # ------------------------------------------------------------------
    # OAuth2 grants
    # ------------------------------------------------------------------

    def _password_grant(
        self,
    ) -> str | None:
        payload = {
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
        }

        return self._request_token(
            payload,
            grant_type="password",
        )

    def _refresh_token_grant(
        self,
    ) -> str | None:
        if not self._refresh_token:
            return None

        payload = {
            "client_id": self.client_id,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }

        return self._request_token(
            payload,
            grant_type="refresh_token",
        )

    def _request_token(
        self,
        payload: dict[str, Any],
        grant_type: str,
    ) -> str | None:
        """
        Execute an OAuth2 token request.

        Secrets are deliberately excluded from logs and exceptions.
        """

        encoded_data = urllib.parse.urlencode(
            payload
        ).encode("utf-8")

        request = urllib.request.Request(
            url=self.token_url,
            data=encoded_data,
            headers={
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                status = int(
                    getattr(
                        response,
                        "status",
                        200,
                    )
                )

                raw = response.read()

        except urllib.error.HTTPError as exc:
            self._last_error = (
                f"CDSE OAuth2 returned HTTP {exc.code}."
            )

            logger.warning(
                "CDSE OAuth2 %s grant failed with HTTP %s.",
                grant_type,
                exc.code,
            )

            # A failed refresh token may be expired/revoked. Clear it so
            # the next call can use password authentication.
            if grant_type == "refresh_token":
                self._refresh_token = None

            return None

        except urllib.error.URLError as exc:
            self._last_error = (
                "CDSE OAuth2 endpoint is unreachable."
            )

            logger.warning(
                "CDSE OAuth2 %s grant could not reach "
                "the token endpoint: %s",
                grant_type,
                exc.reason,
            )

            return None

        except TimeoutError:
            self._last_error = (
                "CDSE OAuth2 token request timed out."
            )

            logger.warning(
                "CDSE OAuth2 %s grant timed out.",
                grant_type,
            )

            return None

        except OSError as exc:
            self._last_error = (
                "CDSE OAuth2 network request failed."
            )

            logger.warning(
                "CDSE OAuth2 %s grant failed due to "
                "a network error: %s",
                grant_type,
                exc,
            )

            return None

        except Exception as exc:
            self._last_error = (
                "Unexpected CDSE OAuth2 error."
            )

            logger.exception(
                "Unexpected CDSE OAuth2 %s grant error.",
                grant_type,
            )

            return None

        if status < 200 or status >= 300:
            self._last_error = (
                f"CDSE OAuth2 returned HTTP {status}."
            )

            logger.warning(
                "CDSE OAuth2 %s grant returned HTTP %s.",
                grant_type,
                status,
            )

            return None

        try:
            decoded = raw.decode(
                "utf-8"
            )

            data = json.loads(
                decoded
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            self._last_error = (
                "CDSE OAuth2 returned invalid JSON."
            )

            logger.warning(
                "CDSE OAuth2 %s grant returned "
                "invalid JSON.",
                grant_type,
            )

            return None

        if not isinstance(data, dict):
            self._last_error = (
                "CDSE OAuth2 returned an invalid response."
            )

            logger.warning(
                "CDSE OAuth2 %s grant returned "
                "a non-object response.",
                grant_type,
            )

            return None

        access_token = data.get(
            "access_token"
        )

        if not access_token or not isinstance(
            access_token,
            str,
        ):
            self._last_error = (
                "CDSE OAuth2 response did not contain "
                "an access token."
            )

            logger.warning(
                "CDSE OAuth2 %s grant succeeded HTTP-wise "
                "but returned no access token.",
                grant_type,
            )

            return None

        # --------------------------------------------------------------
        # Expiry
        # --------------------------------------------------------------

        expires_in_raw = data.get(
            "expires_in"
        )

        try:
            expires_in = float(
                expires_in_raw
            )

        except (
            TypeError,
            ValueError,
        ):
            # CDSE normally supplies expires_in. We cannot know an
            # accurate lifetime if the provider omits it, so do not
            # manufacture a long-lived token lifetime.
            expires_in = 0.0

        if expires_in < 0:
            expires_in = 0.0

        # --------------------------------------------------------------
        # Cache
        # --------------------------------------------------------------

        self._access_token = access_token

        refresh_token = data.get(
            "refresh_token"
        )

        if isinstance(
            refresh_token,
            str,
        ) and refresh_token.strip():
            self._refresh_token = (
                refresh_token.strip()
            )

        elif grant_type == "refresh_token":
            # If CDSE did not return a replacement refresh token,
            # retain the current one only when it is still present.
            pass

        self._expires_at = (
            time.time()
            + expires_in
        )

        self._last_error = None

        logger.info(
            "CDSE OAuth2 authentication succeeded "
            "using %s grant.",
            grant_type,
        )

        return access_token

    # ------------------------------------------------------------------
    # Authorization headers
    # ------------------------------------------------------------------

    def get_auth_headers(
        self,
    ) -> dict[str, str]:
        """
        Return an Authorization header when authentication succeeds.

        Public STAC catalogue endpoints can be called without this header,
        so an unconfigured CDSE account simply produces an empty dictionary.

        The method never returns a fabricated Bearer token.
        """

        token = self.get_access_token()

        if not token:
            return {}

        return {
            "Authorization": (
                f"Bearer {token}"
            )
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return authentication health without exposing secrets.

        Possible states:
            not_configured
            healthy
            unavailable
        """

        with self._token_lock:
            configured = self.is_configured()

            if not configured:
                return {
                    "status": "not_configured",
                    "healthy": False,
                    "configured": False,
                    "message": (
                        "CDSE_USERNAME and CDSE_PASSWORD "
                        "are not configured."
                    ),
                }

            token = self.get_access_token()

            if token:
                remaining = max(
                    0.0,
                    self._expires_at
                    - time.time(),
                )

                return {
                    "status": "healthy",
                    "healthy": True,
                    "configured": True,
                    "token_cached": True,
                    "expires_in_seconds": int(
                        remaining
                    ),
                    "message": (
                        "CDSE OAuth2 authentication is active."
                    ),
                }

            return {
                "status": "unavailable",
                "healthy": False,
                "configured": True,
                "token_cached": False,
                "message": (
                    self._last_error
                    or (
                        "CDSE authentication failed."
                    )
                ),
            }


__all__ = [
    "CDSE_TOKEN_URL",
    "CDSETokenManager",
]