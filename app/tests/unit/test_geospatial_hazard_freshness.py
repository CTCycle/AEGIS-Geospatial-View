from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider


###############################################################################
def test_hazard_providers_include_freshness_labels() -> None:
    responses = [
        asyncio.run(USGSProvider().fetch(ProviderRequest(capability_id="usgs_water_gauges"))),
        asyncio.run(NOAAProvider().fetch(ProviderRequest(capability_id="noaa_coops_water_levels"))),
        asyncio.run(
            NASAFIRMSProvider(api_key="nasa-test").fetch(
                ProviderRequest(capability_id="nasa_firms_active_fires")
            )
        ),
    ]

    for response in responses:
        assert response.payload["freshnessLabel"]
