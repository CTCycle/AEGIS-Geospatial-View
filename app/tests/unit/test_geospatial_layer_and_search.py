from __future__ import annotations
from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache, cache_key_for_request
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from tests.conftest import run_async_in_thread
from server.services.geospatial.providers.census import CensusProvider
from server.domain.catalog import GeospatialLayerReferenceEntry
from server.services.geospatial.layers import LayerProviderService, build_geospatial_layer_catalog
import pytest
from server.services.geospatial.normalizers import NormalizationError, deduplicate_poi_features, normalize_camera_feature, normalize_poi_category, normalize_poi_feature
from server.services.geospatial.poi_benchmark import benchmark_poi_parity, load_poi_records
from server.services.geospatial.search_index import IndexedFeature, build_feature_search_index, query_search_index

# --- test_geospatial_cache.py ---


###############################################################################
class _Clock:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.value = 0.0

    # -------------------------------------------------------------------------
    def __call__(self) -> float:
        return self.value

###############################################################################
def test_geospatial_cache_returns_hit_stale_then_miss() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)

    cache.set(
        "rainviewer:metadata",
        {"frame": 1},
        ttl_seconds=10,
        stale_while_revalidate_seconds=5,
    )

    assert cache.get("rainviewer:metadata").status == CacheLookupStatus.HIT
    clock.value = 11.0
    stale = cache.get("rainviewer:metadata")
    assert stale.status == CacheLookupStatus.STALE
    assert stale.value == {"frame": 1}
    clock.value = 16.0
    assert cache.get("rainviewer:metadata").status == CacheLookupStatus.MISS

###############################################################################
def test_geospatial_cache_can_invalidate_entries() -> None:
    cache = GeospatialCache()

    cache.set("openaq:stations", [1, 2], ttl_seconds=60)
    cache.invalidate("openaq:stations")

    assert cache.get("openaq:stations").status == CacheLookupStatus.MISS

###############################################################################
def test_geospatial_cache_key_for_request_excludes_raw_credentials() -> None:
    key = cache_key_for_request(
        "openaq",
        ProviderRequest(
            capability_id="openaq_air_quality",
            bbox=(1, 2, 3, 4),
            zoom=9,
            params={"api_key": "raw-secret", "pollutant": "pm25"},
        ),
    )

    assert "raw-secret" not in key
    assert key.startswith("openaq:openaq_air_quality:")

# --- test_geospatial_catalog_service.py ---


###############################################################################
class _CredentialRepo:

    # -------------------------------------------------------------------------
    def __init__(self, present: bool) -> None:
        self.present = present

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if self.present and provider == "tomtom" and label == "api_key":
            return object()
        return None

###############################################################################
def _service_with_credentials(present: bool) -> GeospatialCatalogService:
    manifest_loader = GeospatialManifestLoader()
    return GeospatialCatalogService(
        capability_registry=CapabilityRegistry(manifest_loader=manifest_loader),
        runtime_registry=RuntimeRegistry(
            manifest_loader=manifest_loader,
            credentials_repo=_CredentialRepo(present),  # type: ignore[arg-type]
        ),
    )

###############################################################################
def test_catalog_contains_grouped_capability_sections() -> None:
    catalog = _service_with_credentials(False).list_catalog()

    assert "providers" in catalog
    assert "basemaps" in catalog
    assert "overlays" in catalog
    assert "tools" in catalog
    assert any(item["id"] == "osm_default" for item in catalog["basemaps"])
    assert any(item["id"] == "openaq_air_quality" for item in catalog["overlays"])
    assert any(item["id"] == "get_weather_forecast" for item in catalog["tools"])

###############################################################################
def test_catalog_exposes_a_renderable_public_satellite_basemap() -> None:
    catalog = _service_with_credentials(False).list_catalog()
    satellite = next(
        item for item in catalog["basemaps"] if item["id"] == "esri_world_imagery"
    )

    render = satellite["render"]
    assert render["status"] == "available"
    assert "World_Imagery/MapServer/tile" in render["tile_url"]
    assert render["attribution"]

###############################################################################
def test_satellite_basemap_declares_location_execution_arguments() -> None:
    registry = CapabilityRegistry(manifest_loader=GeospatialManifestLoader())
    satellite = registry.get_capability("esri_world_imagery")

    assert satellite is not None
    argument_schema = satellite["metadata"]["argument_schema"]
    assert argument_schema["type"] == "object"
    assert "location" in argument_schema["properties"]
    assert "latitude" in argument_schema["properties"]
    assert "longitude" in argument_schema["properties"]

