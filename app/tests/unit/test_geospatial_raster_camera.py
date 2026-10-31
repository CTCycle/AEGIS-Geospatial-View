from __future__ import annotations
from tests.conftest import run_async_in_thread
from server.services.geospatial.providers.base import ProviderRequest, ProviderAuthError, ProviderUnavailableError
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.providers.tomtom import TomTomProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers._request import grid_points
from server.services.geospatial.openmeteo import OpenMeteoRateLimitError, OpenMeteoRequestError, OpenMeteoService
from server.services.geospatial.land_mask import country_shapes, land_mask
from server.services.catalog.loader import find_macro_region_entry, load_macro_regions
from shapely.geometry import Point
from urllib.parse import urlencode
from unittest.mock import patch
import pytest
import json
import threading
import time
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider
from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.rainviewer import RainViewerRequestError, RainViewerService
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider

# --- test_geospatial_raster_and_secret_providers.py ---



###############################################################################
def test_rainviewer_provider_emits_renderable_raster_payload() -> None:
    rainviewer = run_async_in_thread(
        RainViewerProvider().fetch(
            ProviderRequest(capability_id="rainviewer_precipitation_radar")
        )
    )

    assert rainviewer.payload["renderingMode"] == "raster-tile"
    assert rainviewer.attribution

###############################################################################
def test_tomtom_traffic_flow_keeps_key_server_side() -> None:
    response = run_async_in_thread(
        TomTomProvider(api_key="tomtom-secret").fetch(
            ProviderRequest(capability_id="tomtom_traffic_flow")
        )
    )

    assert response.payload["credentialPolicy"] == "server-side-only"
    assert "tomtom-secret" not in str(response.payload)

# --- test_geospatial_weather_sampling.py ---



###############################################################################
class _OpenMeteoService:

    # -------------------------------------------------------------------------
    async def get_weather_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "current": {
                "wind_speed_10m": 7,
                "wind_direction_10m": 270,
                "surface_pressure": 1008,
                "relative_humidity_2m": 55,
            },
            "hourly_preview": [],
            "attribution": "Data from Open-Meteo",
        }

    # -------------------------------------------------------------------------
    async def get_air_quality_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "hourly_preview": [{"pm2_5": 8, "pm10": 12}],
            "attribution": "Data from Open-Meteo",
        }

