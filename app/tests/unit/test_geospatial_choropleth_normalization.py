from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.census import CensusProvider


def test_census_demographic_payload_uses_choropleth_contract() -> None:
    response = asyncio.run(
        CensusProvider().fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert response.payload["renderingMode"] == "choropleth"
    assert response.payload["classificationField"]
    assert response.attribution
