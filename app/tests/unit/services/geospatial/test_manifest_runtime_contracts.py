from __future__ import annotations
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import CapabilityRoute
from server.domain.agent.decision import ResolvedLocation
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.capability_registry import CapabilityRegistry, _operation_candidates, normalized_execution_contract
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.geospatial.endpoint_validation import EndpointValidationService
from types import SimpleNamespace
from server.repositories.credential_material import seed_credential_encryption_material
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.composition import GeospatialRuntime, build_provider_execution_policy, build_geospatial_runtime
from server.services.chat.composition import build_chat_runtime
from server.services.geospatial.coverage import CoverageService

# --- test_agentic_manifest_contract.py ---


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

###############################################################################
def test_basemap_switch_operations_include_the_manifest_render_primitive() -> None:
    assert "show" in _operation_candidates("switch_basemap_to_satellite")

###############################################################################
def test_metadata_only_solar_estimate_is_direct_text_and_operation_compatible() -> None:
    registry = CapabilityRegistry()
    runtime = RuntimeRegistry()
    rome = ResolvedLocation(
        label="Rome",
        latitude=41.9028,
        longitude=12.4964,
        country="Italy",
    )

    candidates = registry.shortlist(
        domains={
            CapabilityDomain.DATA_RETRIEVAL,
            CapabilityDomain.PLACE_SEARCH,
            CapabilityDomain.MAP_RENDERING,
        },
        queries=[
            "pvgis solar potential",
            "solar irradiance estimate",
            "photovoltaic potential",
        ],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="estimate_solar_potential",
        scope_kind="bbox",
        temporal_mode=None,
        requires_render=False,
        location=rome,
    )

    assert [candidate["id"] for candidate in candidates] == ["pvgis_solar"]
    assert runtime.supports_mode("pvgis_solar", "map") is False
    assert runtime.supports_mode("pvgis_solar", "text") is True

###############################################################################
def test_add_layer_operations_include_the_manifest_render_primitives() -> None:
    assert {"show", "overlay"}.issubset(_operation_candidates("add_layer"))