###############################################################################
def test_openmeteo_wind_sampling_emits_arrow_metadata() -> None:
    response = run_async_in_thread(
        OpenMeteoProvider(service=_OpenMeteoService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="openmeteo_pressure_humidity_wind",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    feature = response.payload["features"][0]
    assert response.payload["renderingMode"] == "clustered-points"
    assert feature["metadata"]["windArrow"] == {"speed": 7, "direction": 270}


###############################################################################
@pytest.mark.parametrize("bbox", [(-180, -85, 180, 85), (-25, 34, 45, 72), (8, 45, 8.1, 70)])
def test_weather_grid_cap_and_interior_centres(bbox):
    points, spacing, excluded = grid_points(bbox)
    assert 1 <= len(points) <= 100 and spacing > 0 and excluded == 0
    assert all(bbox[0] < lon < bbox[2] and bbox[1] < lat < bbox[3] for lat, lon in points)


###############################################################################
def test_region_mask_excludes_sea_and_non_member_land():
    europe = find_macro_region_entry("Europe")
    assert europe is not None
    mask = land_mask(europe.bbox, europe.countries)
    inside = {name: mask.contains(Point(lon, lat)) for name, (lon, lat) in {
        "Lisbon": (-9.14, 38.72), "Warsaw": (21.01, 52.23), "Rabat": (-6.84, 34.02),
        "Ankara": (32.85, 39.93), "Tunis": (10.18, 36.8), "Bay of Biscay": (-5.0, 45.5)}.items()}
    assert inside == {"Lisbon": True, "Warsaw": True, "Rabat": False, "Ankara": False, "Tunis": False, "Bay of Biscay": False}
    points, spacing, excluded = grid_points(europe.bbox, 300, mask)
    assert 255 <= len(points) <= 300 and excluded > 0 and spacing < 3
    assert all(mask.contains(Point(lon, lat)) for lat, lon in points)


###############################################################################
def test_macro_region_members_have_shapes():
    shapes = country_shapes()
    assert all(code in shapes for region in load_macro_regions() for code in region.countries)


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_region_refinement_future_hours_and_provenance():
    requested: list[list[tuple[float, float]]] = []

    ###############################################################################
    class Service:
        weather_base_url = "https://api.open-meteo.com/v1/forecast"

        # -------------------------------------------------------------------------
        async def get_weather_grid(self, points, past_days):
            requested.append(points)
            row = {"elevation": 0, "current": {"time": "2026-10-20T12:00", "temperature_2m": 30},
                   "hourly": {"time": ["2026-10-20T11:00", "2026-10-20T12:00", "2026-10-20T13:00"],
                              "temperature_2m": [28, 30, 99], "precipitation": [2, 3, 100]}}
            return [{**row, "current": {}}] + [row for _ in points[1:]]
    europe = find_macro_region_entry("Europe")
    assert europe is not None
    result = await OpenMeteoProvider(service=Service()).fetch(ProviderRequest(
        capability_id="openmeteo_weather_forecast", bbox=europe.bbox,
        params={"sampling": "area", "macro_region": "Europe"}))
    features = result.payload["features"]
    mask = land_mask(europe.bbox, europe.countries)
    # Elevation zero is no longer treated as sea; the region mask decides.
    assert all(mask.contains(Point(lon, lat)) for batch in requested for lat, lon in batch)
    assert features[0]["precipitation_sum_mm"] == 5 and features[0]["temperature_2m_max_c"] == 30
    assert len(requested) == 2 and 0 < len(requested[1]) <= 80
    assert {f["sample_stage"] for f in features} == {"coarse", "refined"}
    assert result.coverage["region"] == "Europe" and result.coverage["excluded_outside_region_points"] > 0
    assert result.coverage["refined_point_count"] == len(requested[1]) - 1
    assert result.coverage["value_kind"] == "model_estimate"
    assert result.result_status == "partial"
    assert result.units["precipitation_sum_mm"] == "mm"


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_batches_requests_under_8kb():
    service = OpenMeteoService()
    calls = []
    def get_json(**kwargs):
        calls.append(kwargs)
        return {"locations": [{"elevation": 10}] * len(kwargs["params"]["latitude"].split(","))}
    with patch.object(service, "_get_json", side_effect=get_json):
        points, _, _ = grid_points((-180, -85, 180, 85), 300, land_mask((-180, -85, 180, 85)))
        result = await service.get_weather_grid(points, 30)
    assert len(result) == len(points) and len(calls) == 3
    assert all(call["params"]["past_days"] == "14" for call in calls)
    assert all(len(call["endpoint"] + "?" + urlencode(call["params"])) < 8192 for call in calls)

###############################################################################
def _grid_sample(latitude: float, *, stamp: str = "2026-10-20T12:00") -> dict:
    return {"latitude": latitude, "current": {"time": "2026-10-20T12:00", "temperature_2m": 20},
            "hourly": {"time": [stamp], "temperature_2m": [20], "precipitation": [latitude]}}


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_keeps_points_aligned_when_a_batch_is_short_or_fails():
    points = [(float(index), 0.0) for index in range(250)]
    def get_json(**kwargs):
        latitudes = [float(value) for value in kwargs["params"]["latitude"].split(",")]
        if latitudes[0] == 100.0:
            # Short middle batch: positional alignment would shift samples.
            return {"locations": [_grid_sample(latitude) for latitude in latitudes[1:]]}
        if latitudes[0] == 200.0:
            raise OpenMeteoRequestError("boom")
        return {"locations": [_grid_sample(latitude) for latitude in latitudes]}
    service = OpenMeteoService(grid_batch_concurrency=3)
    with patch.object(service, "_get_json", side_effect=get_json):
        samples = await service.get_weather_grid(points, 0)
    assert len(samples) == len(points)
    assert all(samples[i] is not None and samples[i]["latitude"] == points[i][0] for i in range(100))
    assert all(sample is None for sample in samples[100:])
    with patch.object(service, "_get_json", side_effect=OpenMeteoRequestError("down")):
        with pytest.raises(OpenMeteoRequestError):
            await service.get_weather_grid(points, 0)


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_bounds_concurrency_and_stops_on_rate_limit():
    in_flight = max_in_flight = 0
    lock = threading.Lock()
    def get_json(**kwargs):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return {"locations": [{}] * len(kwargs["params"]["latitude"].split(","))}
    points = [(float(index), 0.0) for index in range(400)]
    service = OpenMeteoService(grid_batch_concurrency=2)
    with patch.object(service, "_get_json", side_effect=get_json):
        assert len(await service.get_weather_grid(points, 0)) == 400
    assert max_in_flight == 2
    calls = []
    def rate_limited(**kwargs):
        calls.append(kwargs)
        raise OpenMeteoRateLimitError("slow down", retry_after_seconds=30)
    service = OpenMeteoService(grid_batch_concurrency=1)
    with patch.object(service, "_get_json", side_effect=rate_limited):
        with pytest.raises(OpenMeteoRateLimitError):
            await service.get_weather_grid(points, 0)
    assert len(calls) == 1


###############################################################################
def test_openmeteo_rate_slots_are_reserved_atomically():
    service = OpenMeteoService(min_call_interval_s=0.1)
    sleeps: list[float] = []
    with patch("server.services.geospatial.openmeteo.time.monotonic", return_value=50.0),             patch("server.services.geospatial.openmeteo.time.sleep", side_effect=sleeps.append):
        for _ in range(3):
            service._wait_for_rate_limit_slot("grid")
    assert sleeps == pytest.approx([0.1, 0.2])


###############################################################################
class _GridService:
    weather_base_url = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, coarse, refined):
        self.stages = [coarse, refined]

    async def get_weather_grid(self, points, past_days):
        stage = self.stages.pop(0)
        if isinstance(stage, Exception):
            raise stage
        return stage(points)


###############################################################################
def _grid_request() -> ProviderRequest:
    return ProviderRequest(capability_id="openmeteo_weather_forecast", bbox=(8.0, 45.0, 10.0, 47.0),
                           params={"sampling": "area"})


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_counts_every_missing_sample_across_both_stages():
    def coarse(points):
        samples = [_grid_sample(lat) for lat, _ in points]
        samples[1] = None
        samples[2] = _grid_sample(points[2][0], stamp="not-a-time")
        return samples
    result = await OpenMeteoProvider(service=_GridService(coarse, OpenMeteoRequestError("x"))).fetch(_grid_request())
    coverage = result.coverage
    assert result.result_status == "partial" and result.partial
    assert coverage["refinement_requested_point_count"] > 0 and coverage["refined_point_count"] == 0
    assert coverage["point_count"] + coverage["missing_point_count"] == (
        coverage["requested_point_count"] + coverage["refinement_requested_point_count"])
    # Each feature keeps the coordinates of the point it was sampled for.
    assert all(f["precipitation_sum_mm"] == f["latitude"] for f in result.payload["features"])

    short = lambda points: [_grid_sample(lat) for lat, _ in points][1:]
    result = await OpenMeteoProvider(service=_GridService(
        lambda points: [_grid_sample(lat) for lat, _ in points], short)).fetch(_grid_request())
    assert result.result_status == "partial" and result.coverage["refined_point_count"] == 0
    assert result.coverage["missing_point_count"] == result.coverage["refinement_requested_point_count"]


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_without_usable_samples_is_a_failure_not_empty():
    unusable = lambda points: [_grid_sample(lat, stamp="bad") for lat, _ in points]
    with pytest.raises(ProviderUnavailableError):
        await OpenMeteoProvider(service=_GridService(unusable, unusable)).fetch(_grid_request())

# --- test_geospatial_webcam_provider.py ---




###############################################################################
def test_windy_webcam_provider_builds_bbox_camera_request() -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append((url, headers))
        return {"webcams": []}

    response = run_async_in_thread(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="windy_webcams",
                bbox=(7.0, 45.0, 7.5, 45.5),
                params={"live": True, "camera_type": "traffic"},
            )
        )
    )

    assert "bbox=45.5,7.5,45.0,7.0" in calls[0][0]
    assert "categories=traffic" in calls[0][0]
    assert calls[0][1] == {"x-windy-api-key": "windy-test"}
    assert response.payload["renderingMode"] == "camera-points"

