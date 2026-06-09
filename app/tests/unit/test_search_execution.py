from __future__ import annotations

import asyncio
import inspect

from server.domain.agent.decision import ResolvedLocation
from server.domain.geographics import LocationSearchRequest, SearchByLocationResponse
from server.services.search.composition import build_search_runtime


def _location_request() -> LocationSearchRequest:
    return LocationSearchRequest(
        resolved_location=ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5),
        action_id="show_map",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=[],
        viewport={"center_latitude": 41.9, "center_longitude": 12.5, "radius_m": 2500.0},
        presentation={"emphasize_overlays": False, "high_contrast": False, "show_legend": False},
    )


def test_location_search_request_is_the_only_input_contract() -> None:
    signature_search = inspect.signature(build_search_runtime().search_execution.search_by_location)
    assert signature_search.parameters["payload"].annotation in {
        LocationSearchRequest,
        "LocationSearchRequest",
    }


def test_search_by_location_returns_response(monkeypatch) -> None:
    runtime = build_search_runtime()
    service = runtime.search_execution
    calls: list[LocationSearchRequest] = []

    async def _execute(payload: LocationSearchRequest):
        calls.append(payload)
        return {
            "session_id": "map-test",
            "resolved_location": payload.resolved_location.model_dump(mode="json"),
            "basemap_id": payload.basemap_id,
            "overlay_ids": payload.overlay_ids,
            "viewport": payload.viewport.model_dump(mode="json"),
            "generated_at": "2026-04-24T00:00:00Z",
            "payload": {},
            "center": {"latitude": payload.viewport.center_latitude, "longitude": payload.viewport.center_longitude},
            "bounds": None,
            "basemap": None,
            "overlays": [],
            "compliance_warnings": [],
        }

    monkeypatch.setattr(service.orchestrator, "execute", _execute)

    response = asyncio.run(service.search_by_location(_location_request()))

    assert isinstance(response, SearchByLocationResponse)
    assert calls and calls[0].resolved_location.label == "Rome"