###############################################################################
def test_comparing_places_matches_the_same_capabilities_as_retrieving_them() -> None:
    # "Compare today's weather in Zurich and Lisbon" is a per-target retrieval;
    # no manifest declares a "compare" primitive, so it must not filter the
    # catalog down to nothing.
    registry = CapabilityRegistry(manifest_loader=GeospatialManifestLoader())
    route = dict(
        domains={
            CapabilityDomain.DATA_RETRIEVAL,
            CapabilityDomain.MAP_RENDERING,
            CapabilityDomain.PLACE_SEARCH,
        },
        queries=["weather forecast", "temperature", "precipitation"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        scope_kind="point",
        temporal_mode="forecast",
        temporal_granularity="day",
        requires_render=True,
    )

    compared = [item["id"] for item in registry.shortlist(operation="compare", **route)]
    retrieved = [item["id"] for item in registry.shortlist(operation="retrieve", **route)]

    assert "openmeteo_weather_forecast" in compared
    assert compared == retrieved

###############################################################################
def test_avoid_condition_needs_the_whole_phrase_not_one_shared_word() -> None:
    registry = CapabilityRegistry(manifest_loader=GeospatialManifestLoader())
    route = dict(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        operation="add_layer",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        # A European map: the CONUS-only NOAA radar is out of coverage.
        location=ResolvedLocation(
            label="Lisbon, Portugal", latitude=38.7078, longitude=-9.1366, country="Portugal"
        ),
    )

    def shortlisted(queries: list[str]) -> list[object]:
        return [item["id"] for item in registry.shortlist(queries=queries, **route)]

    # RainViewer avoids "satellite infrared imagery"; "rain radar imagery"
    # shares only the word "imagery" and is exactly what it provides.
    assert "rainviewer_precipitation_radar" in shortlisted(
        ["precipitation radar", "weather radar latest", "rain radar imagery"]
    )
    assert "rainviewer_precipitation_radar" not in shortlisted(
        ["satellite infrared imagery"]
    )

###############################################################################
def test_plain_subject_query_still_counts_beside_an_alias_variant() -> None:
    # "pharmacies" names the subject; the alias variant "points of interest
    # near a landmark" carries the anchor word "landmark".  The subject query
    # alone must keep the POI source eligible.
    registry = CapabilityRegistry(manifest_loader=GeospatialManifestLoader())

    candidates = registry.shortlist(
        domains={
            CapabilityDomain.PLACE_SEARCH,
            CapabilityDomain.MAP_RENDERING,
            CapabilityDomain.DATA_RETRIEVAL,
        },
        queries=["pharmacies", "points of interest near a landmark"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        operation="find_nearby",
        scope_kind="bbox",
        requires_render=True,
        location=ResolvedLocation(
            label="Pantheon, Rome", latitude=41.8986, longitude=12.4768, country="Italy"
        ),
    )

    assert "overpass_poi_amenities" in [item["id"] for item in candidates]

###############################################################################
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
        location_mode="target",
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

###############################################################################
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

###############################################################################
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

###############################################################################
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

    named_gibs_layer = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["nasa gibs modis terra 8 day ndvi vegetation"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_and_render",
        scope_kind="bbox",
        requires_render=True,
        location=location,
    )
    assert named_gibs_layer[0]["id"] == "MODIS_Terra_NDVI_8Day"

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

    # Inside the Euro-Mediterranean preferred area EMSC outranks the global
    # USGS catalog unless USGS is named.
    for query, expected in (("USGS", "usgs_earthquakes"), ("hazard", "emsc_earthquakes")):
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
        assert usgs[0]["id"] == expected

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
    assert earthquake_catalog[0]["id"] == "emsc_earthquakes"

    earthquake_route = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["earthquake events seismic activity recent earthquakes"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="show_earthquakes",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=location,
    )
    assert earthquake_route[0]["id"] == "emsc_earthquakes"

    water_gauges = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=[
            "USGS water gauges",
            "streamflow monitoring stations",
            "active hydrologic sensors",
        ],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="retrieve_features",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=ResolvedLocation(
            label="Austin, Texas",
            latitude=30.2711,
            longitude=-97.7437,
            country="United States",
        ),
    )
    assert water_gauges[0]["id"] == "usgs_water_gauges"

###############################################################################
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

###############################################################################
def test_rainviewer_recent_radar_routes_for_naples_and_venice_but_not_nowcast() -> None:
    registry = CapabilityRegistry()
    runtime = RuntimeRegistry()
    locations = (
        ResolvedLocation(
            label="Naples",
            latitude=40.8518,
            longitude=14.2681,
            country="Italy",
        ),
        ResolvedLocation(
            label="Venice",
            latitude=45.4408,
            longitude=12.3155,
            country="Italy",
        ),
    )

    for location in locations:
        candidates = registry.shortlist(
            domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
            queries=["RainViewer recent precipitation radar"],
            explicit_ids=[],
            runtime_registry=runtime,
            operation="show",
            scope_kind="bbox",
            temporal_mode="current",
            requires_render=True,
            location=location,
        )
        assert candidates[0]["id"] == "rainviewer_precipitation_radar"

    nowcast = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["RainViewer future radar nowcast"],
        explicit_ids=[],
        runtime_registry=runtime,
        operation="show",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=locations[0],
    )
    assert nowcast == []

