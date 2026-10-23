from __future__ import annotations
from tests.conftest import run_async_in_thread
from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.overpass import OverpassService
import math
from typing import Any

import pytest
import httpx
from server.services.geospatial.api_service import GeospatialApiService, GeospatialInvalidRequestError, GeospatialProviderResponseError, normalize_geojson_feature_collection
from server.services.geospatial.spatial_constraints import SpatialConstraintError, feature_matches_constraint, geodesic_distance_m, normalize_bbox, validate_geojson_geometry, validate_point
from server.services.geospatial.providers import http as provider_http

# --- test_direct_service_provenance.py ---



###############################################################################
def test_openmeteo_direct_service_results_carry_source_and_measurement_metadata() -> (
    None
):
    service = OpenMeteoService(
        weather_base_url="https://weather.example/forecast",
        air_quality_base_url="https://air.example/forecast",
    )
    captured: dict[str, object] = {}

    def get_json(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return {
            "timezone": "Europe/Rome",
            "current": {
                "time": "2026-09-01T09:00",
                "temperature_2m": 22.0,
                "precipitation": 0.0,
                "weather_code": 1,
                "relative_humidity_2m": 0,
                "surface_pressure": 0.0,
                "wind_speed_10m": 0.0,
                "wind_direction_10m": 0,
                "wind_gusts_10m": 0.0,
            },
            "current_units": {
                "temperature_2m": "°C",
                "relative_humidity_2m": "%",
                "surface_pressure": "hPa",
            },
            "hourly": {
                "time": ["2026-09-01T09:00"],
                "temperature_2m": [22.0],
                "precipitation": [0.0],
                "weather_code": [1],
                "relative_humidity_2m": [0],
                "surface_pressure": [0.0],
                "wind_speed_10m": [0.0],
                "wind_direction_10m": [0],
                "wind_gusts_10m": [0.0],
                "precipitation_probability": [0],
            },
            "hourly_units": {"precipitation": "mm", "relative_humidity_2m": "%"},
        }

    service._get_json = get_json  # type: ignore[method-assign]

    result = run_async_in_thread(
        service.get_weather_forecast(latitude=41.9, longitude=12.5)
    )

    assert result["provider"] == "openmeteo"
    assert result["source_url"] == "https://weather.example/forecast"
    assert result["result_status"] == "ok"
    assert result["partial"] is False
    assert result["result_type"] == "metadata"
    assert result["fetched_at"] == result["resolved_at"]
    assert result["observation_time"] == "2026-09-01T09:00"
    assert result["coverage"] == {
        "type": "point",
        "latitude": 41.9,
        "longitude": 12.5,
    }
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["current"] == ",".join(OpenMeteoService.WEATHER_CURRENT_VARIABLES)
    assert params["hourly"] == ",".join(OpenMeteoService.WEATHER_VARIABLES)
    assert result["current"]["relative_humidity_2m"] == 0
    assert result["hourly_forecast"][0]["precipitation_probability"] == 0

###############################################################################
def test_openmeteo_direct_service_marks_missing_measurements_as_partial() -> None:
    service = OpenMeteoService(weather_base_url="https://weather.example/forecast")
    service._get_json = lambda **kwargs: {  # type: ignore[method-assign]
        "current": {"time": "2026-09-01T09:00", "temperature_2m": 22.0},
        "hourly": {
            "time": ["2026-09-01T09:00"],
            "temperature_2m": [22.0],
            "precipitation": [0.0],
            "weather_code": [1],
        },
    }

    result = run_async_in_thread(
        service.get_weather_forecast(latitude=43.817, longitude=7.777)
    )

    assert result["result_status"] == "partial"
    assert result["partial"] is True
    assert result["hourly_forecast"][0]["relative_humidity_2m"] is None

###############################################################################
def test_openmeteo_direct_service_distinguishes_valid_empty_response() -> None:
    service = OpenMeteoService(weather_base_url="https://weather.example/forecast")
    service._get_json = lambda **kwargs: {  # type: ignore[method-assign]
        "hourly": {},
        "current": {},
    }

    result = run_async_in_thread(
        service.get_weather_forecast(latitude=43.817, longitude=7.777)
    )

    assert result["result_status"] == "valid_empty"
    assert result["partial"] is False

###############################################################################
def test_openmeteo_air_quality_service_retains_hourly_forecast_window() -> None:
    service = OpenMeteoService(air_quality_base_url="https://air.example/forecast")
    timeline = [f"2026-09-01T{hour:02d}:00" for hour in range(24)]
    service._get_json = lambda **kwargs: {  # type: ignore[method-assign]
        "timezone": "Europe/Rome",
        "hourly": {
            "time": timeline,
            **{
                name: [float(index) for index in range(24)]
                for name in OpenMeteoService.AIR_QUALITY_VARIABLES
            },
        },
    }

    result = run_async_in_thread(
        service.get_air_quality_forecast(latitude=41.9, longitude=12.5)
    )

    assert len(result["hourly_preview"]) == 6
    assert len(result["hourly_forecast"]) == 24
    assert result["hourly_forecast"][0]["time"] == timeline[0]
    assert result["hourly_forecast"][-1]["time"] == timeline[-1]


###############################################################################
def test_overpass_returns_the_nearest_results_and_flags_only_server_cuts() -> None:
    service = OverpassService(
        base_url="https://overpass.example/api/interpreter",
        default_radius_m=1000,
        default_limit=2,
    )
    requested_limits: list[int] = []

    def query(*, limit: int, element_count: int = 3, **_kwargs: Any) -> dict[str, Any]:
        requested_limits.append(limit)
        # Overpass order is unrelated to distance: farthest first here.
        return {
            "elements": [
                {
                    "type": "node",
                    "id": index,
                    "lat": 41.9 + index / 10000,
                    "lon": 12.5 + index / 10000,
                    "tags": {"amenity": "hospital", "name": f"Hospital {index}"},
                }
                for index in reversed(range(element_count))
            ]
        }

    service._query_overpass = query  # type: ignore[method-assign]
    result = run_async_in_thread(
        service.get_nearby_poi(
            latitude=41.9, longitude=12.5, categories=["hospitals"], limit=2
        )
    )

    assert requested_limits == [8]
    assert [item["name"] for item in result["items"]] == ["Hospital 0", "Hospital 1"]
    assert result["result_status"] == "ok"
    assert result["total_results"] == 3
    assert result["returned_results"] == 2
    assert result["truncated"] is False
    assert result["coverage"]["radius_m"] == 1000

    service._query_overpass = lambda **kwargs: query(**kwargs, element_count=8)  # type: ignore[method-assign]
    capped = run_async_in_thread(
        service.get_nearby_poi(
            latitude=41.9, longitude=12.5, categories=["hospitals"], limit=2
        )
    )

    assert capped["result_status"] == "partial"
    assert capped["truncated"] is True

# --- test_geospatial_api_validation.py ---




###############################################################################
def test_geojson_normalization_preserves_valid_geometry_and_coordinates() -> None:
    result = normalize_geojson_feature_collection(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "point-1",
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                    "properties": {"name": "valid"},
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[12.4, 41.8], [12.6, 41.8], [12.6, 42.0], [12.4, 41.8]]
                        ],
                    },
                    "properties": {},
                },
            ],
        }
    )

    assert len(result["features"]) == 2
    assert result["features"][0]["geometry"]["coordinates"] == [12.5, 41.9]

