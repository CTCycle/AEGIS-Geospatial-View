from __future__ import annotations

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import CapabilityRoute
from server.domain.agent.decision import ResolvedLocation
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.capability_registry import _operation_candidates
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class _RuntimeEligibility:

    # -------------------------------------------------------------------------
    def __init__(self, *, disabled: set[str] | None = None) -> None:
        self.disabled = disabled or set()

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return capability_id not in self.disabled


###############################################################################
def _registry() -> CapabilityRegistry:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[
            {
                "id": "traffic",
                "name": "Traffic incidents",
                "provider": "test",
                "capabilityKind": "vector-overlay",
                "description": "Current traffic incidents.",
                "capabilities": ["traffic", "incidents"],
                "agenticUse": {
                    "domains": ["data_retrieval", "map_rendering"],
                    "intentTags": ["traffic"],
                },
                "executionContract": {
                    "supported_operations": ["show", "inspect"],
                    "supported_scope_kinds": ["bbox"],
                    "temporal_modes": ["current"],
                    "render_support": "vector",
                    "coverage": "global",
                },
            },
            {
                "id": "weather",
                "name": "Weather forecast",
                "provider": "test",
                "capabilityKind": "raster-overlay",
                "description": "Forecast weather tiles.",
                "capabilities": ["weather", "forecast"],
                "agenticUse": {"domains": ["data_retrieval"]},
                "executionContract": {
                    "supported_operations": ["show", "forecast"],
                    "supported_scope_kinds": ["bbox"],
                    "temporal_modes": ["current", "forecast"],
                    "render_support": "raster",
                    "coverage": "global",
                },
            },
        ],
        cameras=[],
        transit=[],
        tools=[],
        runtime_profiles=(),
    )
    return CapabilityRegistry.from_catalog_snapshot(snapshot)


###############################################################################
def test_shortlist_is_domain_aware_and_bounded() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["weather"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        limit=25,
    )

    assert [item["id"] for item in candidates] == ["weather"]
    assert len(candidates) <= 12
    assert candidates[0]["routing_domains"] == ["data_retrieval"]


###############################################################################
def test_explicit_shortlist_ids_are_ranked_and_disabled_ids_are_filtered() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=[],
        explicit_ids=["traffic", "weather"],
        runtime_registry=_RuntimeEligibility(disabled={"traffic"}),
        limit=12,
    )

    assert [item["id"] for item in candidates] == ["weather"]


###############################################################################
def test_compound_retrieval_and_undated_recent_intent_match_current_feed() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["recent traffic"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        operation="retrieve_and_map",
        scope_kind="bbox",
        temporal_mode="historical",
        temporal_granularity="recent",
        has_explicit_time_range=False,
        requires_render=True,
    )

    assert candidates[0]["id"] == "traffic"


def test_basemap_switch_operations_include_the_manifest_render_primitive() -> None:
    assert "show" in _operation_candidates("switch_basemap_to_satellite")


def test_add_layer_operations_include_the_manifest_render_primitives() -> None:
    assert {"show", "overlay"}.issubset(_operation_candidates("add_layer"))


def test_dated_historical_intent_does_not_match_current_only_feed() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["traffic in 2020"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        operation="retrieve",
        scope_kind="bbox",
        temporal_mode="historical",
        temporal_granularity="year",
        has_explicit_time_range=True,
    )

    assert candidates == []


###############################################################################
def test_route_contract_remains_independent_of_provider_arguments() -> None:
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["traffic"],
    )

    assert "radius_m" not in route.model_dump()


