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
    service._get_json = lambda **kwargs: {  # type: ignore[method-assign]
        "timezone": "Europe/Rome",
        "current": {"time": "2026-09-01T09:00", "temperature_2m": 22.0},
        "current_units": {"temperature_2m": "°C"},
        "hourly": {
            "time": ["2026-09-01T09:00"],
            "temperature_2m": [22.0],
            "precipitation": [0.0],
            "weather_code": [1],
        },
        "hourly_units": {"precipitation": "mm"},
    }

    result = run_async_in_thread(
        service.get_weather_forecast(latitude=41.9, longitude=12.5)
    )

    assert result["provider"] == "openmeteo"
    assert result["source_url"] == "https://weather.example/forecast"
    assert result["result_status"] == "ok"
    assert result["result_type"] == "metadata"
    assert result["fetched_at"] == result["resolved_at"]
    assert result["observation_time"] == "2026-09-01T09:00"
    assert result["coverage"] == {
        "type": "point",
        "latitude": 41.9,
        "longitude": 12.5,
    }


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
