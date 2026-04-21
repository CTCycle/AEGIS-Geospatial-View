from __future__ import annotations

from AEGIS.server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from AEGIS.server.services.search.request_builder import RequestBuilder


def test_request_builder_constructs_location_request() -> None:
    builder = RequestBuilder()
    plan = ExecutionPlan(state="map_search", intent_id="weather", overlay_ids=["openmeteo_weather_forecast"])
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    request = builder.build_location_search_request(plan, location)
    assert request.basemap_id
    assert request.overlay_ids == ["openmeteo_weather_forecast"]