###############################################################################
def test_missing_agentic_domains_are_not_inferred_from_capability_kind() -> None:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[],
        cameras=[],
        transit=[],
        tools=[
            {
                "id": "weather_direct",
                "name": "Weather Forecast",
                "provider": "openmeteo",
                "capabilityKind": "analysis-tool",
                "description": "Current weather and forecast measurements.",
                "capabilities": ["weather", "forecast"],
                "agenticUse": {
                    "defaultEnabled": False,
                    "manualToggle": True,
                    "plannerHints": ["weather", "forecast"],
                    "requiredUserAction": [],
                    "avoidWhen": [],
                },
            }
        ],
        runtime_profiles=(),
    )
    candidates = CapabilityRegistry.from_catalog_snapshot(snapshot).shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["current weather"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
    )

    assert candidates == []


def test_shortlist_applies_manifest_avoid_conditions_and_coverage() -> None:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[
            {
                "id": "us-parcels",
                "name": "US parcel analysis",
                "provider": "test",
                "capabilityKind": "vector-overlay",
                "description": "High precision parcel data.",
                "agenticUse": {
                    "domains": ["spatial_analysis"],
                    "avoidWhen": ["outside United States"],
                },
                "executionContract": {
                    "supported_operations": ["show", "analyze"],
                    "supported_scope_kinds": ["bbox"],
                    "temporal_modes": ["current"],
                    "render_support": "vector",
                    "coverage": "United States",
                },
            }
        ],
        cameras=[],
        transit=[],
        tools=[],
        runtime_profiles=(),
    )
    registry = CapabilityRegistry.from_catalog_snapshot(snapshot)

    zurich = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        country="Switzerland",
    )
    assert registry.shortlist(
        domains={CapabilityDomain.SPATIAL_ANALYSIS},
        queries=["parcel analysis"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        location=zurich,
    ) == []

    rome = zurich.model_copy(update={"label": "Rome", "country": "Italy"})
    assert registry.shortlist(
        domains={CapabilityDomain.SPATIAL_ANALYSIS},
        queries=["parcel analysis"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        location=rome,
    ) == []

    us_location = zurich.model_copy(
        update={"label": "New York", "country": "United States"}
    )
    candidate = registry.shortlist(
        domains={CapabilityDomain.SPATIAL_ANALYSIS},
        queries=["parcel analysis"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        location=us_location,
    )
    assert [item["id"] for item in candidate] == ["us-parcels"]


def test_semantic_routing_uses_manifest_hints_and_rejects_domain_only_matches() -> None:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[
            {
                "id": "hinted_capability",
                "name": "Structured observations",
                "provider": "test",
                "capabilityKind": "vector-overlay",
                "description": "Generic structured observations.",
                "capabilities": ["observations"],
                "agenticUse": {
                    "domains": ["data_retrieval"],
                    "plannerHints": ["weather"],
                    "requiredUserAction": ["weather_map"],
                },
                "executionContract": {
                    "supported_operations": ["show"],
                    "supported_scope_kinds": ["point"],
                    "temporal_modes": ["current"],
                    "render_support": "vector",
                    "coverage": "global",
                },
            },
            {
                "id": "domain_only_capability",
                "name": "Generic observations",
                "provider": "test",
                "capabilityKind": "vector-overlay",
                "description": "Generic structured observations.",
                "capabilities": ["observations"],
                "agenticUse": {"domains": ["data_retrieval"]},
                "executionContract": {
                    "supported_operations": ["show"],
                    "supported_scope_kinds": ["point"],
                    "temporal_modes": ["current"],
                    "render_support": "vector",
                    "coverage": "global",
                },
            },
        ],
        cameras=[],
        transit=[],
        tools=[],
        runtime_profiles=(),
    )
    registry = CapabilityRegistry.from_catalog_snapshot(snapshot)

    weather = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["weather"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
    )
    assert [item["id"] for item in weather] == ["hinted_capability"]

    context_only = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["current conditions"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
    )
    assert context_only == []


def test_real_catalog_aliases_select_environmental_and_hazard_capabilities() -> None:
    registry = CapabilityRegistry()
    runtime = RuntimeRegistry()
    location = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        country="Switzerland",
    )

    vegetation = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["vegetation"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_land_cover",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert {item["id"] for item in vegetation}.issuperset(
        {"esa_worldcover", "MODIS_Terra_NDVI_8Day"}
    )
    assert "local_parcel_template" not in {item["id"] for item in vegetation}

    land_cover = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["land cover"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_land_cover",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert {item["id"] for item in land_cover}.issuperset(
        {"esa_worldcover", "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual"}
    )

    modis = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["MODIS"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_land_cover",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert "MODIS_Terra_NDVI_8Day" in {item["id"] for item in modis}

    worldcover = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["WorldCover"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_land_cover",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert worldcover[0]["id"] == "esa_worldcover"

    for query in ("USGS", "hazard"):
        usgs = registry.shortlist(
            domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
            queries=[query],
            explicit_ids=[],
            runtime_registry=runtime,
            operation="retrieve_hazard",
            scope_kind="bbox",
            temporal_mode="current",
            requires_render=True,
            location=location,
        )
        assert usgs[0]["id"] == "usgs_earthquakes"

    earthquake_catalog = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["earthquakes seismic events earthquake catalog"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_earthquakes",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert earthquake_catalog[0]["id"] == "usgs_earthquakes"


def test_real_catalog_subject_aliases_do_not_substitute_unrelated_layers() -> None:
    registry = CapabilityRegistry()
    runtime = RuntimeRegistry()
    zurich = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        country="Switzerland",
    )
    rome = zurich.model_copy(update={"label": "Rome", "country": "Italy"})

    def shortlist(query: str, operation: str, location: ResolvedLocation) -> list[str]:
        return [
            str(item["id"])
            for item in registry.shortlist(
                domains={
                    CapabilityDomain.DATA_RETRIEVAL,
                    CapabilityDomain.MAP_RENDERING,
                    CapabilityDomain.PLACE_SEARCH,
                },
                queries=[query],
                explicit_ids=[],
                runtime_registry=runtime,
                operation=operation,
                scope_kind="bbox",
                temporal_mode="current",
                requires_render=True,
                location=location,
            )
        ]

    weather = shortlist("weather", "retrieve_weather", zurich)
    assert weather[0] in {
        "openmeteo_pressure_humidity_wind",
        "openmeteo_weather_forecast",
    }
    assert "openmeteo_air_quality_forecast" not in weather

    forecast = shortlist("forecast", "retrieve_weather", zurich)
    assert forecast[0] in {
        "openmeteo_pressure_humidity_wind",
        "openmeteo_weather_forecast",
    }
    assert "openmeteo_air_quality_forecast" not in forecast

    air_quality = shortlist(
        "air quality forecast", "retrieve_weather", zurich
    )
    assert air_quality[0] == "openmeteo_air_quality_forecast"

    poi = shortlist("points of interest", "find_poi", zurich)
    assert poi[0] == "overpass_poi_amenities"
    assert "openaddresses_points" not in poi

    land_cover = shortlist("land cover", "retrieve_land_cover", zurich)
    assert set(land_cover) <= {
        "esa_worldcover",
        "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
    }

    modis_vegetation = shortlist("MODIS vegetation", "retrieve_land_cover", zurich)
    assert set(modis_vegetation) == {
        "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
        "MODIS_Terra_NDVI_8Day",
    }

    modis_land_cover = shortlist("MODIS land cover", "retrieve_land_cover", zurich)
    assert modis_land_cover == [
        "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual"
    ]

    world_cover = shortlist("world cover", "retrieve_land_cover", zurich)
    assert world_cover == ["esa_worldcover"]

    esa = shortlist("European Space Agency", "retrieve_land_cover", zurich)
    assert esa == ["esa_worldcover"]

    demographics = shortlist("census demographics", "retrieve_demographics", rome)
    assert demographics == []

    charging = shortlist("EV charging stations", "retrieve_infrastructure", rome)
    assert charging == []
