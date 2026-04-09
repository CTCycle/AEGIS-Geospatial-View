from __future__ import annotations

from dataclasses import dataclass

###############################################################################
@dataclass(frozen=True)
class LayerProviderEntry:
    name: str
    provider: str
    label: str
    aliases: tuple[str, ...]
    provider_name: str | None = None
    resolution_m: float | None = None
