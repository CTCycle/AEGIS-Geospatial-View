from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from server.common.paths import PROJECT_DIR
from server.domain.geographics import (
    CapabilityImplementationStatus,
    CapabilityKind,
    CapabilityManifestV2,
    LayerAuditIssue,
    LayerAuditReport,
    ProviderAuthType,
    RenderingMode,
)

type JsonDict = dict[str, Any]

MANIFEST_DIRECTORIES = ("providers", "basemaps", "overlays", "tools", "cameras", "transit")
SECRET_FIELD_MARKERS = ("key", "secret", "token", "password")
SECRET_FIELD_ALLOWLIST = {"providerkey", "accesspageproviderid"}
REQUIRED_INDEX_FIELDS = {
    "version",
    "manifest_schema_version",
    "source_catalog_version",
    "providers_dir",
    "basemaps_dir",
    "overlays_dir",
    "cameras_dir",
    "transit_dir",
    "tools_dir",
    "runtime_profiles_file",
    "capability_groups",
    "health_summary",
}
PLACEHOLDER_STATUSES = {
    "download-required",
    "feed-required",
    "fetch-required",
    "not-enabled",
    "not-implemented",
    "not-queried",
    "requires-ingestion",
    "requires-local-source",
}
PROVIDER_SOURCE_DIR = (
    PROJECT_DIR / "server" / "services" / "geospatial" / "providers"
)
API_SOURCE_PATH = PROJECT_DIR / "server" / "api" / "geospatial.py"
CLIENT_SOURCE_DIR = PROJECT_DIR / "client" / "src" / "app"
TEST_SOURCE_DIR = PROJECT_DIR / "tests" / "unit"
VISUAL_TEST_SOURCE_DIR = PROJECT_DIR / "client" / "e2e"
CLIENT_RENDERING_MODES = {
    "camera-points",
    "choropleth",
    "clustered-points",
    "geojson",
    "metadata-only",
    "raster-tile",
    "vector-tile",
    "wms",
    "wmts",
    "xyz",
}
PROVIDER_SOURCE_ALIASES = {
    "gibs": "nasa_gibs",
}
BASEMAP_TEST_MARKERS = ("basemap", "tile")


