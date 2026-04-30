from __future__ import annotations

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.domain.extraction.models import NormalizedIntent
from server.services.search.request_builder import RequestBuilder


def test_request_builder_uses_wide_radius_for_city_level_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Berlin", latitude=52.5173885, longitude=13.3951309),
        NormalizedIntent(
            intent_id="show_city_map_berlin",
            intent_label="Show city map Berlin",
            task_tags=["map", "city", "wide_view"],
            intent_tags=["city_level"],
        ),
    )

    assert viewport.radius_m == 25000.0


def test_request_builder_uses_tighter_radius_for_exact_address_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="1600 Pennsylvania Avenue", latitude=38.8976387, longitude=-77.0365528),
        NormalizedIntent(
            intent_id="show_exact_address_map",
            intent_label="Show exact address map",
            task_tags=["map", "address"],
            intent_tags=["exact_address"],
        ),
    )

    assert viewport.radius_m == 1000.0


def test_request_builder_plan_path_preserves_city_scale_hint() -> None:
    request = RequestBuilder().build_location_search_request(
        ExecutionPlan(
            state="map_search",
            mode="map",
            intent_id="show_city_map_berlin",
            basemap_id="osm_default",
            overlay_ids=[],
        ),
        ResolvedLocation(label="Berlin", latitude=52.5173885, longitude=13.3951309),
    )

    assert request.viewport.radius_m == 25000.0
