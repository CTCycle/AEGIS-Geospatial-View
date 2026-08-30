from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


###############################################################################
@dataclass(frozen=True)
class ProviderRequest:
    capability_id: str
    bbox: tuple[float, float, float, float] | None = None
    zoom: int | None = None
    time: datetime | None = None
    params: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


###############################################################################
@dataclass(frozen=True)
class ProviderResponse:
    capability_id: str
    provider_id: str
    payload: dict[str, Any]
    attribution: list[str] = field(default_factory=lambda: list[str]())
    warnings: list[str] = field(default_factory=lambda: list[str]())
    stale: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    result_status: Literal["ok", "valid_empty", "stale"] = "ok"
    result_type: Literal["features", "raster", "metadata", "unknown"] = "unknown"


###############################################################################
@dataclass(frozen=True)
class ProviderExecutionPolicy:
    timeout_seconds: float = 10.0
    max_attempts: int = 1
    circuit_breaker_failures: int = 3
    circuit_recovery_seconds: float = 60.0


FeatureRequest = ProviderRequest
ProviderResult = ProviderResponse