###############################################################################
@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [181, 41]},
                    "properties": {},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [12, math.nan]},
                    "properties": {},
                }
            ],
        },
    ],
)
def test_geojson_normalization_rejects_invalid_geometry(payload: dict) -> None:
    with pytest.raises(GeospatialProviderResponseError, match="invalid geometry"):
        normalize_geojson_feature_collection(payload)

###############################################################################
def test_geojson_normalization_converts_latitude_longitude_records() -> None:
    result = normalize_geojson_feature_collection(
        {
            "features": [
                {
                    "id": "station-1",
                    "latitude": 41.9,
                    "longitude": 12.5,
                    "value": 4.2,
                }
            ]
        }
    )

    feature = result["features"][0]
    assert feature["geometry"] == {
        "type": "Point",
        "coordinates": [12.5, 41.9],
    }
    assert feature["properties"]["value"] == 4.2

###############################################################################
def test_bbox_parser_enforces_west_south_east_north_and_finite_values() -> None:
    service = object.__new__(GeospatialApiService)

    assert service._parse_bbox("12.0,41.0,13.0,42.0") == (
        12.0,
        41.0,
        13.0,
        42.0,
    )
    with pytest.raises(GeospatialInvalidRequestError, match="ordered"):
        service._parse_bbox("13.0,41.0,12.0,42.0")
    with pytest.raises(GeospatialInvalidRequestError, match="finite"):
        service._parse_bbox("12.0,41.0,nan,42.0")

