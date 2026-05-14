from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider


class _OpenMeteoService:
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

    async def get_air_quality_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "hourly_preview": [{"pm2_5": 8, "pm10": 12}],
            "attribution": "Data from Open-Meteo",
        }


def test_openmeteo_wind_sampling_emits_arrow_metadata() -> None:
    response = asyncio.run(
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
