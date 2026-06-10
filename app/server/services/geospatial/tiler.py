from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.domain.geospatial.tiler import TileBuildResult


###############################################################################
class TileBuildError(RuntimeError):
    """Raised when a geospatial dataset cannot be prepared for tile delivery."""


###############################################################################
def build_vector_tile_manifest(
    *,
    capability_id: str,
    normalized_geojson: str | Path | None,
    tile_dir: str | Path,
    tile_format: str = "geojson-vector-tile-ready",
) -> TileBuildResult:
    output_dir = Path(tile_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(normalized_geojson) if normalized_geojson else None
    feature_count = _feature_count(source_path) if source_path else 0
    warnings: list[str] = []
    if source_path is None:
        warnings.append("No normalized source was supplied; wrote an empty tile manifest.")
    elif not source_path.exists():
        raise TileBuildError(f"Normalized source does not exist: {source_path}")
    manifest_path = output_dir / "tile_manifest.json"
    payload = {
        "capabilityId": capability_id,
        "source": str(source_path) if source_path else None,
        "tileFormat": tile_format,
        "featureCount": feature_count,
        "requiresOptionalTiler": True,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return TileBuildResult(
        capability_id=capability_id,
        tile_manifest_file=str(manifest_path),
        source_file=str(source_path) if source_path else None,
        tile_format=tile_format,
        feature_count=feature_count,
        warnings=warnings,
    )


###############################################################################
def build_raster_tile_manifest(
    *,
    capability_id: str,
    source_raster: str | Path | None,
    tile_dir: str | Path,
    tile_format: str = "raster-tile-ready",
) -> TileBuildResult:
    output_dir = Path(tile_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(source_raster) if source_raster else None
    if source_path is not None and not source_path.exists():
        raise TileBuildError(f"Raster source does not exist: {source_path}")
    warnings = [] if source_path else ["No raster source was supplied; wrote metadata only."]
    manifest_path = output_dir / "tile_manifest.json"
    payload = {
        "capabilityId": capability_id,
        "source": str(source_path) if source_path else None,
        "tileFormat": tile_format,
        "featureCount": 0,
        "requiresOptionalTiler": True,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return TileBuildResult(
        capability_id=capability_id,
        tile_manifest_file=str(manifest_path),
        source_file=str(source_path) if source_path else None,
        tile_format=tile_format,
        feature_count=0,
        warnings=warnings,
    )


###############################################################################
def _feature_count(source_path: Path | None) -> int:
    if source_path is None:
        return 0
    payload: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
    features = payload.get("features")
    return len(features) if isinstance(features, list) else 0