# --- test_spatial_constraints.py ---



###############################################################################
def test_bbox_uses_west_south_east_north_and_preserves_antimeridian_wrap() -> None:
    assert normalize_bbox([8.0, 45.0, 9.0, 46.0]) == [8.0, 45.0, 9.0, 46.0]
    assert normalize_bbox([170.0, -10.0, -170.0, 10.0]) == [170.0, -10.0, -170.0, 10.0]

    with pytest.raises(SpatialConstraintError, match="equal longitudes"):
        normalize_bbox([8.0, 45.0, 8.0, 46.0])

###############################################################################
def test_invalid_coordinates_and_geometry_fail_closed() -> None:
    with pytest.raises(SpatialConstraintError):
        validate_point(91.0, 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_point(True, 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_point(float("nan"), 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_geojson_geometry({"type": "Polygon", "coordinates": []})

###############################################################################
def test_radius_uses_wgs84_geodesic_distance() -> None:
    distance = geodesic_distance_m(0.0, 0.0, 0.0, 1.0)
    assert 110_000 < distance < 112_000

###############################################################################
def test_containment_and_distance_are_applied_to_feature_geometry() -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[8.0, 45.0], [9.0, 45.0], [9.0, 46.0], [8.0, 46.0], [8.0, 45.0]]],
    }
    inside = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.5, 45.5]}}
    outside = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 45.5]}}

    assert feature_matches_constraint(
        inside,
        relationship="in",
        reference_geometry=polygon,
    ) is True
    assert feature_matches_constraint(
        outside,
        relationship="in",
        reference_geometry=polygon,
    ) is False
    assert feature_matches_constraint(
        inside,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=10,
    ) is True
    assert feature_matches_constraint(
        outside,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=10,
    ) is False

###############################################################################
def test_distance_uses_the_nearest_part_of_nonpoint_geometry() -> None:
    line = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[8.5001, 45.5], [12.0, 50.0]],
        },
    }

    assert feature_matches_constraint(
        line,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=20,
    ) is True

# --- test_provider_http.py ---





###############################################################################
class _FakeResponse:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (),
        body_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {})
        self._chunks = chunks
        self._body_error = body_error

    # -------------------------------------------------------------------------
    async def __aenter__(self) -> _FakeResponse:
        return self

    # -------------------------------------------------------------------------
    async def __aexit__(self, *args: object) -> None:
        return None

    # -------------------------------------------------------------------------
    async def aiter_bytes(self):  # noqa: ANN201
        if self._body_error is not None:
            raise self._body_error
        for chunk in self._chunks:
            yield chunk


###############################################################################
class _FakeClient:

    # -------------------------------------------------------------------------
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self.response = response

    # -------------------------------------------------------------------------
    def stream(self, *args: object, **kwargs: object):  # noqa: ANN201
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


###############################################################################
def _request_error(message: str) -> httpx.RequestError:
    return httpx.ConnectError(message, request=httpx.Request("GET", "https://example.test/tile"))


