from __future__ import annotations

import shutil
from pathlib import Path

from server.domain.geographics import CapabilityKind, CapabilityManifestV2
from server.services.geospatial.layer_auditor import audit_all_manifests
from server.services.geospatial.manifest_loader import GeospatialManifestLoader


def test_all_geospatial_manifests_pass_schema_v2_audit() -> None:
    report = audit_all_manifests(strict=True)

    assert report.ok, report.model_dump()
    assert report.manifest_count > 0


def test_manifest_loader_rejects_missing_schema_v2_fields() -> None:
    manifests = Path("app/tests/artifacts/tmp_manifest_schema_v2")
    if manifests.exists():
        shutil.rmtree(manifests)
    basemaps = manifests / "basemaps"
    overlays = manifests / "overlays"
    providers = manifests / "providers"
    tools = manifests / "tools"
    cameras = manifests / "cameras"
    transit = manifests / "transit"
    for folder in (basemaps, overlays, providers, tools, cameras, transit):
        folder.mkdir(parents=True)
    (manifests / "index.json").write_text(
        """
{
  "version": 4,
  "manifest_schema_version": 2,
  "source_catalog_version": "test",
  "providers_dir": "providers",
  "basemaps_dir": "basemaps",
  "overlays_dir": "overlays",
  "cameras_dir": "cameras",
  "transit_dir": "transit",
  "tools_dir": "tools",
  "runtime_profiles_file": "runtime_profiles.json",
  "capability_groups": [],
  "health_summary": {}
}
""".strip(),
        encoding="utf-8",
    )
    (manifests / "runtime_profiles.json").write_text(
        '{"version": 1, "profiles": []}', encoding="utf-8"
    )
    (basemaps / "legacy.json").write_text(
        """
{
  "id": "legacy",
  "name": "Legacy",
  "provider": "fallback",
  "type": "tile",
  "description": "Legacy manifest without schema v2 fields.",
  "capabilities": ["tile"],
  "coverage": "global",
  "metadata": {},
  "version": 1,
  "last_modified": "2026-05-11T00:00:00+00:00"
}
""".strip(),
        encoding="utf-8",
    )

    loader = GeospatialManifestLoader(root_path=str(manifests))

    try:
        try:
            loader.load_all()
        except Exception as exc:
            assert "missing fields" in str(exc)
        else:
            raise AssertionError("Legacy manifest unexpectedly loaded.")
    finally:
        shutil.rmtree(manifests, ignore_errors=True)


def test_loaded_manifests_expose_v2_capability_kinds() -> None:
    loader = GeospatialManifestLoader()
    loaded = loader.load_all()
    basemaps = loaded["basemaps"]
    overlays = loaded["overlays"]
    transit = loaded["transit"]

    assert all(
        CapabilityManifestV2.model_validate(item).capability_kind
        == CapabilityKind.BASEMAP
        for item in basemaps
    )
    assert any(item["capabilityKind"] == "metadata-only" for item in overlays)
    assert any(item["renderingMode"] == "clustered-points" for item in overlays)
    assert {item["id"] for item in transit}.issuperset(
        {"gtfs_static", "gtfs_realtime", "transitland_feeds"}
    )
