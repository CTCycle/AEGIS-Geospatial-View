from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatasetIngestionPlan:
    capability_id: str
    source_url: str
    raw_path: str
    normalized_path: str
    tile_path: str
    expected_format: str
    target_crs: str
    spatial_index: bool
    text_index: bool
    vector_tile: bool
    checksum_url: str | None = None
    checksum_sha256: str | None = None
    compression: str = "none"
    geometry_type: str = "Unknown"
    id_field: str | None = None
    field_map: dict[str, str] | None = None
    validation: dict[str, Any] | None = None


@dataclass(frozen=True)
class DatasetIngestionResult:
    capability_id: str
    raw_file: str
    normalized_file: str | None
    metadata_file: str
    spatial_index_file: str | None
    text_index_file: str | None
    tile_manifest_file: str | None
    health_file: str
    feature_count: int
    warnings: list[str]