def _read_json(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON document must be an object.")
    return payload


def _add_issue(
    report: LayerAuditReport,
    *,
    path: Path,
    severity: str,
    message: str,
    manifest_id: str | None = None,
) -> None:
    report.issues.append(
        LayerAuditIssue(
            path=str(path),
            manifest_id=manifest_id,
            severity=severity,
            message=message,
        )
    )
    if severity == "error":
        report.error_count += 1
    else:
        report.warning_count += 1


def _manifest_paths(root_path: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in MANIFEST_DIRECTORIES:
        folder = root_path / directory
        if not folder.is_dir():
            continue
        paths.extend(sorted(folder.glob("*.json")))
    return paths


def _read_text_if_exists(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _combined_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        chunks.append(_read_text_if_exists(path))
    return "\n".join(chunks)


def _python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    ignored_parts = {"__pycache__", ".pytest_cache", ".angular", "dist", "node_modules"}
    return [
        path
        for path in root.rglob("*.py")
        if not any(part in ignored_parts for part in path.parts)
    ]


def _client_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    ignored_parts = {"node_modules", ".angular", "dist"}
    return [
        path
        for path in root.rglob("*")
        if path.suffix in {".ts", ".html", ".scss"}
        and not any(part in ignored_parts for part in path.parts)
    ]


def _provider_source(provider_id: str) -> str:
    provider_filename = PROVIDER_SOURCE_ALIASES.get(
        provider_id,
        provider_id.replace("-", "_"),
    )
    return _read_text_if_exists(PROVIDER_SOURCE_DIR / f"{provider_filename}.py")


def _placeholder_statuses(source: str) -> list[str]:
    return sorted(status for status in PLACEHOLDER_STATUSES if status in source)


def _basemap_fetch_implemented(manifest: CapabilityManifestV2) -> bool:
    metadata = manifest.metadata if isinstance(manifest.metadata, dict) else {}
    return manifest.capability_kind == CapabilityKind.BASEMAP and bool(
        str(metadata.get("tile_url") or "").strip()
    )


def _basemap_unit_tested(test_source: str) -> bool:
    return all(marker in test_source for marker in BASEMAP_TEST_MARKERS)


def _status_for_manifest(
    manifest: CapabilityManifestV2,
    *,
    runtime_ids: set[str],
    api_source: str,
    client_source: str,
    test_source: str,
    visual_test_source: str,
) -> CapabilityImplementationStatus:
    provider_source = _provider_source(manifest.provider)
    placeholders = _placeholder_statuses(provider_source)
    provider_fetch_implemented = (
        bool(provider_source) and "not-implemented" not in placeholders
    ) or _basemap_fetch_implemented(manifest)
    if manifest.capability_kind.value == "metadata-only":
        provider_fetch_implemented = True
    unit_tested = manifest.id in test_source or manifest.provider in test_source
    if manifest.capability_kind == CapabilityKind.BASEMAP:
        unit_tested = unit_tested or _basemap_unit_tested(test_source)
    return CapabilityImplementationStatus(
        capability_id=manifest.id,
        provider_id=manifest.provider,
        runtime_registered=manifest.id in runtime_ids,
        provider_fetch_implemented=provider_fetch_implemented,
        normalizer_implemented=bool(
            manifest.normalization.expected_geometry
            and manifest.normalization.expected_geometry != "not-applicable"
        )
        or manifest.rendering_mode.value == "metadata-only",
        cache_implemented=manifest.cache_policy.mode.value != "none",
        api_endpoint_covered=manifest.id in api_source or manifest.provider in api_source,
        client_renderer_covered=manifest.rendering_mode.value in CLIENT_RENDERING_MODES
        and manifest.rendering_mode.value in client_source,
        unit_tested=unit_tested,
        visual_tested=manifest.id in visual_test_source
        or manifest.provider in visual_test_source
        or manifest.rendering_mode.value in visual_test_source,
        placeholder_statuses=placeholders,
    )


def _contains_secret_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            if (
                key_text not in SECRET_FIELD_ALLOWLIST
                and any(marker in key_text for marker in SECRET_FIELD_MARKERS)
            ):
                if isinstance(nested, str) and nested.strip():
                    return True
            if _contains_secret_value(nested):
                return True
    if isinstance(value, list):
        return any(_contains_secret_value(item) for item in value)
    return False


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _record_coverage(manifest: CapabilityManifestV2, report: LayerAuditReport) -> None:
    _increment(report.schema_coverage, f"schema_v{manifest.version}")
    _increment(report.provider_coverage, manifest.provider)
    _increment(report.renderer_coverage, manifest.rendering_mode.value)
    _increment(report.auth_coverage, manifest.auth.type.value)
    _increment(
        report.source_doc_coverage,
        "with_source_docs" if manifest.source_official_docs else "missing_source_docs",
    )


def _validate_index(root_path: Path, report: LayerAuditReport) -> None:
    path = root_path / "index.json"
    try:
        payload = _read_json(path)
    except Exception as exc:
        _add_issue(report, path=path, severity="error", message=str(exc))
        return
    missing = sorted(field for field in REQUIRED_INDEX_FIELDS if field not in payload)
    if missing:
        _add_issue(
            report,
            path=path,
            severity="error",
            message=f"Manifest index is missing schema v2 fields: {', '.join(missing)}",
        )


def _validate_auth_policy(
    path: Path, manifest: CapabilityManifestV2, report: LayerAuditReport
) -> None:
    auth = manifest.auth
    if auth.type == ProviderAuthType.API_KEY and not auth.provider_key:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="API-key manifest must declare auth.providerKey.",
        )
    if auth.required and not auth.access_page_provider_id:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Credential-gated manifest must declare auth.accessPageProviderId.",
        )


def _validate_renderability(
    path: Path, manifest: CapabilityManifestV2, report: LayerAuditReport
) -> None:
    metadata_only_capability = manifest.capability_kind == CapabilityKind.METADATA_ONLY
    renderable_mode = manifest.rendering_mode != RenderingMode.METADATA_ONLY
    if metadata_only_capability and manifest.rendering_mode != RenderingMode.METADATA_ONLY:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Metadata-only capability must use metadata-only renderingMode.",
        )
    if (
        manifest.rendering_mode.value != "metadata-only"
        and not manifest.normalization.expected_geometry
    ):
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Renderable manifest must declare normalization.expectedGeometry.",
        )
    if manifest.reliability.status.value == "broken" and manifest.agentic_use.manual_toggle:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Broken manifest cannot be exposed as a manual toggle.",
        )
    if metadata_only_capability and manifest.agentic_use.manual_toggle:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Metadata-only manifest cannot be exposed as a manual toggle.",
        )
    if metadata_only_capability and (
        manifest.normalization.geometry_path
        or manifest.normalization.expected_geometry not in {"not-applicable", "none"}
    ):
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Metadata-only manifest cannot claim map geometry.",
        )
    if renderable_mode and manifest.normalization.expected_geometry == "not-applicable":
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Renderable manifest must use a concrete expectedGeometry.",
        )