###############################################################################
def test_catalog_marks_key_required_capabilities_unavailable_without_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)

    catalog = _service_with_credentials(False).list_catalog()
    lookup = {item["id"]: item for item in catalog["capabilities"]}
    providers = {item["id"]: item for item in catalog["providers"]}

    assert lookup["tomtom_traffic_flow"]["requires_credentials"] is True
    assert lookup["tomtom_traffic_flow"]["is_available"] is False
    assert providers["tomtom"]["is_available"] is False

###############################################################################
def test_catalog_exposes_openchargemap_local_or_access_reason(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_OCM_SNAPSHOT_PATH", raising=False)

    catalog = _service_with_credentials(False).list_catalog()
    lookup = {item["id"]: item for item in catalog["capabilities"]}
    openchargemap = lookup["openchargemap_ev_charging"]

    assert openchargemap["requires_credentials"] is False
    assert openchargemap["is_available"] is False
    assert "Open Charge Map" in openchargemap["availability_reason"]
    assert "local snapshot" in openchargemap["availability_reason"]

###############################################################################
def test_catalog_marks_key_required_capabilities_available_with_saved_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)

    catalog = _service_with_credentials(True).list_catalog()
    lookup = {item["id"]: item for item in catalog["capabilities"]}
    providers = {item["id"]: item for item in catalog["providers"]}

    assert lookup["tomtom_traffic_flow"]["is_available"] is True
    assert providers["tomtom"]["is_available"] is True

###############################################################################
def test_catalog_exposes_snake_case_nested_api_metadata() -> None:
    catalog = _service_with_credentials(False).list_catalog()
    overlay = next(
        item for item in catalog["overlays"] if item["id"] == "openaq_air_quality"
    )

    assert set(overlay["reliability"]) == {
        "status",
        "last_audited",
        "known_limitations",
    }
    assert set(overlay["auth"]) == {
        "type",
        "required",
        "provider_key",
        "access_page_provider_id",
    }
    assert "lastAudited" not in overlay["reliability"]
    assert "providerKey" not in overlay["auth"]

# --- test_geospatial_choropleth_normalization.py ---



###############################################################################
def test_census_demographic_payload_uses_choropleth_contract() -> None:
    response = run_async_in_thread(
        CensusProvider().fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert response.payload["renderingMode"] == "choropleth"
    assert response.payload["classificationField"]
    assert response.attribution

# --- test_geospatial_layers.py ---


###############################################################################
def test_geospatial_layer_catalog_comes_from_reference_entries() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("fire", "fires"),
                keywords=("fire", "fires"),
            ),
        )
    )

    entry = service.resolve("fires")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.label == "Active Fires (MODIS, Daily)"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"

###############################################################################
def test_geospatial_layer_service_without_catalog_has_no_entries() -> None:
    service = LayerProviderService()

    assert service.list_options() == {}

###############################################################################
def test_build_geospatial_layer_catalog_uses_reference_repository(monkeypatch) -> None:
    expected_catalog = (
        GeospatialLayerReferenceEntry(
            layer_id="fire",
            display_name="Fire",
            group="gibs_nrt",
            provider="gibs",
            aliases=("fires",),
            keywords=("fire",),
        ),
    )

    ###############################################################################
    class RepositoryStub:

        # -------------------------------------------------------------------------
        def __init__(self, database) -> None:
            self.database = database

        # -------------------------------------------------------------------------
        def load_geospatial_layer_catalog(self):  # noqa: ANN201
            return expected_catalog

    monkeypatch.setattr(
        "server.services.geospatial.layers.ReferenceCatalogRepository",
        RepositoryStub,
    )

    service = build_geospatial_layer_catalog(object())

    assert isinstance(service, LayerProviderService)
    assert service.resolve("fires").name == "fire"

# --- test_geospatial_normalizers.py ---



###############################################################################
def test_normalize_poi_feature_accepts_common_coordinate_aliases() -> None:
    poi = normalize_poi_feature(
        {
            "id": "osm-1",
            "name": "Water point",
            "lat": "45.1",
            "lon": "7.2",
            "website": "https://example.test",
            "raw_tag": "drinking_water",
        },
        source="overpass",
        category="drinking_water",
    )

    assert poi.id == "osm-1"
    assert poi.latitude == 45.1
    assert poi.longitude == 7.2
    assert poi.metadata == {"raw_tag": "drinking_water"}