###############################################################################
def test_windy_webcam_live_failure_after_descriptor_is_not_reported_stale() -> None:

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        raise RuntimeError("upstream failure")

    provider = WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher)
    request = ProviderRequest(capability_id="windy_webcams", bbox=(7.0, 45.0, 7.5, 45.5))
    run_async_in_thread(provider.fetch(request))

    with pytest.raises(RuntimeError):
        run_async_in_thread(
            provider.fetch(
                ProviderRequest(
                    capability_id="windy_webcams",
                    bbox=(7.0, 45.0, 7.5, 45.5),
                    params={"live": True},
                )
            )
        )

###############################################################################
def test_local_open_data_camera_template_fetches_configured_source() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "cameras": [
                {
                    "id": "dot-1",
                    "name": "Main Street",
                    "latitude": 41.9,
                    "longitude": 12.5,
                    "officialUrl": "https://agency.example/cameras/dot-1",
                }
            ]
        }

    response = run_async_in_thread(
        LocalOpenDataProvider(
            source_map={"dot_traffic_cameras": "https://agency.example/cameras.json"},
            fetcher=fetcher,
        ).fetch(ProviderRequest(capability_id="dot_traffic_cameras"))
    )

    assert response.payload["renderingMode"] == "camera-points"
    assert response.payload["features"][0]["id"] == "dot-1"
    assert response.payload["features"][0]["properties"]["officialUrl"].startswith(
        "https://"
    )

