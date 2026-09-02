from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.overpass import OverpassService


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
def test_overpass_direct_service_marks_limited_results_as_partial() -> None:
    service = OverpassService(
        base_url="https://overpass.example/api/interpreter",
        default_radius_m=1000,
        default_limit=2,
    )
    service._query_overpass = lambda **kwargs: {  # type: ignore[method-assign]
        "elements": [
            {
                "type": "node",
                "id": index,
                "lat": 41.9 + index / 10000,
                "lon": 12.5 + index / 10000,
                "tags": {"amenity": "hospital", "name": f"Hospital {index}"},
            }
            for index in range(3)
        ]
    }

    result = run_async_in_thread(
        service.get_nearby_poi(
            latitude=41.9,
            longitude=12.5,
            categories=["hospitals"],
            limit=2,
        )
    )

    assert result["source_url"] == "https://overpass.example/api/interpreter"
    assert result["result_status"] == "partial"
    assert result["result_type"] == "features"
    assert result["total_results"] == 3
    assert result["returned_results"] == 2
    assert result["truncated"] is True
    assert result["partial"] is True
    assert result["coverage"]["radius_m"] == 1000
