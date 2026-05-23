from __future__ import annotations

import asyncio

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder


def test_agentic_geospatial_selected_capabilities_flow_into_map_session() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="osm_default",
        overlay_ids=["tomtom_traffic_flow", "windy_webcams"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = asyncio.run(LocationSearchOrchestrator().execute(request))

    assert session.overlay_ids == ["tomtom_traffic_flow", "windy_webcams"]
    assert [overlay["id"] for overlay in session.overlays] == [
        "tomtom_traffic_flow",
        "windy_webcams",
    ]
    assert session.center == {"latitude": 41.9, "longitude": 12.5}


def test_agentic_geospatial_map_session_keeps_credential_warnings() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="tomtom_basic",
        overlay_ids=["tomtom_traffic_flow"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = asyncio.run(LocationSearchOrchestrator().execute(request))

    assert session.basemap_id == "osm_default"
    assert any("provider API key is required" in item for item in session.compliance_warnings)
