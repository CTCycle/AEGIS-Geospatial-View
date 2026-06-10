from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TileBuildResult:
    capability_id: str
    tile_manifest_file: str
    source_file: str | None
    tile_format: str
    feature_count: int
    warnings: list[str]
