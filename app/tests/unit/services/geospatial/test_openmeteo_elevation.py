from __future__ import annotations

import asyncio

from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider


###############################################################################
class StubOpenMeteoService(OpenMeteoService):
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.elevation_base_url = "https://api.open-meteo.com/v1/elevation"
        self.weather_base_url = "https://api.open-meteo.com/v1/forecast"
        self.air_quality_base_url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
        )

    # -------------------------------------------------------------------------
    async def get_elevation(
        self, *, latitude: float, longitude: float
    ) -> dict[str, object]:
        return {
            "provider": "openmeteo",
            "kind": "terrain_elevation",
            "source_url": self.elevation_base_url,
            "fetched_at": "2026-09-03T12:00:00+00:00",
            "result_status": "ok",
            "result_type": "metadata",
            "partial": False,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": 1234.0,
            "resolved_at": "2026-09-03T12:00:00+00:00",
            "observation_time": None,
            "units": {"elevation": "m"},
            "requested_variables": ["elevation"],
            "request_parameters": {
                "latitude": f"{latitude:.6f}",
                "longitude": f"{longitude:.6f}",
            },
            "spatial_resolution": "90 m Copernicus DEM GLO-90",
            "coverage": {
                "type": "point",
                "latitude": latitude,
                "longitude": longitude,
            },
            "attribution": "Data from Open-Meteo; Copernicus DEM GLO-90",
        }


###############################################################################
def test_openmeteo_provider_routes_and_normalizes_elevation() -> None:
    provider = OpenMeteoProvider(service=StubOpenMeteoService())
    request = ProviderRequest(
        capability_id="openmeteo_elevation",
        bbox=(8.5, 46.0, 8.5, 46.0),
    )

    response = asyncio.run(provider.fetch(request))

    assert response.result_status == "ok"
    assert response.result_type == "features"
    assert response.spatial_resolution == "90 m Copernicus DEM GLO-90"
    assert response.units == {"elevation": "m"}
    assert response.source_url == "https://api.open-meteo.com/v1/elevation"
    assert response.payload["kind"] == "terrain_elevation"
    features = response.payload["features"]
    assert isinstance(features, list)
    assert len(features) == 1
    feature = features[0]
    assert feature["category"] == "terrain"
    assert feature["elevation"] == 1234.0
    assert feature["latitude"] == 46.0
    assert feature["longitude"] == 8.5