###############################################################################
def test_real_catalog_keyless_vector_point_capabilities_route_for_tier3() -> None:
    """Guard the T3-10..T3-14 keyless campaign capabilities at the router.

    Each target capability must be shortlisted for a representative
    browser-authoritative prompt (requires_render) and filtered for an
    out-of-scope prompt, independent of any manual-toggle settings action.
    """
    registry = CapabilityRegistry()
    runtime = RuntimeRegistry()
    domains = {
        CapabilityDomain.DATA_RETRIEVAL,
        CapabilityDomain.MAP_RENDERING,
        CapabilityDomain.PLACE_SEARCH,
        CapabilityDomain.SPATIAL_ANALYSIS,
    }

    def ids(
        query: str,
        operation: str,
        location: ResolvedLocation,
        temporal_mode: str = "current",
    ) -> list[str]:
        return [
            str(item["id"])
            for item in registry.shortlist(
                domains=domains,
                queries=[query],
                explicit_ids=[],
                runtime_registry=runtime,
                operation=operation,
                scope_kind="bbox",
                temporal_mode=temporal_mode,
                requires_render=True,
                location=location,
            )
        ]

    tokyo = ResolvedLocation(
        label="Tokyo",
        latitude=35.6762,
        longitude=139.6503,
        country="Japan",
    )
    charleston = ResolvedLocation(
        label="Charleston, South Carolina",
        latitude=32.7765,
        longitude=-79.9311,
        country="United States",
    )
    houston = ResolvedLocation(
        label="Houston, Texas",
        latitude=29.7604,
        longitude=-95.3698,
        country="United States",
    )
    rome = ResolvedLocation(
        label="Rome",
        latitude=41.9028,
        longitude=12.4964,
        country="Italy",
    )
    bologna = ResolvedLocation(
        label="Bologna",
        latitude=44.4949,
        longitude=11.3426,
        country="Italy",
    )
    lugano = ResolvedLocation(
        label="Lugano",
        latitude=46.0037,
        longitude=8.9511,
        country="Switzerland",
    )

    earthquakes = ids(
        "earthquake events seismic activity recent earthquakes",
        "show_earthquakes",
        tokyo,
    )
    assert earthquakes[0] == "usgs_earthquakes"

    water_levels = ids("coastal water level stations", "show", charleston)
    assert water_levels[0] == "noaa_coops_water_levels"

    radar = ids("current weather radar", "show", houston)
    assert radar[0] == "noaa_radar"

    buildings = ids("residential buildings", "show", rome)
    assert buildings[0] == "overpass_residential_buildings"

    amenities = ids("nearby pharmacies amenities", "show", bologna)
    assert "overpass_poi_amenities" in amenities

    atmospheric = ids("wind humidity pressure", "show", rome)
    assert atmospheric[0] == "openmeteo_pressure_humidity_wind"
    assert "openmeteo_air_quality_forecast" not in atmospheric

    occurrences = ids(
        "species occurrences biodiversity",
        "show",
        lugano,
        temporal_mode="none",
    )
    assert occurrences[0] == "gbif_species_occurrences"

    # gbif must still be avoided for its intended non-occurrence intents.
    exhaustive = ids(
        "exhaustive species inventory all records",
        "show",
        lugano,
        temporal_mode="none",
    )
    assert "gbif_species_occurrences" not in exhaustive

    bulk = ids(
        "bulk export occurrences",
        "show",
        lugano,
        temporal_mode="none",
    )
    assert "gbif_species_occurrences" not in bulk

    # The same prompts must not leak an unrelated credentialed or
    # non-renderable capability into the shortlist.
    assert "opentripmap_tourism_pois" not in amenities
    assert "openmeteo_elevation" not in atmospheric

###############################################################################
def test_openaq_stations_are_discoverable_for_a_map_request() -> None:
    registry = CapabilityRegistry(manifest_loader=GeospatialManifestLoader())

    # The queries the live model issued for "air quality monitoring stations".
    shortlisted = registry.shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
        queries=["air quality monitoring stations", "air quality sensors"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        operation="show",
        scope_kind="bbox",
        temporal_mode="current",
        requires_render=True,
        location=ResolvedLocation(
            label="Rome, Italy", latitude=41.8933, longitude=12.4829, country="Italy"
        ),
    )

    assert "openaq_air_quality" in [item["id"] for item in shortlisted]

