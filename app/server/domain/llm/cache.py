from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaToolCapabilityCacheRecord:
    supports_tools: bool
    source: str
    cached_at: float
