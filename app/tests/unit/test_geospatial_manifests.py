from __future__ import annotations
import json
import pytest
import shutil
from pathlib import Path
from server.services.catalog.loader import get_catalog_root, load_reference_catalog
from server.services.geospatial.ecosystem_audit import build_inventory
from server.services.geospatial.layer_auditor import audit_all_manifests, profile_claims_unrenderable_map_support
from dataclasses import replace
from datetime import UTC, datetime
from google.transit import gtfs_realtime_pb2
from tests.conftest import run_async_in_thread
from server.services.geospatial.live_validator import CREDENTIAL_LIVE_CHECKS, PROVIDER_SMOKE_CHECKS, _run_check, validate_live_geospatial_sources
from server.services.geospatial.provider_registry import PROVIDER_FACTORIES, ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.manifest_loader import GeospatialManifestLoader, ManifestValidationError
from server.contracts.geospatial import CapabilityKind, CapabilityManifestV2, LayerHealthStatus
from server.configurations import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import ReferenceCountryAliasRecord, ReferenceCountryRecord, ReferenceGeospatialLayerAliasRecord, ReferenceGeospatialLayerKeywordRecord, ReferenceGeospatialLayerRecord, ReferenceGibsLayerDefaultRecord, ReferenceGibsTileMatrixSetRecord, Base
from server.repositories.catalog.reference_seeder import ReferenceCatalogSeeder
from server.services.geospatial.attribution import AttributionService
from server.services.geospatial.source_health import SourceHealthMonitor
from server.repositories.database.initializer import initialize_database
from server.repositories.catalog.reference_repository import ReferenceCatalogRepository
from server.services.catalog.startup import seed_reference_catalog

# --- test_catalog_reference_loader.py ---




###############################################################################
def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

###############################################################################
def _build_reference_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalog" / "reference"
    root.mkdir(parents=True)
    _write_json(
        root / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "MO", "name": "Macau SAR China"}],
            "aliases": [
                {"alias": "Macau SAR China", "iso2": "MO"},
                {"alias": "Macau", "iso2": "MO"},
            ],
        },
    )
    _write_json(
        root / "geospatial_layers.json",
        {
            "version": 1,
            "layers": [
                {
                    "layerId": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                    "displayName": "True Color Satellite (VIIRS, Daily)",
                    "group": "gibs_nrt",
                    "provider": "gibs",
                    "aliases": ["true color"],
                    "keywords": ["true color"],
                }
            ],
        },
    )
    _write_json(
        root / "gibs_tile_matrix_sets.json",
        {
            "version": 1,
            "tileMatrixSets": [{"tileMatrixSetId": "250m", "metersPerPixel": 250.0}],
        },
    )
    _write_json(
        root / "gibs_layer_defaults.json",
        {
            "version": 1,
            "layerDefaults": [
                {
                    "layerId": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                    "nativeResolutionM": 375.0,
                    "dateFallbackDays": 7,
                }
            ],
        },
    )
    return tmp_path / "catalog"

###############################################################################
def test_loads_all_reference_files_from_catalog_root() -> None:
    catalog = load_reference_catalog(get_catalog_root())

    assert catalog.countries
    assert catalog.country_aliases
    assert catalog.geospatial_layers
    assert catalog.gibs_tile_matrix_sets
    assert catalog.gibs_layer_defaults

###############################################################################
def test_country_aliases_must_resolve_to_existing_iso2(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "US", "name": "United States"}],
            "aliases": [{"alias": "USA", "iso2": "ZZ"}],
        },
    )

    with pytest.raises(ValueError, match="unknown ISO2"):
        load_reference_catalog(root)

