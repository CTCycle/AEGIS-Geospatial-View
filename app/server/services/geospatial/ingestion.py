from __future__ import annotations

import csv
import hashlib
import json
import shutil
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generator
from urllib.parse import urlparse

from server.domain.geospatial.ingestion import (
    DatasetIngestionPlan,
    DatasetIngestionResult,
)

###############################################################################
class IngestionManifestError(ValueError):
    """Raised when a downloadable dataset manifest is incomplete."""

###############################################################################
class IngestionExecutionError(RuntimeError):
    """Raised when an ingestion plan cannot be executed."""


REQUIRED_DOWNLOAD_FIELDS = {
    "sourceUrl",
    "license",
    "updateFrequency",
    "expectedFormat",
    "compression",
}

REQUIRED_STORAGE_FIELDS = {"rawPath", "normalizedPath", "tilePath"}

###############################################################################
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
        checksum_url=_optional_str(download.get("checksumUrl")),
        checksum_sha256=_optional_str(download.get("checksumSha256")),
        compression=str(download.get("compression") or "none"),
        geometry_type=str(normalization.get("geometryType") or "Unknown"),
        id_field=_optional_str(normalization.get("idField")),
        field_map=dict(normalization.get("fieldMap") or {}),
        validation=dict(manifest.get("validation") or {}),
    )

###############################################################################
def validate_ingestion_manifest(manifest: dict[str, Any]) -> list[str]:
    try:
        build_ingestion_plan(manifest)
    except IngestionManifestError as exc:
        return [str(exc)]
    return []

