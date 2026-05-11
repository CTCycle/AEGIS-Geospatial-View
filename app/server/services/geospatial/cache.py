from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any


class CacheLookupStatus(str, Enum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"


@dataclass(frozen=True)
class CacheLookup:
    status: CacheLookupStatus
    value: Any | None = None

    @property
    def usable(self) -> bool:
        return self.status in {CacheLookupStatus.HIT, CacheLookupStatus.STALE}


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    expires_at: float
    stale_expires_at: float


class GeospatialCache:
    def __init__(self, *, clock: Any | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = RLock()
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> CacheLookup:
        normalized = self._normalize_key(key)
        now = float(self._clock())
        with self._lock:
            entry = self._entries.get(normalized)
            if entry is None:
                return CacheLookup(status=CacheLookupStatus.MISS)
            if now <= entry.expires_at:
                return CacheLookup(status=CacheLookupStatus.HIT, value=entry.value)
            if now <= entry.stale_expires_at:
                return CacheLookup(status=CacheLookupStatus.STALE, value=entry.value)
            self._entries.pop(normalized, None)
            return CacheLookup(status=CacheLookupStatus.MISS)

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int,
        stale_while_revalidate_seconds: int = 0,
    ) -> None:
        normalized = self._normalize_key(key)
        ttl = max(0, int(ttl_seconds))
        stale_ttl = max(0, int(stale_while_revalidate_seconds))
        now = float(self._clock())
        expires_at = now + ttl
        with self._lock:
            self._entries[normalized] = _CacheEntry(
                value=value,
                expires_at=expires_at,
                stale_expires_at=expires_at + stale_ttl,
            )

    def invalidate(self, key: str) -> None:
        normalized = self._normalize_key(key)
        with self._lock:
            self._entries.pop(normalized, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _normalize_key(self, key: str) -> str:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("Cache key is required.")
        return normalized
