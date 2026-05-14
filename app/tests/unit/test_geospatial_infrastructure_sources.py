from __future__ import annotations

import asyncio

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.overture import OvertureProvider


def test_geospatial_infrastructure_providers_are_registered() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    for provider_id in ("openchargemap", "nrel", "ourairports", "overture"):
        assert provider_id in registry.list_provider_ids()


def test_openchargemap_infrastructure_source_normalizes_live_station() -> None:
    async def fetcher(url, headers):
        del url, headers
        return [
            {
                "ID": 1,
                "AddressInfo": {
                    "Title": "Fast Charge",
                    "Latitude": 41.9,
                    "Longitude": 12.5,
                    "AddressLine1": "1 Main St",
                },
            }
        ]

    response = asyncio.run(
        OpenChargeMapProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5, "live": True},
            )
        )
    )

    assert response.payload["features"][0]["category"] == "ev_charging"
    assert response.payload["features"][0]["source"] == "openchargemap"


def test_overture_maps_remains_ingestion_backed() -> None:
    response = asyncio.run(
        OvertureProvider().fetch(ProviderRequest(capability_id="overture_maps_places"))
    )

    assert response.payload["status"] == "requires-ingestion"
