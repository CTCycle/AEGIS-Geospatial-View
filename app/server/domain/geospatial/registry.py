from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from server.domain.geospatial.providers import ProviderRequest


@dataclass(frozen=True)
class CapabilityRegistrySnapshot:
    providers: list[dict[str, Any]]
    basemaps: list[dict[str, Any]]
    overlays: list[dict[str, Any]]
    cameras: list[dict[str, Any]]
    transit: list[dict[str, Any]]
    tools: list[dict[str, Any]]


@dataclass(frozen=True)
class RuntimeRegistrySnapshot:
    profiles: dict[str, dict[str, Any]]
    manifests: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class AttributionEntry:
    capability_id: str
    provider_id: str
    label: str
    url: str
    required: bool


class LiveValidationCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    capability_id: str
    status: str
    message: str | None = None
    feature_count: int | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiveValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_count: int = 0
    skipped_count: int = 0
    results: list[LiveValidationCheckResult] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error_count == 0


@dataclass(frozen=True)
class LiveCheck:
    provider_id: str
    request: ProviderRequest
    credential_env: str | None = None
    required_feature_count: int | None = None
