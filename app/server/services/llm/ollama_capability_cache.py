from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class OllamaToolCapabilityCacheRecord:
    supports_tools: bool
    source: str
    cached_at: float


class OllamaToolCapabilityCache:
    def __init__(self, *, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[tuple[str, str], OllamaToolCapabilityCacheRecord] = {}

    @staticmethod
    def _key(base_url: str, model: str) -> tuple[str, str]:
        return (base_url.rstrip("/").lower(), model.strip())

    def _is_expired(self, record: OllamaToolCapabilityCacheRecord, now: float) -> bool:
        return now - record.cached_at >= self.ttl_seconds

    def get(self, base_url: str, model: str, now: float | None = None) -> bool | None:
        at = time() if now is None else now
        key = self._key(base_url, model)
        record = self._records.get(key)
        if record is None:
            return None
        if self._is_expired(record, at):
            self._records.pop(key, None)
            return None
        return record.supports_tools

    def set(
        self,
        base_url: str,
        model: str,
        supports_tools: bool,
        now: float | None = None,
        source: str = "runtime",
    ) -> None:
        at = time() if now is None else now
        self._records[self._key(base_url, model)] = OllamaToolCapabilityCacheRecord(
            supports_tools=supports_tools,
            source=source,
            cached_at=at,
        )

    def source(self, base_url: str, model: str, now: float | None = None) -> str | None:
        at = time() if now is None else now
        key = self._key(base_url, model)
        record = self._records.get(key)
        if record is None:
            return None
        if self._is_expired(record, at):
            self._records.pop(key, None)
            return None
        return record.source
