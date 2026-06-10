from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingestion import build_ingestion_plan, execute_ingestion_plan


###############################################################################
def _iter_manifest_paths(manifest_root: Path) -> list[Path]:
    return sorted(path for path in manifest_root.rglob("*.json") if path.is_file())


###############################################################################
def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


###############################################################################
def materialize_datasets(
    *,
    workspace_root: Path,
    manifest_root: Path,
    include_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for manifest_path in _iter_manifest_paths(manifest_root):
        manifest = _load_manifest(manifest_path)
        if manifest.get("capabilityKind") != "dataset-ingestion":
            continue
        capability_id = str(manifest.get("id") or "").strip()
        if include_ids and capability_id not in include_ids:
            continue
        plan = build_ingestion_plan(manifest)
        result = execute_ingestion_plan(plan, workspace_root=workspace_root)
        results.append(
            {
                "capabilityId": capability_id,
                "manifestPath": str(manifest_path),
                "featureCount": result.feature_count,
                "normalizedFile": result.normalized_file,
                "warnings": result.warnings,
            }
        )
    return results


###############################################################################
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize geospatial dataset-ingestion manifests."
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used for storage paths in manifests.",
    )
    parser.add_argument(
        "--manifest-root",
        default="app/resources/catalog",
        help="Root directory containing capability manifests.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Capability id to materialize. Repeat for multiple ids.",
    )
    return parser.parse_args()


###############################################################################
def main() -> int:
    args = _parse_args()
    include_ids = {item.strip() for item in args.include if item.strip()} or None
    workspace_root = Path(args.workspace_root).resolve()
    manifest_root = Path(args.manifest_root).resolve()
    results = materialize_datasets(
        workspace_root=workspace_root,
        manifest_root=manifest_root,
        include_ids=include_ids,
    )
    print(json.dumps({"datasets": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