def _validate_manifest(path: Path, report: LayerAuditReport) -> None:
    try:
        payload = _read_json(path)
    except Exception as exc:
        _add_issue(report, path=path, severity="error", message=str(exc))
        return
    manifest_id = str(payload.get("id") or "") or None
    try:
        manifest = CapabilityManifestV2.model_validate(payload)
    except ValidationError as exc:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest_id,
            message=f"Schema v2 validation failed: {exc}",
        )
        return
    report.manifest_count += 1
    _record_coverage(manifest, report)
    if not manifest.source_official_docs:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Manifest must declare sourceOfficialDocs.",
        )
    if not manifest.license.name or not manifest.license.url:
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Manifest must declare license name and URL.",
        )
    if _contains_secret_value(payload):
        _add_issue(
            report,
            path=path,
            severity="error",
            manifest_id=manifest.id,
            message="Manifest appears to contain a secret-like value.",
        )
    _validate_auth_policy(path, manifest, report)
    _validate_renderability(path, manifest, report)


def audit_all_manifests(
    strict: bool = False,
    root_path: str | os.PathLike[str] | None = None,
    production: bool = False,
) -> LayerAuditReport:
    root = Path(root_path) if root_path is not None else PROJECT_DIR / "resources" / "catalog"
    report = LayerAuditReport()
    _validate_index(root, report)
    manifest_items: list[tuple[Path, CapabilityManifestV2]] = []
    for path in _manifest_paths(root):
        before = report.manifest_count
        _validate_manifest(path, report)
        if report.manifest_count == before:
            continue
        manifest_items.append(
            (path, CapabilityManifestV2.model_validate(_read_json(path)))
        )
    runtime_profiles = _read_json(root / "runtime_profiles.json").get("profiles") or []
    runtime_ids = {
        str(item.get("capability_id"))
        for item in runtime_profiles
        if isinstance(item, dict) and item.get("capability_id")
    }
    api_source = _read_text_if_exists(API_SOURCE_PATH)
    client_source = _combined_text(_client_files(CLIENT_SOURCE_DIR))
    test_source = _combined_text(_python_files(TEST_SOURCE_DIR))
    visual_test_source = _combined_text(_client_files(VISUAL_TEST_SOURCE_DIR))
    for path, manifest in manifest_items:
        status = _status_for_manifest(
            manifest,
            runtime_ids=runtime_ids,
            api_source=api_source,
            client_source=client_source,
            test_source=test_source,
            visual_test_source=visual_test_source,
        )
        report.implementation_statuses.append(status)
        if path.parent.name != "providers" and not status.runtime_registered:
            _add_issue(
                report,
                path=path,
                severity="error",
                manifest_id=manifest.id,
                message="Capability is not registered in runtime_profiles.json.",
            )
        if manifest.reliability.status.value == "functional" and status.placeholder_statuses:
            _add_issue(
                report,
                path=path,
                severity="error",
                manifest_id=manifest.id,
                message=(
                    "Functional capability provider exposes placeholder statuses: "
                    + ", ".join(status.placeholder_statuses)
                ),
            )
        if status.placeholder_statuses and manifest.agentic_use.manual_toggle:
            _add_issue(
                report,
                path=path,
                severity="error",
                manifest_id=manifest.id,
                message=(
                    "Placeholder-backed capability cannot be exposed as a manual toggle."
                ),
            )
        if production and path.parent.name != "providers":
            if status.placeholder_statuses:
                _add_issue(
                    report,
                    path=path,
                    severity="error",
                    manifest_id=manifest.id,
                    message=(
                        "Production audit forbids placeholder provider states: "
                        + ", ".join(status.placeholder_statuses)
                    ),
                )
            if not status.provider_fetch_implemented:
                _add_issue(
                    report,
                    path=path,
                    severity="error",
                    manifest_id=manifest.id,
                    message="Production audit requires a concrete provider fetch path.",
                )
            if not status.unit_tested:
                _add_issue(
                    report,
                    path=path,
                    severity="error",
                    manifest_id=manifest.id,
                    message="Production audit requires unit test coverage.",
                )
            if not status.client_renderer_covered:
                _add_issue(
                    report,
                    path=path,
                    severity="error",
                    manifest_id=manifest.id,
                    message="Production audit requires client renderer coverage.",
                )
            if not status.visual_tested:
                _add_issue(
                    report,
                    path=path,
                    severity="error",
                    manifest_id=manifest.id,
                    message="Production audit requires browser scenario coverage.",
                )
    if strict and report.warning_count:
        report.error_count += report.warning_count
    return report


def _format_report(report: LayerAuditReport) -> str:
    payload = report.model_dump()
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit geospatial manifest schema v2.")
    parser.add_argument("--strict", action="store_true", help="Fail on any audit issue.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Require production-ready provider, renderer, unit, and browser coverage.",
    )
    parser.add_argument("--root", default=None, help="Override manifest root path.")
    args = parser.parse_args(argv)
    report = audit_all_manifests(
        strict=args.strict,
        root_path=args.root,
        production=args.production,
    )
    print(_format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