# --- test_geospatial_camera_permissions.py ---


###############################################################################
def test_webcam_embedding_requires_explicit_provider_permission() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Allowed",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                    "urls": {"detail": "https://example.test/allowed"},
                    "player": {
                        "embeddingAllowed": True,
                        "day": {"url": "https://example.test/embed"},
                    },
                },
                {
                    "webcamId": "cam-2",
                    "title": "Denied",
                    "location": {"latitude": 1.0, "longitude": 2.1},
                    "urls": {"detail": "https://example.test/denied"},
                    "player": {"day": {"url": "https://example.test/noembed"}},
                },
            ]
        }

    response = run_async_in_thread(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    allowed, denied = response.payload["features"]
    assert allowed["embedding_allowed"] is True
    assert allowed["embed_url"] == "https://example.test/embed"
    assert denied["embedding_allowed"] is False
    assert denied["embed_url"] is None

# --- test_geospatial_camera_staleness.py ---



###############################################################################
def test_webcam_provider_marks_stale_and_expired_previews() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Old camera",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                    "urls": {"detail": "https://example.test/cam"},
                    "images": {
                        "current": {
                            "url": "https://example.test/expired.jpg",
                            "expiresAt": "2000-01-01T00:00:00Z",
                        }
                    },
                    "lastUpdatedOn": "2000-01-01T00:00:00Z",
                }
            ]
        }

    response = run_async_in_thread(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    feature = response.payload["features"][0]
    assert feature["stale"] is True
    assert feature["preview_image_url"] is None
    assert feature["metadata"]["preview_expired"] is True

# --- test_rainviewer_provider.py ---



###############################################################################
class _Clock:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.value = 0.0

    # -------------------------------------------------------------------------
    def __call__(self) -> float:
        return self.value

###############################################################################
class _RainViewerService:

    # -------------------------------------------------------------------------
    def __init__(
        self, payload: dict[str, object] | None = None, *, fail: bool = False
    ) -> None:
        self.payload = payload or {
            "tile_url_template": "https://tiles.test/{z}/{x}/{y}.png",
            "latest_time": 123,
            "frame_count": 2,
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "RainViewer",
        }
        self.fail = fail
        self.calls = 0

    # -------------------------------------------------------------------------
    async def get_latest_radar_metadata(self) -> dict[str, object]:
        self.calls += 1
        if self.fail:
            raise RainViewerRequestError("offline")
        return self.payload

###############################################################################
def test_rainviewer_provider_returns_resolved_raster_tile_payload() -> None:
    service = _RainViewerService()
    provider = RainViewerProvider(service=service)  # type: ignore[arg-type]

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.provider_id == "rainviewer"
    assert response.result_type == "raster"
    assert response.payload["renderingMode"] == "raster-tile"
    assert response.payload["tileUrl"] == "https://tiles.test/{z}/{x}/{y}.png"
    assert response.stale is False

###############################################################################
def test_rainviewer_provider_uses_stale_cache_when_refresh_fails() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)
    cache.set(
        "rainviewer:latest-radar",
        {
            "tile_url_template": "https://stale.test/{z}/{x}/{y}.png",
            "latest_time": 100,
            "frame_count": 1,
            "attribution": "RainViewer",
        },
        ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    clock.value = 2.0
    provider = RainViewerProvider(
        service=_RainViewerService(fail=True),  # type: ignore[arg-type]
        cache=cache,
    )

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.stale is True
    assert response.payload["tileUrl"] == "https://stale.test/{z}/{x}/{y}.png"
    assert response.warnings

###############################################################################
def test_rainviewer_provider_returns_empty_state_when_no_cache_exists() -> None:
    provider = RainViewerProvider(service=_RainViewerService(fail=True))  # type: ignore[arg-type]

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert response.result_type == "raster"
    assert response.payload["tileUrl"] is None
    assert response.warnings

###############################################################################
def test_rainviewer_provider_returns_empty_state_for_malformed_payload() -> None:
    provider = RainViewerProvider(
        service=_RainViewerService(payload={"latest_time": 123}),  # type: ignore[arg-type]
    )

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert response.payload["frameCount"] == 0
    assert "usable radar tile frame" in response.warnings[0]

###############################################################################
def test_rainviewer_provider_uses_stale_cache_when_payload_is_malformed() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)
    cache.set(
        "rainviewer:latest-radar",
        {
            "tile_url_template": "https://stale.test/{z}/{x}/{y}.png",
            "latest_time": 100,
            "frame_count": 1,
            "attribution": "RainViewer",
        },
        ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    clock.value = 2.0
    provider = RainViewerProvider(
        service=_RainViewerService(payload={"tile_url_template": ""}),  # type: ignore[arg-type]
        cache=cache,
    )

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.stale is True
    assert response.payload["tileUrl"] == "https://stale.test/{z}/{x}/{y}.png"

###############################################################################
def test_rainviewer_provider_caches_successful_metadata_for_five_minutes() -> None:
    service = _RainViewerService()
    provider = RainViewerProvider(service=service)  # type: ignore[arg-type]
    request = ProviderRequest(capability_id="rainviewer_precipitation_radar")

    first = run_async_in_thread(provider.fetch(request))
    second = run_async_in_thread(provider.fetch(request))

    assert first.payload == second.payload
    assert service.calls == 1

###############################################################################
def test_rainviewer_provider_handles_timeout_like_service_failure() -> None:

    ###############################################################################
    class _TimeoutService:

        # -------------------------------------------------------------------------
        async def get_latest_radar_metadata(self) -> dict[str, object]:
            raise RainViewerRequestError("timed out")

    provider = RainViewerProvider(service=_TimeoutService())  # type: ignore[arg-type]

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert "timed out" in response.warnings[0]

# --- test_rainviewer_service.py ---



###############################################################################
def test_rainviewer_service_returns_cached_metadata_without_refetch() -> None:
    calls: list[str] = []

    async def _fetcher(
        url: str, headers: dict[str, str] | None = None
    ) -> dict[str, object]:
        calls.append(url)
        _ = headers
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": 100, "path": "/v2/radar/100"},
                    {"time": 200, "path": "/v2/radar/200"},
                ]
            },
        }

    service = RainViewerService(fetcher=_fetcher, cache_ttl_s=300.0)

    first = run_async_in_thread(service.get_latest_radar_metadata())
    second = run_async_in_thread(service.get_latest_radar_metadata())

    assert first["latest_time"] == 200
    assert (
        first["tile_url_template"]
        == "https://tilecache.rainviewer.com/v2/radar/200/256/{z}/{x}/{y}/2/1_1.png"
    )
    assert second["latest_time"] == 200
    assert calls == ["https://api.rainviewer.com/public/weather-maps.json"]

