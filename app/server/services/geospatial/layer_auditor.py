from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from server.common.constants import PROJECT_DIR
from server.domain.geographics import CapabilityManifestV2, ProviderAuthType

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


class LayerAuditIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    manifest_id: str | None = None
    severity: str
    message: str


class LayerAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: list[LayerAuditIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error_count == 0


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
    if manifest.rendering_mode.value != "metadata-only" and not manifest.normalization.expected_geometry:
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
    strict: bool = False, root_path: str | os.PathLike[str] | None = None
) -> LayerAuditReport:
    root = Path(root_path or Path(PROJECT_DIR) / "resources" / "manifests")
    report = LayerAuditReport()
    _validate_index(root, report)
    for path in _manifest_paths(root):
        _validate_manifest(path, report)
    if strict and report.warning_count:
        report.error_count += report.warning_count
    return report


def _format_report(report: LayerAuditReport) -> str:
    payload = report.model_dump()
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit geospatial manifest schema v2.")
    parser.add_argument("--strict", action="store_true", help="Fail on any audit issue.")
    parser.add_argument("--root", default=None, help="Override manifest root path.")
    args = parser.parse_args(argv)
    report = audit_all_manifests(strict=args.strict, root_path=args.root)
    print(_format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
