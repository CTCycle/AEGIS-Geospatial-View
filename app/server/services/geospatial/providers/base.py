from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


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


class GeospatialProvider(Protocol):
    provider_id: str

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        """Fetch and normalize a provider payload for a geospatial capability."""
