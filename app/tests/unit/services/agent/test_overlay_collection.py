from __future__ import annotations

from server.contracts.extraction import (
    OverlayCommand,
    OverlaySelector,
    OverlayScope,
    OverlayStateReference,
)
from server.contracts.geospatial import MapSession, OverlayCollectionState, OverlayInstance, ViewportPolicy
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler


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


def test_identity_resolution_falls_through_unmatched_instance_alias_to_capability() -> None:
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


def test_keep_only_removes_nonmatching_instances() -> None:
    collection = OverlayCollectionState(
        instances=[
            _instance("weather", "openmeteo_weather_forecast", label="Weather", scope_key="global", latitude=0, longitude=0),
            _instance("traffic", "tomtom_traffic_flow", label="Traffic", scope_key="global", latitude=0, longitude=0),
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


def test_add_reuses_same_capability_and_scope_identity() -> None:
    collection = OverlayCollectionState()
    command = OverlayCommand(
        action="add",
        selector=OverlaySelector(capability_ids=["openmeteo_weather_forecast"]),
        scope=OverlayScope(kind="location", location={"label": "Zurich", "latitude": 47.37, "longitude": 8.54}),
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

    first, first_result = OverlayCollectionService.apply(collection, command, catalog=catalog)
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

    updated, result = OverlayCollectionService.apply(collection=OverlayCollectionState(), command=command, catalog=catalog)

    assert result.added_instance_ids == [updated.instances[0].instance_id]
    assert updated.instances[0].capability_id == "weather-official"
    assert updated.instances[0].descriptor["tags"] == ["forecast"]


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


def test_unmatched_selector_that_targets_active_basemap_is_explained_without_mutation() -> None:
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
    still_unchanged, no_match_result = OverlayCollectionService.apply(unchanged, no_match)
    assert still_unchanged == unchanged
    assert no_match_result.unmatched_selectors == ["missing"]


def test_provider_candidate_is_committed_against_active_revision_without_dropping_state() -> None:
    location = ResolvedLocation(label="Zurich", latitude=47.37, longitude=8.54, country="Switzerland")
    viewport = ViewportPolicy(center_latitude=47.37, center_longitude=8.54)
    active = MapSession(
        session_id="active",
        resolved_location=location,
        basemap_id="osm_default",
        viewport=viewport,
        overlay_collection=OverlayCollectionState(revision=1),
        overlay_collection_revision=1,
    )
    fetched = active.model_copy(
        update={
            "session_id": "fetched",
            "overlays": [
                {
                    "id": "catalog-weather",
                    "capability_id": "openmeteo_weather_forecast",
                    "label": "Weather",
                    "provider": "openmeteo",
                    "type": "raster",
                    "rendering_mode": "metadata-only",
                }
            ],
        }
    )
    command = OverlayCommand(
        action="show",
        selector=OverlaySelector(capability_ids=["openmeteo_weather_forecast"]),
        scope=OverlayScope(kind="location", location={"label": "Zurich", "latitude": 47.37, "longitude": 8.54}),
        state_reference=OverlayStateReference(revision=1),
    )

    updated, results = AgentTurnStateAssembler.apply_overlay_commands(
        fetched,
        [command],
        state_session=active,
    )

    assert updated.overlay_collection_revision == 2
    assert len(updated.overlay_collection.instances) == 1
    assert results[0].added_instance_ids == [updated.overlay_collection.instances[0].instance_id]
