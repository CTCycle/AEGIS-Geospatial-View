from __future__ import annotations

import asyncio

from server.services.geospatial.overpass import OverpassService
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.overpass import OverpassProvider


###############################################################################
class _BuildingService:
    default_radius_m = 1500.0

    # -------------------------------------------------------------------------
    async def get_residential_buildings(self, **kwargs):
        assert kwargs["latitude"] == 41.89
        assert kwargs["longitude"] == 12.49
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[12.49, 41.89], [12.50, 41.89], [12.49, 41.89]]],
                    },
                    "properties": {"building": "apartments"},
                }
            ],
        }


###############################################################################
def test_overpass_provider_routes_residential_capability_separately() -> None:
    async def _run() -> None:
        response = await OverpassProvider(service=_BuildingService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="overpass_residential_buildings",
                params={"latitude": 41.89, "longitude": 12.49},
            )
        )
        assert response.payload["type"] == "FeatureCollection"
        assert response.payload["features"][0]["properties"]["building"] == "apartments"
        assert "OpenStreetMap" in response.attribution[0]

    asyncio.run(_run())


###############################################################################
def test_residential_building_normalization_rejects_non_polygons() -> None:
    service = OverpassService()
    service._query_buildings = lambda **kwargs: {  # type: ignore[method-assign]
        "elements": [
            {"type": "node", "id": 1, "tags": {"building": "house"}},
            {
                "type": "way",
                "id": 2,
                "tags": {"building": "commercial"},
                "geometry": [
                    {"lat": 41.0, "lon": 12.0},
                    {"lat": 41.1, "lon": 12.1},
                    {"lat": 41.0, "lon": 12.0},
                ],
            },
        ]
    }
    payload = asyncio.run(
        service.get_residential_buildings(
            latitude=41.89,
            longitude=12.49,
            limit=10,
        )
    )
    assert payload["features"] == []

