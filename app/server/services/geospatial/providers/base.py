from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol

from server.domain.geographics import ProviderCredentialValidationResult


class ProviderError(Exception):
    """Base error for geospatial provider execution failures."""


class ProviderAuthError(ProviderError):
    """Raised when a provider needs credentials that are unavailable or invalid."""


class ProviderCircuitOpenError(ProviderError):
    """Raised when a provider circuit is open after repeated failures."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider rejects or cannot satisfy rate limits."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its timeout."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider cannot be reached or is temporarily unhealthy."""


class ProviderMalformedPayloadError(ProviderError):
    """Raised when a provider returns a payload that cannot be normalized."""


@dataclass(frozen=True)
class ProviderRequest:
    capability_id: str
    bbox: tuple[float, float, float, float] | None = None
    zoom: int | None = None
    time: datetime | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    capability_id: str
    provider_id: str
    payload: dict[str, Any]
    attribution: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stale: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


FeatureRequest = ProviderRequest
ProviderResult = ProviderResponse

SENSITIVE_PARAM_MARKERS = ("key", "secret", "token", "password", "authorization")


def safe_request_params(params: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in sorted(params.items()):
        key_text = str(key)
        if any(marker in key_text.lower() for marker in SENSITIVE_PARAM_MARKERS):
            safe[key_text] = "<redacted>"
        else:
            safe[key_text] = value
    return safe


def provider_cache_key(provider_id: str, request: ProviderRequest) -> str:
    payload = {
        "provider": str(provider_id).strip().lower(),
        "capability_id": request.capability_id,
        "bbox": request.bbox,
        "zoom": request.zoom,
        "time": request.time.isoformat() if request.time else None,
        "params": safe_request_params(request.params),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{payload['provider']}:{request.capability_id}:{digest}"


def response_without_credentials(response: ProviderResponse) -> ProviderResponse:
    return ProviderResponse(
        capability_id=response.capability_id,
        provider_id=response.provider_id,
        payload=_redact_secrets(response.payload),
        attribution=list(response.attribution),
        warnings=list(response.warnings),
        stale=response.stale,
        fetched_at=response.fetched_at,
    )


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in SENSITIVE_PARAM_MARKERS):
                redacted[key_text] = "<redacted>"
            else:
                redacted[key_text] = _redact_secrets(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


class GeospatialProvider(Protocol):
    provider_id: str

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        """Fetch and normalize a provider payload for a geospatial capability."""

    async def fetch_features(self, request: FeatureRequest) -> ProviderResult:
        """Fetch features using the canonical geospatial provider contract."""

    async def validate_credentials(
        self, credentials: Mapping[str, str]
    ) -> ProviderCredentialValidationResult:
        """Validate provider credentials without persisting them."""


async def unsupported_credential_validation(
    provider_id: str,
) -> ProviderCredentialValidationResult:
    return ProviderCredentialValidationResult(
        provider_id=provider_id,
        valid=False,
        status="unsupported",
        message="Credential validation is not implemented for this provider.",
    )