###############################################################################
def execute_ingestion_plan(
    plan: DatasetIngestionPlan,
    *,
    workspace_root: str | Path = ".",
) -> DatasetIngestionResult:
    root = Path(workspace_root)
    raw_dir = _safe_output_dir(root, plan.raw_path)
    normalized_dir = _safe_output_dir(root, plan.normalized_path)
    tile_dir = _safe_output_dir(root, plan.tile_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    tile_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    raw_file = _materialize_source(plan, raw_dir)
    checksum = _sha256(raw_file)
    expected_checksum = plan.checksum_sha256 or _resolve_checksum_url(plan)
    if expected_checksum and checksum.lower() != expected_checksum.lower():
        raise IngestionExecutionError(
            f"Checksum mismatch for {plan.capability_id}: expected "
            f"{expected_checksum}, got {checksum}."
        )

    metadata_file = raw_dir / "source_metadata.json"
    _write_json(
        metadata_file,
        {
            "capabilityId": plan.capability_id,
            "sourceUrl": plan.source_url,
            "sourceTimestamp": datetime.now(UTC).isoformat(),
            "rawFile": str(raw_file),
            "sha256": checksum,
            "checksumSource": "checksumSha256" if plan.checksum_sha256 else ("checksumUrl" if plan.checksum_url else None),
            "expectedFormat": plan.expected_format,
            "compression": plan.compression,
            "targetCrs": plan.target_crs,
        },
    )

    normalized_file: Path | None = None
    feature_count = 0
    expected_format = plan.expected_format.lower()
    if expected_format == "csv":
        normalized_file, feature_count = _normalize_csv(plan, raw_file, normalized_dir)
    elif expected_format == "geojson":
        normalized_file, feature_count, invalid_count = _normalize_geojson(
            plan, raw_file, normalized_dir
        )
        if invalid_count:
            warnings.append(f"Dropped {invalid_count} GeoJSON feature(s) with invalid geometry.")
    else:
        warnings.append(
            f"{plan.expected_format} normalization requires optional geospatial ingestion dependencies."
        )

    _validate_feature_count(plan, feature_count)
    _validate_bbox_intersection(plan, normalized_file)
    spatial_index_file = (
        _write_spatial_index(normalized_file, normalized_dir) if plan.spatial_index and normalized_file else None
    )
    text_index_file = (
        _write_text_index(normalized_file, normalized_dir) if plan.text_index and normalized_file else None
    )
    tile_manifest_file = (
        _write_tile_manifest(plan, normalized_file, tile_dir, feature_count)
        if plan.vector_tile
        else None
    )
    health_file = normalized_dir / "health.json"
    _write_json(
        health_file,
        {
            "capabilityId": plan.capability_id,
            "status": "functional" if normalized_file else "partial",
            "featureCount": feature_count,
            "lastIngested": datetime.now(UTC).isoformat(),
            "warnings": warnings,
        },
    )
    return DatasetIngestionResult(
        capability_id=plan.capability_id,
        raw_file=str(raw_file),
        normalized_file=str(normalized_file) if normalized_file else None,
        metadata_file=str(metadata_file),
        spatial_index_file=str(spatial_index_file) if spatial_index_file else None,
        text_index_file=str(text_index_file) if text_index_file else None,
        tile_manifest_file=str(tile_manifest_file) if tile_manifest_file else None,
        health_file=str(health_file),
        feature_count=feature_count,
        warnings=warnings,
    )

###############################################################################
def _required_dict(manifest: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = manifest.get(field_name)
    if not isinstance(value, dict):
        raise IngestionManifestError(f"{field_name} must be an object.")
    return value

###############################################################################
def _require_fields(payload: dict[str, Any], fields: set[str], prefix: str) -> None:
    missing = sorted(field for field in fields if field not in payload)
    if missing:
        raise IngestionManifestError(
            f"{prefix} is missing required fields: {', '.join(missing)}"
        )

###############################################################################
def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

###############################################################################
def _safe_output_dir(root: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        raise IngestionExecutionError("Ingestion storage paths must be repository-relative.")
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    if root_resolved not in resolved.parents and resolved != root_resolved:
        raise IngestionExecutionError("Ingestion storage path escapes the workspace root.")
    return resolved

###############################################################################
def _materialize_source(plan: DatasetIngestionPlan, raw_dir: Path) -> Path:
    direct_source = Path(plan.source_url)
    if direct_source.exists():
        destination = raw_dir / direct_source.name
        shutil.copyfile(direct_source, destination)
        return destination
    parsed = urlparse(plan.source_url)
    filename = Path(parsed.path).name or f"{plan.capability_id}.{plan.expected_format}"
    destination = raw_dir / filename
    if parsed.scheme in {"", "file"}:
        source = Path(parsed.path if parsed.scheme == "file" else plan.source_url)
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.is_file():
            raise IngestionExecutionError(f"Local source file does not exist: {source}")
        shutil.copyfile(source, destination)
        return destination
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(plan.source_url, timeout=30) as response:
            destination.write_bytes(response.read())
        return destination
    raise IngestionExecutionError(f"Unsupported source URL scheme: {parsed.scheme}")

###############################################################################
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

###############################################################################
def _resolve_checksum_url(plan: DatasetIngestionPlan) -> str | None:
    if not plan.checksum_url:
        return None
    parsed = urlparse(plan.checksum_url)
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(plan.checksum_url, timeout=30) as response:
            text = response.read().decode("utf-8")
    else:
        source = Path(parsed.path if parsed.scheme == "file" else plan.checksum_url)
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.is_file():
            raise IngestionExecutionError(f"Checksum file does not exist: {source}")
        text = source.read_text(encoding="utf-8")
    for token in text.replace("\r", " ").replace("\n", " ").split():
        candidate = token.strip()
        if len(candidate) == 64 and all(char in "0123456789abcdefABCDEF" for char in candidate):
            return candidate
    raise IngestionExecutionError(f"Checksum URL did not contain a SHA-256 digest for {plan.capability_id}.")

###############################################################################
def _normalize_csv(
    plan: DatasetIngestionPlan, raw_file: Path, normalized_dir: Path
) -> tuple[Path, int]:
    output = normalized_dir / f"{plan.capability_id}.geojson"
    field_map = plan.field_map or {}
    lat_fields = ("latitude", "lat", "latitude_deg", "y")
    lon_fields = ("longitude", "lon", "lng", "longitude_deg", "x")
    features: list[dict[str, Any]] = []
    with raw_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            latitude = _first_float(row, lat_fields)
            longitude = _first_float(row, lon_fields)
            if latitude is None or longitude is None:
                continue
            properties = {
                field_map.get(key, key): value
                for key, value in row.items()
                if key not in lat_fields and key not in lon_fields
            }
            feature_id = row.get(plan.id_field or "") or properties.get("id") or str(index)
            features.append(
                {
                    "type": "Feature",
                    "id": str(feature_id),
                    "properties": properties,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                }
            )
    _write_json(output, {"type": "FeatureCollection", "features": features})
    return output, len(features)

###############################################################################
def _normalize_geojson(
    plan: DatasetIngestionPlan, raw_file: Path, normalized_dir: Path
) -> tuple[Path, int, int]:
    output = normalized_dir / f"{plan.capability_id}.geojson"
    payload = json.loads(raw_file.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise IngestionExecutionError("GeoJSON source must be a FeatureCollection.")
    valid_features = []
    invalid_count = 0
    for feature in payload["features"]:
        if not isinstance(feature, dict) or not _valid_geometry(feature.get("geometry")):
            invalid_count += 1
            continue
        valid_features.append(feature)
    _write_json(output, {"type": "FeatureCollection", "features": valid_features})
    return output, len(valid_features), invalid_count

###############################################################################
def _first_float(row: dict[str, str], field_names: tuple[str, ...]) -> float | None:
    lowered = {key.lower(): value for key, value in row.items()}
    for field_name in field_names:
        value = lowered.get(field_name)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except ValueError:
            continue
        if field_name in {"latitude", "lat", "latitude_deg", "y"} and not -90 <= parsed <= 90:
            return None
        if field_name in {"longitude", "lon", "lng", "longitude_deg", "x"} and not -180 <= parsed <= 180:
            return None
        return parsed
    return None

###############################################################################
def _validate_feature_count(plan: DatasetIngestionPlan, feature_count: int) -> None:
    validation = plan.validation or {}
    minimum = validation.get("minFeatureCount")
    if minimum is not None and feature_count < int(minimum):
        raise IngestionExecutionError(
            f"{plan.capability_id} produced {feature_count} features; expected at least {minimum}."
        )

###############################################################################
def _validate_bbox_intersection(plan: DatasetIngestionPlan, normalized_file: Path | None) -> None:
    validation = plan.validation or {}
    expected_bbox = validation.get("bboxMustIntersect")
    if expected_bbox is None or normalized_file is None:
        return
    if (
        not isinstance(expected_bbox, list)
        or len(expected_bbox) != 4
        or not all(isinstance(item, int | float) for item in expected_bbox)
    ):
        raise IngestionExecutionError("validation.bboxMustIntersect must contain four numbers.")
    payload = json.loads(normalized_file.read_text(encoding="utf-8"))
    feature_bbox = _feature_collection_bounds(payload)
    if feature_bbox is None:
        return
    if not _bboxes_intersect(feature_bbox, [float(item) for item in expected_bbox]):
        raise IngestionExecutionError(
            f"{plan.capability_id} normalized bbox {feature_bbox} does not intersect "
            f"required bbox {expected_bbox}."
        )

###############################################################################
def _write_spatial_index(normalized_file: Path, normalized_dir: Path) -> Path:
    payload = json.loads(normalized_file.read_text(encoding="utf-8"))
    bounds = _feature_collection_bounds(payload)
    if bounds is None:
        bounds = [-180.0, -90.0, 180.0, 90.0]
    output = normalized_dir / "spatial_index.json"
    _write_json(output, {"bbox": bounds, "indexType": "bbox-summary"})
    return output

###############################################################################
def _feature_collection_bounds(payload: dict[str, Any]) -> list[float] | None:
    bounds = [180.0, 90.0, -180.0, -90.0]
    for feature in payload.get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates")
        for lon, lat in _iter_coordinate_pairs(coordinates):
            bounds = [
                min(bounds[0], lon),
                min(bounds[1], lat),
                max(bounds[2], lon),
                max(bounds[3], lat),
            ]
    if bounds == [180.0, 90.0, -180.0, -90.0]:
        return None
    return bounds

###############################################################################
def _bboxes_intersect(left: list[float], right: list[float]) -> bool:
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )

###############################################################################
def _write_text_index(normalized_file: Path, normalized_dir: Path) -> Path:
    payload = json.loads(normalized_file.read_text(encoding="utf-8"))
    terms: dict[str, list[str]] = {}
    for feature in payload.get("features", []):
        feature_id = str(feature.get("id") or "")
        for value in feature.get("properties", {}).values():
            if not isinstance(value, str):
                continue
            for term in value.lower().replace(",", " ").split():
                if len(term) >= 3:
                    terms.setdefault(term, []).append(feature_id)
    output = normalized_dir / "text_index.json"
    _write_json(output, {"indexType": "term-to-feature", "terms": terms})
    return output

###############################################################################
def _write_tile_manifest(
    plan: DatasetIngestionPlan, normalized_file: Path | None, tile_dir: Path, feature_count: int
) -> Path:
    output = tile_dir / "tile_manifest.json"
    _write_json(
        output,
        {
            "capabilityId": plan.capability_id,
            "source": str(normalized_file) if normalized_file else None,
            "tileFormat": "geojson-vector-tile-ready",
            "featureCount": feature_count,
            "requiresOptionalTiler": True,
        },
    )
    return output

###############################################################################
def _is_point(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 2 and all(
        isinstance(item, int | float) for item in value[:2]
    )

###############################################################################
def _valid_geometry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    geometry_type = str(value.get("type") or "")
    coordinates = value.get("coordinates")
    if geometry_type == "Point":
        return _is_coordinate_pair(coordinates)
    if geometry_type == "LineString":
        return isinstance(coordinates, list) and any(
            _is_coordinate_pair(item) for item in coordinates
        )
    if geometry_type == "Polygon":
        return isinstance(coordinates, list) and any(
            isinstance(ring, list) and any(_is_coordinate_pair(item) for item in ring)
            for ring in coordinates
        )
    if geometry_type == "MultiPoint":
        return isinstance(coordinates, list) and any(
            _is_coordinate_pair(item) for item in coordinates
        )
    if geometry_type == "MultiLineString":
        return isinstance(coordinates, list) and any(
            isinstance(line, list) and any(_is_coordinate_pair(item) for item in line)
            for line in coordinates
        )
    if geometry_type == "MultiPolygon":
        return isinstance(coordinates, list) and any(
            isinstance(polygon, list)
            and any(
                isinstance(ring, list) and any(_is_coordinate_pair(item) for item in ring)
                for ring in polygon
            )
            for polygon in coordinates
        )
    return False

###############################################################################
def _iter_coordinate_pairs(value: Any) -> Generator[tuple[float, float] | Any, Any, None]:
    if _is_coordinate_pair(value):
        yield float(value[0]), float(value[1])
        return
    if not isinstance(value, list):
        return
    for item in value:
        yield from _iter_coordinate_pairs(item)

###############################################################################
def _is_coordinate_pair(value: Any) -> bool:
    if not _is_point(value):
        return False
    lon, lat = float(value[0]), float(value[1])
    return -180 <= lon <= 180 and -90 <= lat <= 90

###############################################################################
def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
