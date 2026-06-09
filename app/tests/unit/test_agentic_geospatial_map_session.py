from __future__ import annotations

import asyncio
import json
import threading
from typing import TypeVar

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

T = TypeVar("T")


def _run_async(awaitable) -> T:  # type: ignore[no-untyped-def]
    result: dict[str, T] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=_runner, name="test-async-runner")
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result["value"]


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

    session = _run_async(LocationSearchOrchestrator().execute(request))

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

    session = _run_async(LocationSearchOrchestrator().execute(request))

    assert session.basemap_id == "osm_default"
    assert any("provider API key is required" in item for item in session.compliance_warnings)


def test_agentic_geospatial_map_session_never_serializes_provider_api_keys(monkeypatch) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-secret-forbidden")
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
        overlay_ids=["tomtom_traffic_flow"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))

    serialized = json.dumps(session.model_dump(mode="json"))
    assert "tomtom-secret-forbidden" not in serialized
    assert "api_key=" not in serialized
    assert "/api/geospatial/tiles/tomtom_traffic_flow/" in serialized


def test_agentic_geospatial_wms_and_wmts_descriptors_include_backend_render_templates() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="thematic_layers",
        basemap_id="osm_default",
        overlay_ids=["eea_noise_2019", "esa_worldcover"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))
    overlays = {overlay["id"]: overlay for overlay in session.overlays}

    eea = overlays["eea_noise_2019"]
    esa = overlays["esa_worldcover"]

    assert eea["rendering_mode"] == "wms"
    assert "service=WMS" in eea["tile_url_template"]
    assert "request=GetMap" in eea["tile_url_template"]
    assert "version=1.1.1" in eea["tile_url_template"]
    assert "bbox={bbox-epsg-3857}" in eea["tile_url_template"]

    assert esa["rendering_mode"] == "wmts"
    assert "service=WMTS" in esa["tile_url_template"]
    assert "request=GetTile" in esa["tile_url_template"]
    assert "tilematrixset=EPSG:3857" in esa["tile_url_template"]
    assert "tilematrix=EPSG:3857:{z}" in esa["tile_url_template"]


def test_agentic_geospatial_metadata_only_descriptors_stay_non_renderable() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="regional_demographics",
        basemap_id="osm_default",
        overlay_ids=["eurostat_regional_demographics"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))
    overlay = session.overlays[0]

    assert overlay["id"] == "eurostat_regional_demographics"
    assert overlay["rendering_mode"] == "metadata-only"
    assert overlay["type"] == "time-series-insight"
    assert "tile_url_template" not in overlay