###############################################################################
def test_duplicate_country_alias_keys_fail(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "US", "name": "United States"}],
            "aliases": [
                {"alias": "USA", "iso2": "US"},
                {"alias": " usa ", "iso2": "US"},
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate country alias key"):
        load_reference_catalog(root)

###############################################################################
def test_duplicate_layer_ids_fail(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "geospatial_layers.json",
        {
            "version": 1,
            "layers": [
                {
                    "layerId": "layer-1",
                    "displayName": "Layer 1",
                    "group": "common",
                    "provider": "gibs",
                    "aliases": [],
                    "keywords": [],
                },
                {
                    "layerId": "layer-1",
                    "displayName": "Layer 1 duplicate",
                    "group": "common",
                    "provider": "gibs",
                    "aliases": [],
                    "keywords": [],
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate geospatial layer ID"):
        load_reference_catalog(root)

###############################################################################
def test_gibs_layer_defaults_require_a_populated_value(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "gibs_layer_defaults.json",
        {
            "version": 1,
            "layerDefaults": [
                {
                    "layerId": "layer-1",
                    "nativeResolutionM": None,
                    "dateFallbackDays": None,
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="must define at least one value"):
        load_reference_catalog(root)

###############################################################################
def test_macau_alias_resolves_to_mo() -> None:
    catalog = load_reference_catalog(get_catalog_root())
    aliases = {entry.alias: entry.iso2 for entry in catalog.country_aliases}

    assert aliases["Macau"] == "MO"

# --- test_geospatial_ecosystem_audit.py ---


###############################################################################
def test_ecosystem_inventory_covers_catalog_runtime_and_native_tools() -> None:
    report = build_inventory(
        {
            "results": [
                {"provider_id": "openmeteo", "status": "passed"},
            ]
        }
    )

    assert report["counts"] == {
        "manifests": 88,
        "providers": 40,
        "direct_tools": 5,
        "llm_native_tools": 11,
        "runtime_profiles": 70,
    }
    providers = {item["id"]: item for item in report["providers"]}
    assert providers["openmeteo"]["operational_status"] == "active"
    assert providers["openfreemap"]["operational_status"] == "active_rendering_only"
    assert providers["arcgis"]["internal_components"]["adapter"].endswith(
        "arcgis_rest.py"
    )

    tool_ids = {item["id"] for item in report["tools"]}
    assert "apply_map_plan" in tool_ids
    assert "execute_geospatial_capability" in tool_ids
    assert report["replacements"][0]["new"] == ["mobility_database_feeds"]

# --- test_geospatial_layer_auditor.py ---


###############################################################################
def test_profile_map_support_must_match_contract_render_support() -> None:
    profile = {"capability_id": "elevation", "supports_map": True}

    assert profile_claims_unrenderable_map_support(
        profile, {"render_support": "metadata_only"}
    )
    assert not profile_claims_unrenderable_map_support(
        profile, {"render_support": "vector"}
    )
    assert not profile_claims_unrenderable_map_support(
        {"supports_map": False}, {"render_support": "metadata_only"}
    )
    assert not profile_claims_unrenderable_map_support(None, {})

###############################################################################
def test_layer_auditor_blocks_broken_manual_toggles() -> None:
    report = audit_all_manifests(strict=True)
    issues = [
        issue
        for issue in report.issues
        if issue.message == "Broken manifest cannot be exposed as a manual toggle."
    ]

    assert not issues

###############################################################################
def test_layer_auditor_production_gate_has_no_placeholder_or_visual_gaps() -> None:
    report = audit_all_manifests(strict=True, production=True)
    payload = report.model_dump()

    assert report.ok, payload
    assert all(
        not status.placeholder_statuses for status in report.implementation_statuses
    )
    assert all(
        status.provider_fetch_implemented for status in report.implementation_statuses
    )
    assert all(
        status.visual_tested
        for status in report.implementation_statuses
        if status.capability_id != status.provider_id
    )

# --- test_geospatial_live_validator.py ---





###############################################################################
class _LiveValidationRegistry:
    credential_resolver = type(
        "CredentialResolver",
        (),
        {"is_configured": staticmethod(lambda provider_id: False)},
    )()

    # -------------------------------------------------------------------------
    def build_from_manifests(self) -> None:
        return None

    # -------------------------------------------------------------------------
    async def fetch(
        self, provider_id: str, request: ProviderRequest
    ) -> ProviderResponse:
        check = next(
            item for item in PROVIDER_SMOKE_CHECKS if item.provider_id == provider_id
        )
        if check.response_contract == "feature_collection":
            payload = {"features": [{"latitude": 41.9, "longitude": 12.5}]}
        elif check.response_contract == "result_list":
            payload = {"results": [{"latitude": 41.9, "longitude": 12.5}]}
        elif check.response_contract == "raster_metadata":
            payload = {
                "tileUrl": "https://example.test/{z}/{x}/{y}.png",
                "latestTime": "2026-09-08T00:00:00Z",
                "frameCount": 5,
            }
        elif check.response_contract == "dataset":
            payload = {
                "type": "dataset",
                "status": "source-ready",
                "downloadUrl": "https://example.test/data",
                "feeds": [],
                "entities": [],
                "summary": {},
                "catalogRecordCount": 0,
            }
        elif check.response_contract == "metadata":
            payload = {"layer": {}, "render": {}}
        else:
            payload = {"latitude": 41.9, "longitude": 12.5, "current": {}}
            if provider_id == "openmeteo":
                payload["features"] = [
                    {"latitude": 41.9, "longitude": 12.5}
                ]
        for key in check.numeric_payload_keys:
            payload[key] = 1 if key == "frameCount" else 1.0
        for key in check.required_payload_keys:
            if key not in payload:
                payload[key] = (
                    "https://example.test/source"
                    if key.lower().endswith(("url", "path"))
                    else {}
                )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider_id,
            payload=payload,
        )

###############################################################################
def test_live_validator_covers_the_factory_matrix_with_injected_registry() -> None:
    report = run_async_in_thread(
        validate_live_geospatial_sources(registry_factory=_LiveValidationRegistry)
    )

    assert report.ok, report.model_dump()
    assert len(report.results) == len(PROVIDER_SMOKE_CHECKS)
    assert {result.provider_id for result in report.results} == set(PROVIDER_FACTORIES)
    assert all(result.status in {"passed", "skipped"} for result in report.results)

###############################################################################
def test_live_validator_matrix_has_one_case_per_factory_entry() -> None:
    provider_ids = [check.provider_id for check in PROVIDER_SMOKE_CHECKS]

    assert len(provider_ids) == len(set(provider_ids))
    assert set(provider_ids) == set(PROVIDER_FACTORIES)

###############################################################################
def test_live_validator_skips_missing_saved_credentials() -> None:

    result = run_async_in_thread(
        _run_check(_LiveValidationRegistry(), CREDENTIAL_LIVE_CHECKS[0])
    )

    assert result.status == "skipped"
    assert "saved credential" in (result.message or "")

###############################################################################
def test_live_validator_rejects_error_payloads() -> None:

    ###############################################################################
    class _ErrorRegistry(_LiveValidationRegistry):

        # -------------------------------------------------------------------------
        async def fetch(
            self, provider_id: str, request: ProviderRequest
        ) -> ProviderResponse:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=provider_id,
                payload={"error": "upstream unavailable"},
            )

    result = run_async_in_thread(
        _run_check(
            _ErrorRegistry(),
            CREDENTIAL_LIVE_CHECKS[0].__class__(
                provider_id="pvgis",
                request=ProviderRequest(capability_id="pvgis_solar_potential"),
            ),
        )
    )

    assert result.status == "failed"
    assert "upstream unavailable" in (result.message or "")

###############################################################################
def test_live_validator_rejects_malformed_feature_geometry() -> None:

    ###############################################################################
    class _MalformedRegistry(_LiveValidationRegistry):

        # -------------------------------------------------------------------------
        async def fetch(
            self, provider_id: str, request: ProviderRequest
        ) -> ProviderResponse:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=provider_id,
                payload={"features": [{"id": "missing-geometry"}]},
            )

    result = run_async_in_thread(
        _run_check(
            _MalformedRegistry(),
            PROVIDER_SMOKE_CHECKS[1].__class__(
                provider_id="census",
                request=ProviderRequest(capability_id="census_cartographic_boundaries"),
                response_contract="feature_collection",
                required_payload_keys=("features",),
            ),
        )
    )

    assert result.status == "failed"
    assert "geometry" in (result.message or "")

###############################################################################
def test_live_validator_runs_configured_openchargemap_snapshot(monkeypatch, tmp_path) -> None:
    snapshot = tmp_path / "ocm.json"
    snapshot.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("AEGIS_OCM_SNAPSHOT_PATH", str(snapshot))
    check = next(
        item for item in PROVIDER_SMOKE_CHECKS if item.provider_id == "openchargemap"
    )

    result = run_async_in_thread(_run_check(_LiveValidationRegistry(), check))

    assert result.status == "passed"

###############################################################################
def test_live_validator_accepts_production_gtfs_realtime_normalization(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_GTFS_REALTIME_FEED_URL", "https://example.test/vehicles.pb")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(datetime.now(UTC).timestamp())
    entity = feed.entity.add()
    entity.id = "vehicle-1"
    entity.vehicle.position.latitude = 42.36
    entity.vehicle.position.longitude = -71.06
    check = next(item for item in PROVIDER_SMOKE_CHECKS if item.provider_id == "gtfs_realtime")
    check = replace(check, request=ProviderRequest(
        capability_id="gtfs_realtime", params={"feed_bytes": feed.SerializeToString()},
    ))
    result = run_async_in_thread(_run_check(
        ProviderRegistry(providers=[GTFSRealtimeProvider()]), check,
    ))

    assert result.status == "passed", result.message
    assert result.feature_count == 1

# --- test_manifest_loader.py ---



###############################################################################
def test_manifest_loader_reads_core_collections() -> None:
    loader = GeospatialManifestLoader()
    payload = loader.load_all()
    assert "providers" in payload
    assert "basemaps" in payload
    assert "overlays" in payload
    assert any(item["id"] == "osm_default" for item in payload["basemaps"])
    assert any(item["id"] == "openaq_air_quality" for item in payload["overlays"])
    basemap = next(item for item in payload["basemaps"] if item["id"] == "osm_default")
    assert basemap.get("source_filename")
    assert basemap.get("source_path")

###############################################################################
def test_priority_provider_manifests_include_temporal_metadata() -> None:
    payload = GeospatialManifestLoader().load_all()
    providers = {item["id"]: item for item in payload["providers"]}
    for provider_id in ("inspire", "data_europa", "arcgis", "geoss", "google_maps"):
        metadata = providers[provider_id]["metadata"]
        assert metadata["dataset_time_reference"]
        assert metadata["source_freshness"]
        assert metadata["query_mode"]

###############################################################################
def test_manifest_loader_accepts_path_root_argument() -> None:
    root_path = Path("data/catalog")

    payload = GeospatialManifestLoader(root_path=root_path).load_all()

    assert any(item["id"] == "osm_default" for item in payload["basemaps"])

# --- test_manifest_schema_v2.py ---




###############################################################################
def test_all_geospatial_manifests_pass_schema_v2_audit() -> None:
    report = audit_all_manifests(strict=True)

    assert report.ok, report.model_dump()
    assert report.manifest_count > 0
    assert report.source_doc_coverage.get("with_source_docs") == report.manifest_count
    assert not [
        issue
        for issue in report.issues
        if issue.message == "Metadata-only manifest cannot claim map geometry."
    ]

###############################################################################
def test_manifest_loader_rejects_missing_schema_v2_fields() -> None:
    manifests = (
        Path(__file__).resolve().parents[2] / "artifacts" / "tmp_manifest_schema_v2"
    )
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
    (basemaps / "missing_schema_v2.json").write_text(
        """
{
  "id": "missing_schema_v2",
  "name": "Missing Schema V2",
  "provider": "osm_tiles",
  "type": "tile",
  "description": "Manifest without schema v2 fields.",
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
            raise AssertionError("Invalid schema v2 manifest unexpectedly loaded.")
    finally:
        shutil.rmtree(manifests, ignore_errors=True)

###############################################################################
def test_manifest_loader_rejects_empty_agentic_domains() -> None:
    loader = GeospatialManifestLoader()
    entry = dict(loader.load_all()["overlays"][0])
    entry.pop("source_filename", None)
    entry.pop("source_path", None)
    entry["agenticUse"] = {
        **dict(entry["agenticUse"]),
        "domains": [],
    }

    with pytest.raises(ManifestValidationError, match="agenticUse domain"):
        loader._validate_entry(
            entry,
            source="missing_domains.json",
            require_agentic_domains=True,
        )

###############################################################################
def test_loaded_manifests_expose_v2_capability_kinds() -> None:
    loader = GeospatialManifestLoader()
    loaded = loader.load_all()
    basemaps = loaded["basemaps"]
    overlays = loaded["overlays"]
    transit = loaded["transit"]

    def without_loader_metadata(item: dict[str, object]) -> dict[str, object]:
        return {
            key: value
            for key, value in item.items()
            if key not in {"source_filename", "source_path"}
        }

    assert all(
        CapabilityManifestV2.model_validate(without_loader_metadata(item)).capability_kind
        == CapabilityKind.BASEMAP
        for item in basemaps
    )
    assert any(item["capabilityKind"] == "metadata-only" for item in overlays)
    assert any(item["renderingMode"] == "clustered-points" for item in overlays)
    assert {item["id"] for item in transit}.issuperset(
        {"gtfs_static", "gtfs_realtime", "mobility_database_feeds"}
    )

# --- test_reference_catalog_seeder.py ---



###############################################################################
def _build_database(tmp_path: Path) -> SQLiteRepository:
    repository = SQLiteRepository(
        DatabaseSettings(
            database_path=str(tmp_path / "database.db"),
        )
    )
    Base.metadata.create_all(repository.engine)
    return repository

###############################################################################
def test_fresh_sqlite_database_creates_reference_tables(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)

    assert repository.count_records(ReferenceCountryRecord) == 0
    assert repository.count_records(ReferenceGeospatialLayerRecord) == 0
    assert repository.count_records(ReferenceGibsTileMatrixSetRecord) == 0
    assert repository.count_records(ReferenceGibsLayerDefaultRecord) == 0

###############################################################################
def test_first_seed_inserts_all_reference_rows(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)

    result = ReferenceCatalogSeeder(repository).seed_if_needed(load_reference_catalog())

    assert result.countries_seeded is True
    assert result.geospatial_layers_seeded is True
    assert result.gibs_tile_matrix_sets_seeded is True
    assert result.gibs_layer_defaults_seeded is True
    assert repository.count_records(ReferenceCountryRecord) > 0
    assert repository.count_records(ReferenceCountryAliasRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerAliasRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerKeywordRecord) > 0
    assert repository.count_records(ReferenceGibsTileMatrixSetRecord) > 0
    assert repository.count_records(ReferenceGibsLayerDefaultRecord) > 0

###############################################################################
def test_second_seed_does_not_insert_duplicates(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    seeder = ReferenceCatalogSeeder(repository)

    seeder.seed_if_needed(load_reference_catalog())
    first_counts = {
        "countries": repository.count_records(ReferenceCountryRecord),
        "aliases": repository.count_records(ReferenceCountryAliasRecord),
        "layers": repository.count_records(ReferenceGeospatialLayerRecord),
        "layer_aliases": repository.count_records(ReferenceGeospatialLayerAliasRecord),
        "layer_keywords": repository.count_records(
            ReferenceGeospatialLayerKeywordRecord
        ),
        "tile_matrix_sets": repository.count_records(ReferenceGibsTileMatrixSetRecord),
        "layer_defaults": repository.count_records(ReferenceGibsLayerDefaultRecord),
    }

    result = seeder.seed_if_needed(load_reference_catalog())

    assert result.countries_seeded is False
    assert result.geospatial_layers_seeded is False
    assert result.gibs_tile_matrix_sets_seeded is False
    assert result.gibs_layer_defaults_seeded is False
    assert first_counts == {
        "countries": repository.count_records(ReferenceCountryRecord),
        "aliases": repository.count_records(ReferenceCountryAliasRecord),
        "layers": repository.count_records(ReferenceGeospatialLayerRecord),
        "layer_aliases": repository.count_records(ReferenceGeospatialLayerAliasRecord),
        "layer_keywords": repository.count_records(
            ReferenceGeospatialLayerKeywordRecord
        ),
        "tile_matrix_sets": repository.count_records(ReferenceGibsTileMatrixSetRecord),
        "layer_defaults": repository.count_records(ReferenceGibsLayerDefaultRecord),
    }

###############################################################################
def test_country_seeding_is_skipped_when_reference_countries_populated(
    tmp_path: Path,
) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(ReferenceCountryRecord(iso2="ZZ", name="Seeded Country"))
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed(load_reference_catalog())

    assert result.countries_seeded is False

###############################################################################
def test_layer_seeding_is_skipped_when_reference_layers_populated(
    tmp_path: Path,
) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGeospatialLayerRecord(
                layer_id="seeded-layer",
                display_name="Seeded Layer",
                group="common",
                provider="gibs",
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed(load_reference_catalog())

    assert result.geospatial_layers_seeded is False

###############################################################################
def test_tile_matrix_seeding_is_skipped_when_table_populated(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGibsTileMatrixSetRecord(
                tile_matrix_set_id="seeded",
                meters_per_pixel=1.0,
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed(load_reference_catalog())

    assert result.gibs_tile_matrix_sets_seeded is False

###############################################################################
def test_layer_default_seeding_is_skipped_when_table_populated(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGibsLayerDefaultRecord(
                layer_id="seeded",
                native_resolution_m=1.0,
                date_fallback_days=None,
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed(load_reference_catalog())

    assert result.gibs_layer_defaults_seeded is False

# --- test_source_health_and_attribution.py ---


###############################################################################
def test_source_health_prefers_recorded_provider_status() -> None:
    monitor = SourceHealthMonitor()
    manifest = {
        "provider": "rainviewer",
        "reliability": {"status": "partial"},
    }

    monitor.record("rainviewer", LayerHealthStatus.FUNCTIONAL)

    assert monitor.status_for_manifest(manifest) == LayerHealthStatus.FUNCTIONAL

###############################################################################
def test_source_health_uses_manifest_status_without_probe_record() -> None:
    monitor = SourceHealthMonitor()

    status = monitor.status_for_manifest(
        {"provider": "rainviewer", "reliability": {"status": "partial"}}
    )

    assert status == LayerHealthStatus.PARTIAL

###############################################################################
def test_attribution_service_deduplicates_manifest_labels() -> None:
    manifests = GeospatialManifestLoader().load_all()
    service = AttributionService()
    selected = [
        item
        for item in manifests["basemaps"] + manifests["overlays"]
        if item["provider"] == "gibs"
    ][:2]

    labels = service.merge_labels(selected)

    assert labels
    assert len(labels) == len(set(labels))

# --- test_gibs_reference_defaults.py ---



###############################################################################
def _seeded_repository(tmp_path: Path) -> SQLiteRepository:
    repository = SQLiteRepository(
        DatabaseSettings(
            database_path=str(tmp_path / "database.db"),
        )
    )
    initialize_database(
        repository,
        on_ready=lambda: seed_reference_catalog(repository),
    )
    return repository

###############################################################################
def test_gibs_reference_maps_load_from_reference_tables(tmp_path: Path) -> None:
    repository = _seeded_repository(tmp_path)
    reference_repository = ReferenceCatalogRepository(repository)

    native_resolution_map = reference_repository.load_gibs_layer_native_resolution_map()
    date_fallback_map = reference_repository.load_gibs_layer_date_fallback_days_map()
    tile_matrix_map = reference_repository.load_gibs_tile_matrix_resolution_map()

    assert native_resolution_map["VIIRS_SNPP_CorrectedReflectance_TrueColor"] == 375.0
    assert date_fallback_map["MODIS_Combined_Thermal_Anomalies_All"] == 3
    assert tile_matrix_map["250m"] == 250.0