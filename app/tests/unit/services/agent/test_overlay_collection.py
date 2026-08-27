from __future__ import annotations

from server.contracts.extraction import (
    OverlayCommand,
    OverlaySelector,
    OverlayScope,
    OverlayStateReference,
)
from server.contracts.geospatial import OverlayCollectionState, OverlayInstance
from server.services.agent.overlay_collection import OverlayCollectionService


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
