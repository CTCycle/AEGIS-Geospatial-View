from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from server.domain.geographics import LayerHealthStatus


@dataclass(frozen=True)
class SourceHealthRecord:
    provider_id: str
    status: LayerHealthStatus
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    stale: bool = False


class SourceHealthMonitor:
    def __init__(self) -> None:
        self._records: dict[str, SourceHealthRecord] = {}

    def record(
        self,
        provider_id: str,
        status: LayerHealthStatus | str,
        *,
        message: str = "",
        stale: bool = False,
    ) -> SourceHealthRecord:
        normalized_provider = self._normalize_provider_id(provider_id)
        normalized_status = (
            status if isinstance(status, LayerHealthStatus) else LayerHealthStatus(status)
        )
        record = SourceHealthRecord(
            provider_id=normalized_provider,
            status=normalized_status,
            message=message,
            stale=stale,
        )
        self._records[normalized_provider] = record
        return record

    def get(self, provider_id: str) -> SourceHealthRecord | None:
        return self._records.get(self._normalize_provider_id(provider_id))

    def status_for_manifest(self, manifest: dict[str, object]) -> LayerHealthStatus:
        provider_id = str(manifest.get("provider") or "").strip().lower()
        if provider_id:
            recorded = self.get(provider_id)
            if recorded is not None:
                return recorded.status
        reliability = manifest.get("reliability")
        if isinstance(reliability, dict):
            value = reliability.get("status")
            if isinstance(value, str) and value:
                return LayerHealthStatus(value)
        return LayerHealthStatus.UNKNOWN

    def _normalize_provider_id(self, provider_id: str) -> str:
        normalized = str(provider_id).strip().lower()
        if not normalized:
            raise ValueError("Provider id is required.")
        return normalized