###############################################################################
@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (301, "unexpected_redirect"),
        (401, "authentication_rejected"),
        (404, "invalid_request"),
        (429, "rate_limited"),
        (500, "upstream_http_5xx"),
        (503, "upstream_http_5xx"),
    ],
)
def test_raster_http_classifies_upstream_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    category: str,
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                status_code=status_code,
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "content-length": "17",
                },
            )
        ),
    )

    with provider_http.raster_diagnostic_scope(
        provider_id="fema", capability_id="fema_nfhl_flood_zones"
    ):
        with pytest.raises(provider_http.RasterHttpError) as error:
            run_async_in_thread(
                provider_http.fetch_raster_image_url(
                    "https://example.test/tile.png?api_key=secret-token&token=secret-token"
                )
            )

    diagnostic = error.value.diagnostic
    assert diagnostic.category == category
    assert diagnostic.status_code == status_code
    assert diagnostic.content_type == "text/html"
    assert diagnostic.content_length == 17
    assert diagnostic.failure_phase == "response_headers"
    assert diagnostic.provider_id == "fema"
    assert diagnostic.capability_id == "fema_nfhl_flood_zones"
    assert diagnostic.upstream == "https://example.test/tile.png"
    assert "secret-token" not in str(error.value)
    assert "secret-token" not in diagnostic.upstream


###############################################################################
def test_raster_http_classifies_transport_failure_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for expected_category, exception in (
        ("connect_timeout", httpx.ConnectTimeout("secret-connect-timeout")),
        ("read_timeout", httpx.ReadTimeout("secret-read-timeout")),
        ("proxy_failure", httpx.ProxyError("secret-proxy")),
        ("remote_protocol_failure", httpx.RemoteProtocolError("secret-reset")),
        ("connection_failure", _request_error("secret-connection")),
    ):
        monkeypatch.setattr(
            provider_http,
            "_ASYNC_HTTP_CLIENT",
            _FakeClient(exception),
        )
        with pytest.raises(provider_http.RasterHttpError) as error:
            run_async_in_thread(
                provider_http.fetch_raster_image_url(
                    "https://example.test/tile.png?credential=secret-token"
                )
            )
        assert error.value.diagnostic.category == expected_category
        assert error.value.diagnostic.failure_phase == "request"
        assert error.value.diagnostic.status_code is None
        assert "secret" not in str(error.value).lower()


###############################################################################
def test_raster_http_classifies_body_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png", "content-length": "8"},
                body_error=RuntimeError("secret body failure"),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url("https://example.test/tile.png")
        )

    assert error.value.diagnostic.category == "body_read_failure"
    assert error.value.diagnostic.failure_phase == "response_body"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_type == "image/png"
    assert error.value.diagnostic.content_length == 8
    assert "secret body failure" not in str(error.value)


###############################################################################
@pytest.mark.parametrize(
    ("body", "content_type", "category"),
    [
        (b"", "image/png", "empty_body"),
        (b"<html>provider error</html>", "text/html", "non_image_body"),
        (b"<?xml version='1.0'?><error/>", "application/xml", "non_image_body"),
    ],
)
def test_raster_http_classifies_empty_and_non_image_bodies(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    content_type: str,
    category: str,
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": content_type},
                chunks=(body,),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url("https://example.test/tile.png")
        )

    assert error.value.diagnostic.category == category
    assert error.value.diagnostic.failure_phase == "validation"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_type == content_type
    assert error.value.diagnostic.content_length == len(body)


###############################################################################
@pytest.mark.parametrize(
    "body",
    [b"\x89PNG\r\n\x1a\npng", b"\xff\xd8\xffjpeg"],
)
def test_raster_http_accepts_png_and_jpeg(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png"}, chunks=(body,)
            )
        ),
    )

    assert run_async_in_thread(
        provider_http.fetch_raster_image_url("https://example.test/tile.png")
    ) == body


###############################################################################
def test_raster_http_classifies_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png", "content-length": "9"},
                chunks=(b"\x89PNG\r\n\x1a\n",),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url(
                "https://example.test/tile.png", max_bytes=8
            )
        )

    assert error.value.diagnostic.category == "response_too_large"
    assert error.value.diagnostic.failure_phase == "response_headers"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_length == 9