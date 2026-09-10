"""Safe external-provider boundary for integration tests and runtime adapters.

The boundary keeps provider failures structured and makes provider injection
explicit. It never substitutes synthetic observations for a failed real
provider. Test doubles must be injected by the caller and are marked as such.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .base import (
    SatelliteProviderAuthenticationError,
    SatelliteProviderConfigurationError,
    SatelliteProviderError,
    SatelliteProviderRequestError,
    SatelliteProviderResponseError,
)


@dataclass(frozen=True)
class ProviderCallResult:
    status: str
    operation: str
    data: Any = None
    error_code: str | None = None
    message: str | None = None
    provider: str | None = None
    test_double: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation": self.operation,
            "data": self.data,
            "error_code": self.error_code,
            "message": self.message,
            "provider": self.provider,
            "test_double": self.test_double,
        }


class SatelliteProviderBoundary:
    """Execute provider operations without hiding provider failures."""

    def __init__(self, provider: Any, *, test_double: bool = False):
        self.provider = provider
        self.test_double = bool(test_double)
        self.provider_name = str(getattr(provider, "slug", None) or getattr(provider, "name", None) or "unknown")

    def call(self, operation: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> ProviderCallResult:
        try:
            data = fn(*args, **kwargs)
            return ProviderCallResult(
                status="success",
                operation=operation,
                data=data,
                provider=self.provider_name,
                test_double=self.test_double,
            )
        except SatelliteProviderAuthenticationError as exc:
            return self._failure(operation, "AUTHENTICATION_FAILED", str(exc))
        except SatelliteProviderConfigurationError as exc:
            return self._failure(operation, "PROVIDER_MISCONFIGURED", str(exc))
        except SatelliteProviderResponseError as exc:
            return self._failure(operation, "INVALID_PROVIDER_RESPONSE", str(exc))
        except SatelliteProviderRequestError as exc:
            return self._failure(operation, "PROVIDER_REQUEST_FAILED", str(exc))
        except SatelliteProviderError as exc:
            return self._failure(operation, "PROVIDER_ERROR", str(exc))
        except (TimeoutError, ConnectionError) as exc:
            return self._failure(operation, "PROVIDER_NETWORK_FAILED", str(exc))
        except Exception as exc:
            return self._failure(operation, "UNEXPECTED_PROVIDER_ERROR", str(exc))

    def _failure(self, operation: str, code: str, message: str) -> ProviderCallResult:
        return ProviderCallResult(
            status="failed",
            operation=operation,
            error_code=code,
            message=message,
            provider=self.provider_name,
            test_double=self.test_double,
        )
