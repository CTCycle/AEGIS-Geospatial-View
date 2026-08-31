from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from server.contracts.geospatial import ProviderCredentialValidationResult
from server.domain.geospatial.providers import (
    FeatureRequest,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
)


###############################################################################
class ProviderError(Exception):
    """Base error for geospatial provider execution failures."""


###############################################################################
class ProviderAuthError(ProviderError):
    """Raised when a provider needs credentials that are unavailable or invalid."""


###############################################################################
class ProviderCircuitOpenError(ProviderError):
    """Raised when a provider circuit is open after repeated failures."""


###############################################################################
class ProviderRateLimitError(ProviderError):
    """Raised when a provider rejects or cannot satisfy rate limits."""

    # -------------------------------------------------------------------------
    def __init__(
        self, message: str, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


###############################################################################
class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its timeout."""


###############################################################################
class ProviderUnavailableError(ProviderError):
    """Raised when a provider cannot be reached or is temporarily unhealthy."""


###############################################################################
class ProviderMalformedPayloadError(ProviderError):
    """Raised when a provider returns a payload that cannot be normalized."""


###############################################################################
class ProviderInvalidQueryError(ProviderError):
    """Raised when a provider rejects a deterministic or invalid query."""


SENSITIVE_PARAM_MARKERS = ("key", "secret", "token", "password", "authorization")


###############################################################################
def safe_request_params(params: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in sorted(params.items()):
        key_text = str(key)
        if any(marker in key_text.lower() for marker in SENSITIVE_PARAM_MARKERS):
            safe[key_text] = "<redacted>"
        else:
            safe[key_text] = value
    return safe


###############################################################################
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


###############################################################################
def response_without_credentials(response: ProviderResponse) -> ProviderResponse:
    return ProviderResponse(
        capability_id=response.capability_id,
        provider_id=response.provider_id,
        payload=_redact_secrets(response.payload),
        attribution=list(response.attribution),
        warnings=list(response.warnings),
        stale=response.stale,
        fetched_at=response.fetched_at,
        result_status="stale" if response.stale else response.result_status,
        result_type=response.result_type,
        observation_time=response.observation_time,
        coverage=dict(response.coverage) if response.coverage is not None else None,
        spatial_resolution=response.spatial_resolution,
        units=dict(response.units),
        source_url=_redact_url_query(response.source_url)
        if response.source_url
        else None,
        partial=response.partial,
    )


###############################################################################
def _redact_secrets(value: Any) -> Any:
    if is_json_object(value):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in SENSITIVE_PARAM_MARKERS):
                redacted[key_text] = "<redacted>"
            else:
                redacted[key_text] = _redact_secrets(nested)
        return redacted
    if is_json_array(value):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, str) and "://" in value:
        return _redact_url_query(value)
    return value


###############################################################################
def _redact_url_query(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.query:
        return value
    query: list[tuple[str, str]] = []
    for key, nested in parse_qsl(parsed.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_PARAM_MARKERS):
            query.append((key, "<redacted>"))
        else:
            query.append((key, nested))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


###############################################################################
class GeospatialProvider(Protocol):
    provider_id: str

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        """Fetch and normalize a provider payload for a geospatial capability."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: FeatureRequest) -> ProviderResult:
        """Fetch features using the canonical geospatial provider contract."""
        response = await self.fetch(request)
        return response

    # -------------------------------------------------------------------------
    async def validate_credentials(
        self, credentials: Mapping[str, str]
    ) -> ProviderCredentialValidationResult:
        """Validate provider credentials without persisting them."""
        return await unsupported_credential_validation(self.provider_id)


###############################################################################
async def unsupported_credential_validation(
    provider_id: str,
) -> ProviderCredentialValidationResult:
    return ProviderCredentialValidationResult(
        provider_id=provider_id,
        valid=False,
        status="unsupported",
        message="Credential validation is not implemented for this provider.",
    )