# --- test_capability_registry.py ---


###############################################################################
def test_capability_registry_loads_tools() -> None:
    registry = CapabilityRegistry()
    snapshot = registry.load_capabilities()
    assert snapshot.tools
    assert registry.get_capability("get_weather_forecast") is not None

###############################################################################
def test_execution_contract_is_read_from_the_manifest() -> None:
    contract = CapabilityRegistry().execution_contract(
        "openmeteo_weather_forecast"
    )

    assert contract["supported_operations"] == ["show", "inspect", "forecast"]
    assert contract["supported_scope_kinds"] == ["point", "bbox", "grid_sample"]
    assert contract["render_support"] == "vector"
    assert contract["output_geometry_type"] == "Point"

###############################################################################
def test_execution_contract_is_not_inferred_for_an_incomplete_manifest() -> None:
    contract = normalized_execution_contract(
        {
            "id": "incomplete",
            "type": "time-series-insight",
            "capabilityKind": "analysis-tool",
            "name": "Weather forecast",
            "metadata": {"geometry_type": "point", "queryable": True},
        }
    )

    assert contract["supported_operations"] == []
    assert contract["supported_scope_kinds"] == []
    assert contract["render_support"] == "none"

# --- test_manifest_metadata_contract.py ---


###############################################################################
class _NoCredentials:

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None


REQUIRED_TRAIT_FIELDS = {
    "official_docs_url",
    "source_protocol",
    "data_format",
    "geometry_type",
    "endpoint_health",
    "auth_mode",
    "rate_limit_notes",
}

###############################################################################
def test_all_manifest_entries_expose_source_traits() -> None:
    payload = GeospatialManifestLoader().load_all()
    missing: list[str] = []
    for collection_name in ("providers", "basemaps", "overlays", "tools"):
        for item in payload[collection_name]:
            metadata = dict(item.get("metadata") or {})
            for field in REQUIRED_TRAIT_FIELDS:
                if not metadata.get(field):
                    missing.append(f"{collection_name}:{item['id']}:metadata.{field}")
    assert not missing

###############################################################################
def test_enabled_executable_manifests_declare_execution_contracts() -> None:
    payload = GeospatialManifestLoader().load_all()
    profiles = {
        str(item["capability_id"]): item for item in payload["runtime_profiles"]
    }
    missing = [
        f"{collection_name}:{item['id']}"
        for collection_name in ("basemaps", "overlays", "cameras", "transit", "tools")
        for item in payload[collection_name]
        if (
            bool(profiles.get(item["id"], {}).get("enabled_by_default"))
            or bool(profiles.get(item["id"], {}).get("manual_toggle"))
        )
        and not isinstance(item.get("executionContract"), dict)
    ]

    assert not missing

###############################################################################
def test_credentialed_capabilities_are_not_healthy_without_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
    runtime = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
    )
    runtime.build_snapshot()

    assert runtime.provider_health("openaq_air_quality") == "missing_credentials"

###############################################################################
def test_endpoint_validation_builds_sampled_urls_without_network_calls() -> None:
    payload = GeospatialManifestLoader().load_all()
    overlays = {item["id"]: item for item in payload["overlays"]}
    service = EndpointValidationService()

    census_url = service.build_validation_url(overlays["census_tigerweb_hydrography"])
    assert census_url is not None
    assert "{bbox}" not in census_url
    assert "f=geojson" in census_url

    esa_url = service.build_validation_url(overlays["esa_worldcover"])
    assert esa_url is not None
    assert "GetCapabilities" in esa_url

    basemaps = {item["id"]: item for item in payload["basemaps"]}
    openfreemap_url = service.build_validation_url(basemaps["openfreemap_liberty"])
    assert openfreemap_url == "https://tiles.openfreemap.org/styles/liberty"
    osm_url = service.build_validation_url(basemaps["osm_default"])
    assert osm_url is not None
    assert osm_url.endswith("/6/33/23.png")

