from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers._request import grid_points
from server.services.geospatial.openmeteo import OpenMeteoService
from urllib.parse import urlencode
from unittest.mock import patch
import pytest

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


@pytest.mark.parametrize("bbox", [(-180, -85, 180, 85), (-25, 34, 45, 72), (8, 45, 8.1, 70)])
def test_weather_grid_cap_and_interior_centres(bbox):
    points, spacing = grid_points(bbox)
    assert 1 <= len(points) <= 100 and spacing > 0
    assert all(bbox[0] < lon < bbox[2] and bbox[1] < lat < bbox[3] for lat, lon in points)


@pytest.mark.asyncio
async def test_weather_grid_sea_future_hours_and_provenance():
    class Service:
        weather_base_url = "https://api.open-meteo.com/v1/forecast"
        async def get_weather_grid(self, points, past_days):
            row = {"elevation": 100, "current": {"time": "2026-10-20T12:00", "temperature_2m": 30},
                   "hourly": {"time": ["2026-10-20T11:00", "2026-10-20T12:00", "2026-10-20T13:00"],
                              "temperature_2m": [28, 30, 99], "precipitation": [2, 3, 100]}}
            return [{**row, "elevation": 0}, row, {**row, "current": {}}] + [row for _ in points[3:]]
    result = await OpenMeteoProvider(service=Service()).fetch(ProviderRequest(
        capability_id="openmeteo_weather_forecast", bbox=(-25, 34, 45, 72), params={"sampling": "area"}))
    assert result.payload["features"][0]["precipitation_sum_mm"] == 5
    assert result.payload["features"][0]["temperature_2m_max_c"] == 30
    assert result.coverage["excluded_sea_points"] == 1
    assert result.coverage["value_kind"] == "model_estimate"
    assert result.result_status == "partial"
    assert result.units["precipitation_sum_mm"] == "mm"


@pytest.mark.asyncio
async def test_weather_grid_one_cached_request_url_under_8kb():
    service = OpenMeteoService()
    captured = {}
    def get_json(**kwargs):
        captured.update(kwargs)
        return {"locations": [{"elevation": 10}] * 100}
    with patch.object(service, "_get_json", side_effect=get_json):
        points, _ = grid_points((-180, -85, 180, 85))
        result = await service.get_weather_grid(points, 30)
    assert len(result) == 100
    assert captured["params"]["past_days"] == "14"
    assert len(captured["endpoint"] + "?" + urlencode(captured["params"])) < 8192