###############################################################################
def test_rainviewer_service_rejects_malformed_payload() -> None:
    async def _fetcher(
        url: str, headers: dict[str, str] | None = None
    ) -> dict[str, object]:
        _ = url, headers
        return {"host": "https://tilecache.rainviewer.com", "radar": {"past": []}}

    service = RainViewerService(fetcher=_fetcher)

    try:
        run_async_in_thread(service.get_latest_radar_metadata())
    except RainViewerRequestError as exc:
        assert "recent radar history frames" in str(exc)
    else:
        raise AssertionError("RainViewerRequestError was not raised.")

# --- test_geospatial_snapshot_prototypes.py ---



###############################################################################
def test_openchargemap_requires_key_for_hosted_access() -> None:
    try:
        run_async_in_thread(
            OpenChargeMapProvider().fetch(
                ProviderRequest(
                    capability_id="openchargemap_ev_charging",
                    params={"latitude": 41.9, "longitude": 12.5, "live": True},
                )
            )
        )
    except ProviderAuthError as exc:
        assert "Geospatial Access" in str(exc)
    else:
        raise AssertionError("Hosted Open Charge Map access must not be anonymous.")

###############################################################################
def test_openchargemap_reads_local_snapshot(tmp_path) -> None:
    snapshot = tmp_path / "ocm.json"
    snapshot.write_text(
        json.dumps(
            [
                {
                    "ID": 1,
                    "AddressInfo": {
                        "Title": "Charger",
                        "Latitude": 41.9,
                        "Longitude": 12.5,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    response = run_async_in_thread(
        OpenChargeMapProvider(snapshot_path=snapshot).fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"live": True, "latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    assert response.payload["sourceMode"] == "local-snapshot"
    assert response.payload["featureCount"] == 1