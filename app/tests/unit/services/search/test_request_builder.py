from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.contracts.extraction import NormalizedAction, ViewportIntent
from server.services.search.request_builder import RequestBuilder

###############################################################################
def test_request_builder_uses_wide_radius_for_city_level_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Berlin", latitude=52.5173885, longitude=13.3951309),
        NormalizedAction(
            action_id="show_city_map_berlin",
            action_label="Show city map Berlin",
            task_tags=["map", "city", "wide_view"],
            action_tags=["city_level"],
        ),
    )

    assert viewport.radius_m == 18000.0

###############################################################################
def test_request_builder_uses_tighter_radius_for_exact_address_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="1600 Pennsylvania Avenue",
            latitude=38.8976387,
            longitude=-77.0365528,
            location_type="house",
            location_class="building",
            bbox=[-77.0370, 38.8972, -77.0362, 38.8980],
        ),
        NormalizedAction(
            action_id="show_exact_address_map",
            action_label="Show exact address map",
            task_tags=["map", "address"],
            action_tags=["exact_address"],
        ),
    )

    assert viewport.radius_m <= 350.0
    assert viewport.bbox is not None

###############################################################################
def test_request_builder_prefers_explicit_viewport_intent_over_generic_defaults() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(scope="street", reason="local_area_request"),
    )

    assert viewport.radius_m == 350.0

###############################################################################
def test_request_builder_tightens_relative_to_active_viewport() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(
            scope="street",
            tighten_relative_to_active=True,
            reason="explicit_tighter_view",
        ),
        active_visualization={
            "viewport": {
                "center_latitude": 44.4056,
                "center_longitude": 8.9463,
                "radius_m": 2500.0,
            }
        },
    )

    assert viewport.radius_m < 2500.0
    assert viewport.radius_m <= 875.0

###############################################################################
def test_request_builder_uses_geocoder_bbox_when_parser_intent_is_absent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="Via Pisa, Genoa",
            latitude=44.4056,
            longitude=8.9463,
            location_type="road",
            location_class="highway",
            bbox=[8.9448, 44.4049, 8.9474, 44.4061],
        ),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
    )

    assert viewport.bbox is not None
    assert viewport.radius_m <= 400.0

###############################################################################
def test_request_builder_preserves_current_viewport_for_basemap_only_follow_up() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(scope="preserve_current", reason="basemap_only_follow_up"),
        active_visualization={
            "viewport": {
                "center_latitude": 44.4056,
                "center_longitude": 8.9463,
                "radius_m": 640.0,
                "bbox": [8.94, 44.40, 8.95, 44.41],
            }
        },
    )

    assert viewport.radius_m == 640.0
    assert viewport.bbox == [8.94, 44.4, 8.95, 44.41]

###############################################################################
def test_request_builder_recenters_when_follow_up_changes_location() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="Zurich",
            latitude=47.3769,
            longitude=8.5417,
            location_type="city",
        ),
        NormalizedAction(
            action_id="map_search",
            action_label="Change map location",
            task_tags=["map"],
            action_tags=["correction"],
        ),
        viewport_intent=ViewportIntent(scope="preserve_current", reason="location_correction"),
        active_visualization={
            "resolved_location": {
                "label": "Lugano",
                "latitude": 46.0037,
                "longitude": 8.9511,
            },
            "viewport": {
                "center_latitude": 46.0037,
                "center_longitude": 8.9511,
                "radius_m": 350.0,
            },
        },
    )

    assert viewport.center_latitude == 47.3769
    assert viewport.center_longitude == 8.5417
    assert viewport.radius_m == 18000.0


