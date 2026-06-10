from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider


###############################################################################
def test_hazard_providers_include_legend_metadata() -> None:
    responses = [
        asyncio.run(USGSProvider().fetch(ProviderRequest(capability_id="usgs_earthquakes"))),
        asyncio.run(NOAAProvider().fetch(ProviderRequest(capability_id="noaa_weather_alerts"))),
        asyncio.run(NOAAProvider().fetch(ProviderRequest(capability_id="noaa_radar"))),
        asyncio.run(FEMAProvider().fetch(ProviderRequest(capability_id="fema_nfhl_flood_zones"))),
    ]

    for response in responses:
        assert response.payload["legend"]["type"]
        assert response.payload["legend"]["label"]
