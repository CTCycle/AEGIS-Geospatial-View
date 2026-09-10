from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import run_async_in_thread
from server.contracts.extraction import (
    OverlayCommand,
    OverlaySelector,
    OverlayScope,
    OverlayStateReference,
)
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ViewportPolicy,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler

###############################################################################
def _instance(
    instance_id: str,
    capability_id: str,
    *,
    label: str,
    scope_key: str,
    latitude: float,
    longitude: float,
    visible: bool = True,
) -> OverlayInstance:
    return OverlayInstance(
        instance_id=instance_id,
        capability_id=capability_id,
        label=label,
        provider="openmeteo",
        overlay_type="raster",
        rendering_mode="raster-tile",
        scope_key=scope_key,
        scope={"kind": "location", "label": scope_key},
        resolved_location={
            "label": scope_key,
            "latitude": latitude,
            "longitude": longitude,
            "country": "Switzerland",
        },
        visible=visible,
        descriptor={"id": instance_id, "label": label, "capability_id": capability_id},
    )

###############################################################################
def test_hide_one_instance_preserves_unrelated_descriptor() -> None:
    weather = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    traffic = _instance(
        "traffic-zurich",
        "tomtom_traffic_flow",
        label="Traffic",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    collection = OverlayCollectionState(instances=[weather, traffic])
    command = OverlayCommand(
        action="hide",
        selector=OverlaySelector(instance_ids=["weather-zurich"]),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(collection, command)

    assert updated.revision == 1
    assert updated.instances[0].visible is False
    assert updated.instances[1].descriptor == traffic.descriptor
    assert result.updated_instance_ids == ["weather-zurich"]

###############################################################################
def test_identity_resolution_falls_through_unmatched_instance_alias_to_capability() -> (
    None
):
    weather = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    command = OverlayCommand(
        action="hide",
        selector=OverlaySelector(
            instance_ids=["openmeteo_weather_forecast"],
            capability_ids=["openmeteo_weather_forecast"],
            concepts=["weather"],
        ),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(
        OverlayCollectionState(instances=[weather]), command
    )

    assert updated.instances[0].visible is False
    assert result.updated_instance_ids == ["weather-zurich"]

###############################################################################
def test_location_scoped_remove_does_not_remove_other_scope() -> None:
    zurich = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    switzerland = _instance(
        "weather-switzerland",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Switzerland",
        latitude=46.8,
        longitude=8.2,
    )
    collection = OverlayCollectionState(instances=[zurich, switzerland])
    command = OverlayCommand(
        action="remove",
        selector=OverlaySelector(concepts=["weather"]),
        scope=OverlayScope(kind="location", location={"label": "Zurich"}),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(collection, command)

    assert [item.instance_id for item in updated.instances] == ["weather-switzerland"]
    assert result.removed_instance_ids == ["weather-zurich"]


def test_location_scope_matches_partial_canonical_place_without_coordinates() -> None:
    bologna = _instance(
        "species-bologna",
        "gbif_species_occurrences",
        label="Species records",
        scope_key="Bologna, Emilia-Romagna, Italy",
        latitude=44.4938,
        longitude=11.3426,
    )
    command = OverlayCommand(
        action="add",
        selector=OverlaySelector(capability_ids=["gbif_species_occurrences"]),
        scope=OverlayScope(
            kind="location",
            location={
                "city": "Bologna",
                "country": "Italy",
                "radius_m": 20_000,
            },
            label="Species records within 20 km of Bologna",
        ),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(
        OverlayCollectionState(instances=[bologna]), command
    )

    assert [item.instance_id for item in updated.instances] == ["species-bologna"]
    assert result.added_instance_ids == []


###############################################################################
def test_current_view_remove_removes_only_visible_overlays_inside_view() -> None:
    collection = OverlayCollectionState(
        instances=[
            _instance(
                "inside-visible",
                "weather-inside",
                label="Inside visible",
                scope_key="view",
                latitude=47.05,
                longitude=8.05,
            ),
            _instance(
                "inside-hidden",
                "weather-hidden",
                label="Inside hidden",
                scope_key="view",
                latitude=47.06,
                longitude=8.06,
                visible=False,
            ),
            _instance(
                "outside-visible",
                "weather-outside",
                label="Outside visible",
                scope_key="other",
                latitude=47.50,
                longitude=8.50,
            ),
        ]
    )
    command = OverlayCommand(
        action="remove",
        selector=OverlaySelector(visibility="visible"),
        scope=OverlayScope(kind="current_view"),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(
        collection,
        command,
        current_view={
            "center_latitude": 47.05,
            "center_longitude": 8.05,
            "radius_m": 10_000,
            "bbox": [8.0, 47.0, 8.1, 47.1],
        },
    )

    assert updated.revision == 1
    assert [item.instance_id for item in updated.instances] == [
        "inside-hidden",
        "outside-visible",
    ]
    assert result.removed_instance_ids == ["inside-visible"]

###############################################################################
def test_current_view_remove_uses_viewport_center_when_bbox_is_unavailable() -> None:
    collection = OverlayCollectionState(
        instances=[
            _instance(
                "same-location",
                "weather-same",
                label="Same location",
                scope_key="view",
                latitude=47.37,
                longitude=8.54,
            ),
            _instance(
                "other-location",
                "weather-other",
                label="Other location",
                scope_key="other",
                latitude=47.50,
                longitude=8.50,
            ),
        ]
    )
    command = OverlayCommand(
        action="remove",
        selector=OverlaySelector(visibility="visible"),
        scope=OverlayScope(kind="current_view"),
    )

    updated, result = OverlayCollectionService.apply(
        collection,
        command,
        current_view={
            "center_latitude": 47.37,
            "center_longitude": 8.54,
            "radius_m": 2_500,
        },
    )

    assert [item.instance_id for item in updated.instances] == ["other-location"]
    assert result.removed_instance_ids == ["same-location"]

###############################################################################
def test_keep_only_removes_nonmatching_instances() -> None:
    collection = OverlayCollectionState(
        instances=[
            _instance(
                "weather",
                "openmeteo_weather_forecast",
                label="Weather",
                scope_key="global",
                latitude=0,
                longitude=0,
            ),
            _instance(
                "traffic",
                "tomtom_traffic_flow",
                label="Traffic",
                scope_key="global",
                latitude=0,
                longitude=0,
            ),
        ]
    )
    command = OverlayCommand(
        action="keep_only",
        selector=OverlaySelector(capability_ids=["openmeteo_weather_forecast"]),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(collection, command)

    assert [item.instance_id for item in updated.instances] == ["weather"]
    assert result.removed_instance_ids == ["traffic"]

###############################################################################
def test_revision_conflict_preserves_collection() -> None:
    collection = OverlayCollectionState(revision=3)
    command = OverlayCommand(
        action="remove",
        selector=OverlaySelector(concepts=["weather"]),
        state_reference=OverlayStateReference(revision=2),
    )

    updated, result = OverlayCollectionService.apply(collection, command)

    assert updated == collection
    assert result.revision == 3
    assert result.clarification

###############################################################################
def test_apply_overlay_commands_binds_default_revision_between_mutations() -> None:
    weather = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    traffic = _instance(
        "traffic-zurich",
        "tomtom_traffic_flow",
        label="Traffic",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    session = MapSession(
        session_id="map-1",
        resolved_location=ResolvedLocation(
            label="Zurich", latitude=47.37, longitude=8.54
        ),
        basemap_id="osm_default",
        viewport=ViewportPolicy(
            center_latitude=47.37,
            center_longitude=8.54,
            radius_m=2_500,
        ),
        overlay_collection=OverlayCollectionState(instances=[weather, traffic]),
    )

    updated, results = AgentTurnStateAssembler.apply_overlay_commands(
        session,
        [
            OverlayCommand(
                action="remove",
                selector=OverlaySelector(instance_ids=["weather-zurich"]),
            ),
            OverlayCommand(
                action="hide",
                selector=OverlaySelector(instance_ids=["traffic-zurich"]),
            ),
        ],
    )

    assert [result.revision for result in results] == [1, 2]
    assert updated.overlay_collection.revision == 2
    assert updated.overlay_collection.instances[0].visible is False

###############################################################################
def test_local_overlay_partition_keeps_provider_work_independent() -> None:
    collection = OverlayCollectionState(
        instances=[
            _instance(
                "weather-zurich",
                "openmeteo_weather_forecast",
                label="Weather",
                scope_key="Zurich",
                latitude=47.37,
                longitude=8.54,
            )
        ]
    )
    remove = OverlayCommand(
        action="remove",
        selector=OverlaySelector(instance_ids=["weather-zurich"]),
    )
    add = OverlayCommand(
        action="add",
        selector=OverlaySelector(capability_ids=["missing-capability"]),
    )

    applicable = OverlayCollectionService.locally_applicable_commands(
        collection, [remove, add]
    )

    assert applicable == [remove]
    assert not OverlayCollectionService.can_apply_locally(collection, [remove, add])

###############################################################################
def test_add_reuses_same_capability_and_scope_identity() -> None:
    collection = OverlayCollectionState()
    command = OverlayCommand(
        action="add",
        selector=OverlaySelector(capability_ids=["openmeteo_weather_forecast"]),
        scope=OverlayScope(
            kind="location",
            location={"label": "Zurich", "latitude": 47.37, "longitude": 8.54},
        ),
        state_reference=OverlayStateReference(revision=0),
    )
    catalog = [
        {
            "id": "openmeteo_weather_forecast",
            "label": "Weather",
            "provider": "openmeteo",
            "type": "raster",
            "rendering_mode": "raster-tile",
            "descriptor": {"id": "catalog-weather"},
        }
    ]

    first, first_result = OverlayCollectionService.apply(
        collection, command, catalog=catalog
    )
    second, second_result = OverlayCollectionService.apply(
        first,
        command.model_copy(
            update={
                "state_reference": OverlayStateReference(revision=first.revision),
            }
        ),
        catalog=catalog,
    )

    assert len(first.instances) == 1
    assert first_result.added_instance_ids == [first.instances[0].instance_id]
    assert len(second.instances) == 1
    assert second.instances[0].instance_id == first.instances[0].instance_id
    assert second_result.added_instance_ids == []

###############################################################################
def test_missing_location_scope_binds_to_the_map_session_target() -> None:
    weather = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    session = MapSession(
        session_id="map-1",
        resolved_location=ResolvedLocation(
            label="Zurich", latitude=47.37, longitude=8.54
        ),
        basemap_id="osm_default",
        viewport=ViewportPolicy(
            center_latitude=47.37,
            center_longitude=8.54,
            radius_m=2_500,
        ),
        overlay_collection=OverlayCollectionState(instances=[weather]),
    )

    updated, results = AgentTurnStateAssembler.apply_overlay_commands(
        session,
        [
            OverlayCommand(
                action="add",
                selector=OverlaySelector(
                    capability_ids=["openmeteo_weather_forecast"]
                ),
                scope=OverlayScope(kind="location"),
            )
        ],
    )

    assert len(updated.overlay_collection.instances) == 1
    assert results[0].added_instance_ids == []
    assert updated.overlay_collection.revision == 0

###############################################################################
def test_catalog_selector_filters_provider_type_and_tags() -> None:
    command = OverlayCommand(
        action="add",
        selector=OverlaySelector(
            concepts=["weather"],
            providers=["official-feed"],
            overlay_types=["raster"],
            tags=["forecast"],
        ),
        state_reference=OverlayStateReference(revision=0),
    )
    catalog = [
        {
            "id": "weather-official",
            "label": "Weather forecast",
            "provider": "official-feed",
            "type": "raster",
            "rendering_mode": "raster-tile",
            "concepts": ["weather"],
            "tags": ["forecast"],
        },
        {
            "id": "weather-community",
            "label": "Weather forecast",
            "provider": "community-feed",
            "type": "raster",
            "rendering_mode": "raster-tile",
            "concepts": ["weather"],
            "tags": ["forecast"],
        },
    ]

    updated, result = OverlayCollectionService.apply(
        collection=OverlayCollectionState(), command=command, catalog=catalog
    )

    assert result.added_instance_ids == [updated.instances[0].instance_id]
    assert updated.instances[0].capability_id == "weather-official"
    assert updated.instances[0].descriptor["tags"] == ["forecast"]

###############################################################################
def test_catalog_selector_accepts_redundant_alias_fields_for_capability() -> None:
    command = OverlayCommand(
        action="show",
        selector=OverlaySelector(
            capability_ids=["openmeteo_weather_forecast"],
            concepts=["weather"],
            labels=["weather"],
            tags=["weather"],
        ),
        state_reference=OverlayStateReference(revision=0),
    )
    catalog = [
        {
            "id": "openmeteo_weather_forecast",
            "label": "Open-Meteo Weather Forecast",
            "provider": "openmeteo",
            "type": "point-insight",
            "rendering_mode": "metadata-only",
        }
    ]

    updated, result = OverlayCollectionService.apply(
        OverlayCollectionState(), command, catalog=catalog
    )

    assert result.added_instance_ids == [updated.instances[0].instance_id]
    assert updated.instances[0].capability_id == "openmeteo_weather_forecast"

###############################################################################
def test_unmatched_selector_that_targets_active_basemap_is_explained_without_mutation() -> (
    None
):
    command = OverlayCommand(
        action="hide",
        selector=OverlaySelector(labels=["imagery"]),
        state_reference=OverlayStateReference(revision=0),
    )

    updated, result = OverlayCollectionService.apply(
        OverlayCollectionState(),
        command,
        basemap={
            "id": "esri_world_imagery",
            "label": "Satellite Imagery",
            "provider": "arcgis",
            "type": "tile",
            "capabilities": ["tile", "imagery"],
        },
    )

    assert updated == OverlayCollectionState()
    assert result.unmatched_selectors == ["imagery"]
    assert result.clarification is not None
    assert "active map basemap, not an overlay" in result.clarification

###############################################################################
def test_ambiguous_catalog_selector_and_no_match_preserve_state() -> None:
    ambiguous = OverlayCommand(
        action="add",
        selector=OverlaySelector(concepts=["weather"]),
        state_reference=OverlayStateReference(revision=0),
    )
    catalog = [
        {"id": "weather-one", "label": "Weather", "concepts": ["weather"]},
        {"id": "weather-two", "label": "Weather", "concepts": ["weather"]},
    ]
    unchanged, ambiguous_result = OverlayCollectionService.apply(
        OverlayCollectionState(), ambiguous, catalog=catalog
    )

    assert unchanged.instances == []
    assert unchanged.revision == 0
    assert ambiguous_result.ambiguous_selectors == ["weather"]
    assert ambiguous_result.clarification

    no_match = OverlayCommand(
        action="remove",
        selector=OverlaySelector(instance_ids=["missing"]),
        state_reference=OverlayStateReference(revision=0),
    )
    still_unchanged, no_match_result = OverlayCollectionService.apply(
        unchanged, no_match
    )
    assert still_unchanged == unchanged
    assert no_match_result.unmatched_selectors == ["missing"]

###############################################################################
def test_provider_candidate_is_committed_against_active_revision_without_dropping_state() -> (
    None
):
    location = ResolvedLocation(
        label="Zurich", latitude=47.37, longitude=8.54, country="Switzerland"
    )
    viewport = ViewportPolicy(center_latitude=47.37, center_longitude=8.54)
    active = MapSession(
        session_id="active",
        resolved_location=location,
        basemap_id="osm_default",
        viewport=viewport,
        overlay_collection=OverlayCollectionState(revision=1),
    )
    fetched = active.model_copy(
        update={
            "session_id": "fetched",
            "overlay_collection": OverlayCollectionState(
                instances=[
                    OverlayInstance(
                        instance_id="catalog-weather",
                        capability_id="openmeteo_weather_forecast",
                        label="Weather",
                        provider="openmeteo",
                        overlay_type="raster",
                        rendering_mode="metadata-only",
                        descriptor={
                            "id": "catalog-weather",
                            "capability_id": "openmeteo_weather_forecast",
                            "label": "Weather",
                            "provider": "openmeteo",
                            "type": "raster",
                            "rendering_mode": "metadata-only",
                        },
                    )
                ]
            ),
        }
    )
    command = OverlayCommand(
        action="show",
        selector=OverlaySelector(
            capability_ids=["openmeteo_weather_forecast"],
            concepts=["environmental"],
        ),
        scope=OverlayScope(
            kind="location",
            location={"label": "Zurich", "latitude": 47.37, "longitude": 8.54},
        ),
        state_reference=OverlayStateReference(revision=1),
    )

    updated, results = AgentTurnStateAssembler.apply_overlay_commands(
        fetched,
        [command],
        state_session=active,
    )

    assert updated.overlay_collection.revision == 2
    assert len(updated.overlay_collection.instances) == 1
    assert results[0].added_instance_ids == [
        updated.overlay_collection.instances[0].instance_id
    ]

###############################################################################
def test_merge_replaces_only_the_authoritative_collection() -> None:
    weather = _instance(
        "weather-zurich",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Zurich",
        latitude=47.37,
        longitude=8.54,
    )
    session = MapSession(
        session_id="fetched",
        resolved_location=ResolvedLocation(
            label="Zurich", latitude=47.37, longitude=8.54
        ),
        basemap_id="osm_default",
        viewport=ViewportPolicy(center_latitude=47.37, center_longitude=8.54),
        overlay_collection=OverlayCollectionState(),
    )

    merged = OverlayCollectionService.merge_into_map_session(
        session,
        OverlayCollectionState(instances=[weather]),
    )

    assert merged.overlay_collection.instances == [weather]
    serialized = merged.model_dump(mode="json")
    assert "overlay_ids" not in serialized
    assert "overlays" not in serialized
    assert "failed_overlays" not in serialized


###############################################################################
def test_tool_map_session_is_merged_into_active_map_without_refetch() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9028,
        longitude=12.4964,
        country="Italy",
    )
    active_overlay = _instance(
        "weather-rome",
        "openmeteo_weather_forecast",
        label="Weather",
        scope_key="Rome",
        latitude=location.latitude,
        longitude=location.longitude,
    )
    active = MapSession(
        session_id="active",
        resolved_location=location,
        basemap_id="esri_world_imagery",
        basemap={"id": "esri_world_imagery", "label": "Satellite Imagery"},
        viewport=ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
        ),
        overlay_collection=OverlayCollectionState(instances=[active_overlay]),
    )
    fetched_overlay = _instance(
        "hydrography-rome",
        "census_tigerweb_hydrography",
        label="Hydrography",
        scope_key="Rome",
        latitude=location.latitude,
        longitude=location.longitude,
    )
    fetched = active.model_copy(
        update={
            "session_id": "fetched",
            "basemap_id": "osm_default",
            "basemap": {"id": "osm_default", "label": "OpenStreetMap"},
            "payload": {"source": "provider-tool"},
            "overlay_collection": OverlayCollectionState(instances=[fetched_overlay]),
        }
    )
    assembler = object.__new__(AgentTurnStateAssembler)
    contract = SimpleNamespace(
        location_signals=[],
        requested_basemap=None,
        overlay_commands=[],
    )

    merged = run_async_in_thread(
        assembler.build_combined_map_session_from_tool_results(
            tool_payload={
                "tool_results": [
                    {
                        "content": {
                            "ok": True,
                            "data": {"map_session": fetched.model_dump(mode="json")},
                        }
                    }
                ]
            },
            turn_contract=contract,
            latest_memory={"active_visualization": active.model_dump(mode="json")},
            resolved_location=location,
        )
    )

    assert isinstance(merged, MapSession)
    assert merged.payload == {"source": "provider-tool"}
    assert merged.resolved_location == location
    assert merged.basemap_id == "esri_world_imagery"
    assert merged.basemap == {"id": "esri_world_imagery", "label": "Satellite Imagery"}
    assert {
        instance.capability_id for instance in merged.overlay_collection.instances
    } == {
        "openmeteo_weather_forecast",
        "census_tigerweb_hydrography",
    }
    assert merged.overlay_collection.revision == 1


###############################################################################
def test_server_side_prepared_sessions_are_merged_without_reembedding_payload() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9028,
        longitude=12.4964,
        country="Italy",
    )
    overlay = _instance(
        "raster-rome",
        "rainviewer_precipitation_radar",
        label="Precipitation radar",
        scope_key="Rome",
        latitude=location.latitude,
        longitude=location.longitude,
    )
    prepared = MapSession(
        session_id="prepared-raster",
        resolved_location=location,
        basemap_id="osm_default",
        viewport=ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
        ),
        overlay_collection=OverlayCollectionState(instances=[overlay]),
    )
    prepared_second = prepared.model_copy(
        update={
            "overlay_collection": OverlayCollectionState(
                instances=[
                    overlay.model_copy(
                        update={
                            "instance_id": "vector-rome",
                            "capability_id": "openmeteo_weather_forecast",
                            "label": "Weather observations",
                            "overlay_type": "point",
                            "rendering_mode": "circle",
                        }
                    )
                ]
            )
        }
    )
    assembler = object.__new__(AgentTurnStateAssembler)

    merged = run_async_in_thread(
        assembler.build_combined_map_session_from_tool_results(
            tool_payload={"tool_results": []},
            turn_contract=SimpleNamespace(
                location_signals=[],
                requested_basemap=None,
                overlay_commands=[],
                relationship="new_task",
                operations=[],
            ),
            latest_memory={},
            resolved_location=location,
            prepared_map_sessions=[
                prepared.model_dump(mode="json"),
                prepared_second.model_dump(mode="json"),
            ],
        )
    )

    assert isinstance(merged, MapSession)
    assert {
        item.capability_id for item in merged.overlay_collection.instances
    } == {"rainviewer_precipitation_radar", "openmeteo_weather_forecast"}


###############################################################################
def test_multi_target_tool_sessions_preserve_scope_and_aggregate_bounds() -> None:
    paris = ResolvedLocation(
        label="Paris, France",
        latitude=48.8566,
        longitude=2.3522,
        country="France",
    )
    london = ResolvedLocation(
        label="London, United Kingdom",
        latitude=51.5074,
        longitude=-0.1278,
        country="United Kingdom",
    )
    paris_overlay = _instance(
        "earthquake-paris",
        "usgs_earthquakes",
        label="Earthquakes",
        scope_key="Paris",
        latitude=paris.latitude,
        longitude=paris.longitude,
    ).model_copy(update={"resolved_location": paris})
    london_overlay = _instance(
        "earthquake-london",
        "usgs_earthquakes",
        label="Earthquakes",
        scope_key="London",
        latitude=london.latitude,
        longitude=london.longitude,
    ).model_copy(update={"resolved_location": london})
    paris_session = MapSession(
        session_id="paris-session",
        resolved_location=paris,
        basemap_id="osm_default",
        viewport=ViewportPolicy(
            center_latitude=paris.latitude,
            center_longitude=paris.longitude,
            radius_m=20_000,
        ),
        bounds=[2.0, 48.5, 2.7, 49.1],
        overlay_collection=OverlayCollectionState(instances=[paris_overlay]),
    )
    london_session = paris_session.model_copy(
        update={
            "session_id": "london-session",
            "resolved_location": london,
            "viewport": ViewportPolicy(
                center_latitude=london.latitude,
                center_longitude=london.longitude,
                radius_m=20_000,
            ),
            "bounds": [-0.5, 51.2, 0.3, 51.8],
            "overlay_collection": OverlayCollectionState(instances=[london_overlay]),
        }
    )
    assembler = object.__new__(AgentTurnStateAssembler)
    contract = SimpleNamespace(
        location_signals=[],
        requested_basemap=None,
        overlay_commands=[],
        relationship="new_task",
        operations=["compare"],
    )

    merged = run_async_in_thread(
        assembler.build_combined_map_session_from_tool_results(
            tool_payload={
                "tool_results": [
                    {
                        "content": {
                            "ok": True,
                            "data": {"map_session": paris_session.model_dump(mode="json")},
                        }
                    },
                    {
                        "content": {
                            "ok": True,
                            "data": {"map_session": london_session.model_dump(mode="json")},
                        }
                    },
                ]
            },
            turn_contract=contract,
            latest_memory={},
            resolved_location=paris,
        )
    )

    assert isinstance(merged, MapSession)
    assert merged.bounds == [-0.5, 48.5, 2.7, 51.8]
    scoped = {
        instance.scope_key: instance.resolved_location.label
        for instance in merged.overlay_collection.instances
    }
    assert scoped == {"Paris": "Paris, France", "London": "London, United Kingdom"}


###############################################################################
def test_new_task_replaces_same_location_search_layers() -> None:
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    old = _instance(
        "old", "old_search", label="Old search", scope_key="Rome", latitude=41.9, longitude=12.5
    )
    new = _instance(
        "new", "new_search", label="New search", scope_key="Rome", latitude=41.9, longitude=12.5
    )
    active = MapSession(
        session_id="active",
        resolved_location=location,
        basemap_id="osm_default",
        viewport=ViewportPolicy(center_latitude=41.9, center_longitude=12.5),
        overlay_collection=OverlayCollectionState(instances=[old]),
    )
    candidate = active.model_copy(
        update={
            "session_id": "candidate",
            "overlay_collection": OverlayCollectionState(instances=[new]),
        }
    )
    assembler = object.__new__(AgentTurnStateAssembler)
    merged = run_async_in_thread(
        assembler.build_combined_map_session_from_tool_results(
            tool_payload={
                "tool_results": [
                    {"content": {"ok": True, "data": {"map_session": candidate.model_dump(mode="json")}}}
                ]
            },
            turn_contract=SimpleNamespace(
                location_signals=[],
                requested_basemap=None,
                overlay_commands=[],
                relationship="new_task",
                operations=[],
            ),
            latest_memory={"active_visualization": active.model_dump(mode="json")},
            resolved_location=location,
        )
    )

    assert isinstance(merged, MapSession)
    assert [instance.capability_id for instance in merged.overlay_collection.instances] == [
        "new_search"
    ]