###############################################################################
def test_normalize_camera_feature_requires_official_url() -> None:
    with pytest.raises(NormalizationError):
        normalize_camera_feature(
            {"id": "cam-1", "latitude": 45.1, "longitude": 7.2},
            provider="windy_webcams",
            camera_type="webcam",
        )

###############################################################################
def test_normalize_camera_feature_defaults_to_no_embedding() -> None:
    camera = normalize_camera_feature(
        {
            "id": "cam-1",
            "name": "Pass camera",
            "latitude": 45.1,
            "longitude": 7.2,
            "official_url": "https://example.test/cam",
            "preview_image_url": "https://example.test/preview.jpg",
        },
        provider="windy_webcams",
        camera_type="webcam",
    )

    assert camera.embedding_allowed is False
    assert camera.embed_url is None
    assert camera.official_url == "https://example.test/cam"

###############################################################################
def test_normalize_poi_category_maps_optional_provider_sources() -> None:
    assert normalize_poi_category("charging station") == "ev_charging"
    assert normalize_poi_category("gas-station") == "fuel"
    assert normalize_poi_category("railway") == "rail"
    assert normalize_poi_category("pipeline") == "pipelines"
    assert normalize_poi_category("museum") == "tourism"
    assert normalize_poi_category("heliport") == "airports"
    assert normalize_poi_category("fuel stations") == "fuel"
    assert normalize_poi_category("power substation") == "power"
    assert normalize_poi_category("communication tower") == "telecom"
    assert normalize_poi_category("hiking trail") == "trails"
    assert normalize_poi_category("marina") == "ports"
    assert normalize_poi_category("railway station") == "rail"

###############################################################################
def test_deduplicate_poi_features_by_name_category_and_coordinates() -> None:
    first = normalize_poi_feature(
        {"id": "osm-1", "name": "Central Charger", "lat": 45.0, "lon": 7.0},
        source="overpass",
        category="charging_station",
    )
    duplicate = normalize_poi_feature(
        {"id": "ocm-1", "name": "Central Charger", "lat": 45.000004, "lon": 7.000004},
        source="openchargemap",
        category="ev_charging",
    )
    different = normalize_poi_feature(
        {"id": "other-1", "name": "Central Fuel", "lat": 45.0, "lon": 7.0},
        source="overpass",
        category="fuel",
    )

    deduplicated = deduplicate_poi_features([first, duplicate, different])

    assert [feature.id for feature in deduplicated] == ["osm-1", "other-1"]

# --- test_geospatial_poi_benchmark.py ---


###############################################################################
def test_poi_parity_report_matches_by_id_and_tracks_completeness() -> None:
    baseline = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]
    candidate = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]

    report = benchmark_poi_parity(baseline, candidate)

    assert report.matched_count == 2
    assert report.recall == 1.0
    assert report.precision == 1.0
    assert report.meets_thresholds is True

###############################################################################
def test_poi_parity_report_rejects_missing_candidate_coverage_and_duplicates() -> None:
    baseline = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]
    candidate = [
        {"id": "x", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "y", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
    ]

    report = benchmark_poi_parity(baseline, candidate)

    assert report.recall == 0.5
    assert report.duplicate_rate == 0.5
    assert report.meets_thresholds is False

###############################################################################
def test_load_poi_records_accepts_geojson_feature_collections(tmp_path) -> None:
    source = tmp_path / "provider.geojson"
    source.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"p1","properties":{"name":"Clinic"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )

    records = load_poi_records(source)

    assert records == [
        {
            "id": "p1",
            "name": "Clinic",
            "category": None,
            "latitude": 41.9,
            "longitude": 12.5,
        }
    ]

# --- test_geospatial_poi_search_index.py ---


###############################################################################
def test_geospatial_poi_search_index_matches_labels_categories_and_sources() -> None:
    index = build_feature_search_index(
        [
            IndexedFeature(
                id="1", label="Central Museum", category="tourism", source="opentripmap"
            ),
            IndexedFeature(
                id="2",
                label="Fast Charge",
                category="ev_charging",
                source="openchargemap",
            ),
        ]
    )

    assert [item.id for item in query_search_index(index, "museum tourism")] == ["1"]
    assert [item.id for item in query_search_index(index, "ev charging")] == ["2"]

# --- test_geospatial_service_regressions.py ---


###############################################################################
def test_layer_provider_maps_active_fires_to_supported_provider_layer() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("active fires", "fire", "fires"),
                keywords=("active fires", "fire", "fires"),
            ),
        )
    )

    entry = service.resolve("MODIS_Combined_Thermal_Anomalies_Fire")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"