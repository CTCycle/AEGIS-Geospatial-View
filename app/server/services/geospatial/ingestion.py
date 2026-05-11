from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IngestionManifestError(ValueError):
    """Raised when a downloadable dataset manifest is incomplete."""


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


REQUIRED_DOWNLOAD_FIELDS = {
    "sourceUrl",
    "license",
    "updateFrequency",
    "expectedFormat",
    "compression",
}

REQUIRED_STORAGE_FIELDS = {"rawPath", "normalizedPath", "tilePath"}


def build_ingestion_plan(manifest: dict[str, Any]) -> DatasetIngestionPlan:
    if manifest.get("capabilityKind") != "dataset-ingestion":
        raise IngestionManifestError("Manifest is not a dataset-ingestion capability.")
    download = _required_dict(manifest, "download")
    storage = _required_dict(manifest, "storage")
    normalization = _required_dict(manifest, "normalization")
    indexing = _required_dict(manifest, "indexing")
    _require_fields(download, REQUIRED_DOWNLOAD_FIELDS, "download")
    _require_fields(storage, REQUIRED_STORAGE_FIELDS, "storage")
    source_url = str(download.get("sourceUrl") or "").strip()
    if not source_url:
        raise IngestionManifestError("download.sourceUrl is required.")
    return DatasetIngestionPlan(
        capability_id=str(manifest.get("id") or ""),
        source_url=source_url,
        raw_path=str(storage["rawPath"]),
        normalized_path=str(storage["normalizedPath"]),
        tile_path=str(storage["tilePath"]),
        expected_format=str(download["expectedFormat"]),
        target_crs=str(normalization.get("targetCrs") or "EPSG:4326"),
        spatial_index=bool(indexing.get("spatialIndex", False)),
        text_index=bool(indexing.get("textIndex", False)),
        vector_tile=bool(indexing.get("vectorTile", False)),
    )


def validate_ingestion_manifest(manifest: dict[str, Any]) -> list[str]:
    try:
        build_ingestion_plan(manifest)
    except IngestionManifestError as exc:
        return [str(exc)]
    return []


def _required_dict(manifest: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = manifest.get(field_name)
    if not isinstance(value, dict):
        raise IngestionManifestError(f"{field_name} must be an object.")
    return value


def _require_fields(payload: dict[str, Any], fields: set[str], prefix: str) -> None:
    missing = sorted(field for field in fields if field not in payload)
    if missing:
        raise IngestionManifestError(
            f"{prefix} is missing required fields: {', '.join(missing)}"
        )