# --- test_runtime_registry.py ---


###############################################################################
class _CredentialRepo:

    # -------------------------------------------------------------------------
    def __init__(self, present: bool) -> None:
        self.present = present

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if (
            self.present
            and provider in {"tomtom", "openchargemap"}
            and label == "api_key"
        ):
            return object()
        return None

###############################################################################
def test_runtime_registry_reads_profiles() -> None:
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )
    snapshot = registry.build_snapshot()
    assert "osm_default" in snapshot.profiles
    assert registry.is_enabled("osm_default")

###############################################################################
def test_runtime_profiles_cover_all_capabilities() -> None:
    capability_registry = CapabilityRegistry()
    capabilities = capability_registry.load_capabilities()
    all_capability_ids = {
        *(str(item.get("id")) for item in capabilities.basemaps),
        *(str(item.get("id")) for item in capabilities.overlays),
        *(str(item.get("id")) for item in capabilities.tools),
    }
    runtime_profiles = (
        RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_CredentialRepo(False),
        )
        .build_snapshot()
        .profiles
    )
    missing = sorted(
        capability_id
        for capability_id in all_capability_ids
        if capability_id not in runtime_profiles
    )
    assert not missing

###############################################################################
def test_key_required_providers_are_unavailable_without_saved_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]
    registry.build_snapshot()

    assert not registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "missing_credentials"

###############################################################################
def test_key_required_providers_use_saved_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(True),
    )  # type: ignore[arg-type]
    registry.build_snapshot()

    assert registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "healthy"

###############################################################################
def test_openchargemap_requires_saved_key_or_local_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("AEGIS_OCM_SNAPSHOT_PATH", raising=False)
    unavailable = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]

    assert not unavailable.access_available("openchargemap_ev_charging")
    assert unavailable.provider_health("openchargemap_ev_charging") == "missing_access"
    assert "Open Charge Map" in (
        unavailable.access_reason("openchargemap_ev_charging") or ""
    )

    snapshot = tmp_path / "openchargemap.json"
    snapshot.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("AEGIS_OCM_SNAPSHOT_PATH", str(snapshot))
    local = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]

    assert local.access_available("openchargemap_ev_charging")
    assert local.provider_health("openchargemap_ev_charging") == "healthy"

###############################################################################
def test_openchargemap_is_available_with_saved_access_credential(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_OCM_SNAPSHOT_PATH", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(True),
    )  # type: ignore[arg-type]

    assert registry.access_available("openchargemap_ev_charging")
    assert registry.provider_health("openchargemap_ev_charging") == "healthy"

###############################################################################
def test_configured_gtfs_feeds_require_a_feed_source(monkeypatch) -> None:
    feed_profiles = (
        ("gtfs_static", "AEGIS_GTFS_STATIC_FEED_URL"),
        ("gtfs_realtime", "AEGIS_GTFS_REALTIME_FEED_URL"),
    )
    for capability_id, env_name in feed_profiles:
        monkeypatch.delenv(env_name, raising=False)
        unavailable = RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_CredentialRepo(False),
        )  # type: ignore[arg-type]

        assert not unavailable.access_available(capability_id)
        assert unavailable.provider_health(capability_id) == "missing_access"

        monkeypatch.setenv(env_name, "https://transit.example.test/feed")
        configured = RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_CredentialRepo(False),
        )  # type: ignore[arg-type]

        assert configured.access_available(capability_id)
        assert configured.provider_health(capability_id) == "healthy"

###############################################################################
def test_restricted_capability_is_disabled_without_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_ALLOW_RESTRICTED_SOURCES", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )

    assert not registry.is_enabled("openmeteo_elevation")
    assert registry.provider_health("openmeteo_elevation") == "disabled"

###############################################################################
def test_restricted_capability_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALLOW_RESTRICTED_SOURCES", "true")
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )

    assert registry.is_enabled("openmeteo_elevation")
    assert registry.provider_health("openmeteo_elevation") == "healthy"

