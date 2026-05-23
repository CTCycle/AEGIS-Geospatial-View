from __future__ import annotations

import asyncio
import inspect

from server.domain.geographics import LocationSearchRequest, SearchByLocationResponse
from server.domain.agent.decision import ResolvedLocation
from server.domain.jobs import JobStartResponse
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.composition import build_search_runtime


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


def _location_request() -> LocationSearchRequest:
    return LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Rome",
            latitude=41.9,
            longitude=12.5,
        ),
        action_id="show_map",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=[],
        viewport={
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": False,
            "high_contrast": False,
            "show_legend": False,
        },
    )


def test_search_and_job_paths_share_normalized_payload(monkeypatch) -> None:
    runtime = build_search_runtime()
    service = runtime.search_execution
    calls: list[LocationSearchRequest] = []
    job_kwargs: dict[str, object] = {}

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
            "center": {
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            "bounds": None,
            "basemap": None,
            "overlays": [],
            "compliance_warnings": [],
        }

    def _start_job(**kwargs) -> str:  # noqa: ANN003
        job_kwargs.update(kwargs)
        return "job-123"

    monkeypatch.setattr(service.orchestrator, "execute", _execute)
    monkeypatch.setattr(service.job_manager, "start_job", _start_job)
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

    payload = _location_request()
    response = asyncio.run(service.search_by_location(payload))
    started = asyncio.run(service.start_search_job(payload))
    assert isinstance(response, SearchByLocationResponse)
    assert isinstance(started, JobStartResponse)
    assert calls == [payload]
    assert job_kwargs["kwargs"] == {"service": service, "job_payload": payload}


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
        action_id="show_precipitation_radar",
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
    assert session.bounds is not None
    assert len(session.bounds) == 4


def test_location_search_orchestrator_derives_bounds_from_viewport_radius() -> None:
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Berlin",
            latitude=52.5173885,
            longitude=13.3951309,
        ),
        action_id="show_city_map_berlin",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=[],
        viewport={
            "center_latitude": 52.5173885,
            "center_longitude": 13.3951309,
            "radius_m": 25000.0,
        },
        presentation={
            "emphasize_overlays": False,
            "high_contrast": False,
            "show_legend": False,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert session.bounds is not None
    min_lon, min_lat, max_lon, max_lat = session.bounds
    assert min_lon < 13.3951309 < max_lon
    assert min_lat < 52.5173885 < max_lat
    assert max_lat - min_lat > 0.4


def test_location_search_orchestrator_uses_point_insight_for_direct_text_overlay_without_tiles() -> None:
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Naples",
            latitude=40.8358846,
            longitude=14.2487679,
        ),
        action_id="weather_forecast_rain_radar",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=["openmeteo_weather_forecast"],
        viewport={
            "center_latitude": 40.8358846,
            "center_longitude": 14.2487679,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": True,
            "high_contrast": True,
            "show_legend": True,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert {
        "source_protocol": None,
        "data_format": None,
        "geometry_type": None,
        **session.overlays[0],
    } == {
        "id": "openmeteo_weather_forecast",
        "label": "Open-Meteo Weather Forecast",
        "provider": "openmeteo",
        "type": "point-insight",
        "rendering_mode": "metadata-only",
        "attribution": "© Open-Meteo",
        "default_opacity": 0.72,
        "source_protocol": "JSON time series",
        "data_format": "JSON",
        "geometry_type": "regional/time-series",
    }
    assert session.compliance_warnings == []


def test_location_search_orchestrator_adds_bbox_to_live_feature_endpoints() -> None:
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Rome",
            latitude=41.9,
            longitude=12.5,
        ),
        action_id="air_quality_nearby",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=["openaq_air_quality", "windy_webcams"],
        viewport={
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": True,
            "high_contrast": False,
            "show_legend": True,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    openaq = next(overlay for overlay in session.overlays if overlay["id"] == "openaq_air_quality")
    webcams = next(overlay for overlay in session.overlays if overlay["id"] == "windy_webcams")
    assert str(openaq["url"]).startswith("/api/geospatial/layers/openaq_air_quality/features?")
    assert "live=true" in str(openaq["url"])
    assert "bbox=" in str(openaq["url"])
    assert str(webcams["url"]).startswith("/api/geospatial/cameras?")
    assert "provider=windy_webcams" in str(webcams["url"])
    assert "bbox=" in str(webcams["url"])
    assert any("WINDY_WEBCAMS_API_KEY" in warning for warning in session.compliance_warnings)


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
        action_id="show_precipitation_radar",
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


def test_location_search_orchestrator_resolves_provider_tile_templates(monkeypatch) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-test-key")
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Times Square",
            latitude=40.7570095,
            longitude=-73.9859724,
        ),
        action_id="show_current_traffic_flow",
        time_mode="current",
        basemap_id="tomtom_basic",
        overlay_ids=["tomtom_traffic_flow"],
        viewport={
            "center_latitude": 40.7570095,
            "center_longitude": -73.9859724,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": True,
            "high_contrast": True,
            "show_legend": True,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert session.basemap is not None
    assert session.basemap_id == "tomtom_basic"
    assert session.basemap["id"] == "tomtom_basic"
    assert "tomtom-test-key" in str(session.basemap["tile_url"])
    assert session.overlays[0]["id"] == "tomtom_traffic_flow"
    assert "tomtom-test-key" in str(session.overlays[0]["url"])
    assert session.compliance_warnings == []


def test_location_search_orchestrator_warns_and_falls_back_for_missing_basemap_key(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    orchestrator = LocationSearchOrchestrator()
    payload = LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Times Square",
            latitude=40.7570095,
            longitude=-73.9859724,
        ),
        action_id="show_current_traffic_flow",
        time_mode="current",
        basemap_id="tomtom_basic",
        overlay_ids=[],
        viewport={
            "center_latitude": 40.7570095,
            "center_longitude": -73.9859724,
            "radius_m": 2500.0,
        },
        presentation={
            "emphasize_overlays": False,
            "high_contrast": False,
            "show_legend": False,
        },
    )

    session = asyncio.run(orchestrator.execute(payload))

    assert session.basemap is not None
    assert session.basemap_id == "osm_default"
    assert session.basemap["id"] == "osm_default"
    assert session.compliance_warnings == [
        "tomtom_basic: provider API key is required; falling back to osm_default."
    ]
