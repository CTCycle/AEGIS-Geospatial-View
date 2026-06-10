from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.geoapify import GeoapifyProvider


###############################################################################
def test_geoapify_poi_normalization_keeps_popup_metadata() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "features": [
                {
                    "properties": {
                        "place_id": "poi-1",
                        "name": "Clinic",
                        "categories": ["healthcare.clinic"],
                        "formatted": "1 Test Street",
                    },
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                }
            ]
        }

    response = asyncio.run(
        GeoapifyProvider(api_key="geoapify-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="geoapify_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"live": True, "categories": "healthcare"},
            )
        )
    )

    feature = response.payload["features"][0]
    assert feature["name"] == "Clinic"
    assert feature["address"] == "1 Test Street"
    assert feature["source"] == "geoapify"