# --- test_tool_runtime_profiles.py ---


###############################################################################

###############################################################################
def test_tool_runtime_profiles_complete() -> None:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
    )
    tools = capabilities.load_capabilities().tools
    profiles = runtime.build_snapshot().profiles
    for tool in tools:
        assert tool["id"] in profiles

# --- test_geospatial_runtime_composition.py ---



###############################################################################
def test_provider_policy_uses_source_timeout_floors() -> None:
    settings = SimpleNamespace(
        agent_execution=SimpleNamespace(
            provider_request_seconds=10.0,
            provider_max_attempts=2,
            retry_backoff_base_seconds=0.25,
            retry_backoff_max_seconds=2.0,
        ),
        nominatim=SimpleNamespace(timeout=12.0),
        openmeteo=SimpleNamespace(timeout=15.0),
        overpass=SimpleNamespace(timeout=20.0),
        rainviewer=SimpleNamespace(timeout=15.0),
        gibs=SimpleNamespace(timeout=20.0, layer_sync_timeout=30.0),
    )

    policy = build_provider_execution_policy(settings)

    assert policy.timeout_seconds == 10.0
    assert policy.provider_timeout_seconds == {
        "nominatim": 12.0,
        "openmeteo": 15.0,
        "overpass": 20.0,
        "rainviewer": 15.0,
        "usgs": 40.0,
        "emsc": 40.0,
        "gibs": 30.0,
    }

###############################################################################
def test_build_geospatial_runtime_reuses_shared_services(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    runtime = build_geospatial_runtime(sqlite_backend)

    assert isinstance(runtime, GeospatialRuntime)
    assert isinstance(runtime.api_service, GeospatialApiService)
    assert runtime.api_service.catalog_service.capability_registry is not None
    assert runtime.api_service.catalog_snapshot is runtime.catalog_snapshot
    assert (
        runtime.api_service.catalog_service.runtime_registry
        is runtime.api_service.runtime_registry
    )
    assert (
        runtime.api_service.catalog_service.capability_registry.catalog_snapshot
        is runtime.catalog_snapshot
    )
    assert (
        runtime.api_service.provider_registry.catalog_snapshot
        is runtime.catalog_snapshot
    )

###############################################################################
def test_chat_consumes_shared_geospatial_runtime(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    geospatial_runtime = build_geospatial_runtime(sqlite_backend)
    chat_runtime = build_chat_runtime(
        sqlite_backend,
        geospatial_runtime=geospatial_runtime,
    )

    assert (
        chat_runtime.agent_orchestrator.policy_engine.capability_registry
        is geospatial_runtime.capability_registry
    )
    assert (
        chat_runtime.agent_orchestrator.policy_engine.runtime_registry
        is geospatial_runtime.runtime_registry
    )
    assert (
        chat_runtime.agent_orchestrator.tool_registry.runtime_registry
        is geospatial_runtime.runtime_registry
    )
    assert chat_runtime.agent_loop is chat_runtime.agent_orchestrator.agent_loop
    assert chat_runtime.agent_loop is not None
    assert (
        chat_runtime.agent_turn_runner
        is chat_runtime.agent_orchestrator.agent_turn_runner
    )
    assert chat_runtime.agent_turn_runner is not None
    assert {
        tool.definition.name
        for tool in chat_runtime.agent_loop.tool_registry._registered_tools.values()
    } == {
        "route_request",
        "resolve_geospatial_location",
        "discover_geospatial_capabilities",
        "discover_geospatial_provider_layers",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
        "inspect_evidence",
        "transform_evidence",
        "apply_map_plan",
        "search_conversation_history",
    }

# --- test_coverage.py ---


###############################################################################

###############################################################################
def test_coverage_global_policy_supported() -> None:
    service = CoverageService(
        runtime_registry=RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
        )
    )
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    assert service.is_location_supported("osm_default", location)