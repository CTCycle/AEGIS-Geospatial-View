from __future__ import annotations

import asyncio
import inspect

from AEGIS.server.domain.geographics import LocationSearchRequest, SearchByLocationResponse
from AEGIS.server.domain.agent.decision import ResolvedLocation
from AEGIS.server.domain.jobs import JobStartResponse
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.search.composition import build_search_runtime


def test_location_search_request_is_the_only_input_contract() -> None:
    signature_search = inspect.signature(
        build_search_runtime().search_execution.search_by_location
    )
    signature_job = inspect.signature(
        build_search_runtime().search_execution.start_search_job
    )
    assert signature_search.parameters["payload"].annotation in {
        LocationSearchRequest,
        "LocationSearchRequest",
    }
    assert signature_job.parameters["payload"].annotation in {
        LocationSearchRequest,
        "LocationSearchRequest",
    }


def test_image_dimensions_survive_normalization() -> None:
    runtime = build_search_runtime()
    payload = LocationSearchRequest(
        datetime="2024-06-15T12:00:00",
        use_coordinates=True,
        latitude=41.9,
        longitude=12.5,
        image_width=1536,
        image_height=1024,
    )
    typed_payload, _, payload_data = asyncio.run(
        runtime.search_execution._prepare_request(payload)
    )
    assert typed_payload.image_width == 1536
    assert typed_payload.image_height == 1024
    assert payload_data["image_width"] == 1536
    assert payload_data["image_height"] == 1024


def test_search_and_job_paths_share_normalized_payload(monkeypatch) -> None:
    runtime = build_search_runtime()
    service = runtime.search_execution
    calls = {"count": 0}

    async def _prepare(payload: LocationSearchRequest):  # noqa: ANN202
        calls["count"] += 1
        return payload, {"country": payload.country}, payload.model_dump(mode="python")

    async def _process(_: LocationSearchRequest) -> dict[str, object]:
        return {
            "status_message": "Map search request submitted.",
            "payload": {},
            "map_session": {},
            "compliance_warnings": [],
        }

    async def _record(**kwargs) -> None:  # noqa: ANN003, ARG001
        return None

    monkeypatch.setattr(service, "_prepare_request", _prepare)
    monkeypatch.setattr(service, "process_location_search", _process)
    monkeypatch.setattr(service, "record_search_session", _record)
    monkeypatch.setattr(service.job_manager, "start_job", lambda **kwargs: "job-123")
    monkeypatch.setattr(
        service.job_manager,
        "get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "job_type": "map_search",
            "status": "running",
            "progress": 1.0,
            "result": None,
            "error": None,
        },
    )

    payload = LocationSearchRequest(
        datetime="2024-06-15T12:00:00",
        use_coordinates=True,
        latitude=41.9,
        longitude=12.5,
    )
    response = asyncio.run(service.search_by_location(payload))
    started = asyncio.run(service.start_search_job(payload))
    assert isinstance(response, SearchByLocationResponse)
    assert isinstance(started, JobStartResponse)
    assert calls["count"] == 2


def test_location_search_orchestrator_includes_render_descriptors(monkeypatch) -> None:
    monkeypatch.setattr(
        LocationSearchOrchestrator,
        "_resolve_rainviewer_tile_url",
        staticmethod(
            lambda: "https://tilecache.rainviewer.com/v2/radar/123/256/{z}/{x}/{y}/2/1_1.png"
        ),
    )
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Tokyo",
            latitude=35.6768601,
            longitude=139.7638947,
        ),
        intent_id="show_precipitation_radar",
        time_mode="current",
        basemap_id="osm_dark",
        overlay_ids=["rainviewer_precipitation_radar"],
        viewport={
            "center_latitude": 35.6768601,
            "center_longitude": 139.7638947,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": True,
            "high_contrast": True,
            "show_legend": True,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert session.center == {
        "latitude": 35.6768601,
        "longitude": 139.7638947,
    }
    assert session.basemap is not None
    assert session.basemap["id"] == "osm_dark"
    assert session.basemap["label"] == "Dark Basemap"
    assert session.overlays[0]["id"] == "rainviewer_precipitation_radar"
    assert "{time}" not in str(session.overlays[0]["url"])
    assert str(session.overlays[0]["url"]).startswith(
        "https://tilecache.rainviewer.com/v2/radar/"
    )
    assert session.overlays[0]["maxzoom"] == 10
    assert session.compliance_warnings == []


def test_location_search_orchestrator_warns_on_rainviewer_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        LocationSearchOrchestrator,
        "_resolve_rainviewer_tile_url",
        staticmethod(lambda: None),
    )
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Tokyo",
            latitude=35.6768601,
            longitude=139.7638947,
        ),
        intent_id="show_precipitation_radar",
        time_mode="current",
        basemap_id="osm_dark",
        overlay_ids=["rainviewer_precipitation_radar"],
        viewport={
            "center_latitude": 35.6768601,
            "center_longitude": 139.7638947,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": True,
            "high_contrast": True,
            "show_legend": True,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert "{time}" not in str(session.overlays[0]["url"])
    assert session.compliance_warnings == [
        "rainviewer_precipitation_radar: RainViewer metadata could not be fetched; using a timestamp fallback."
    ]
