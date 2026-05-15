from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider


def test_hazard_providers_emit_renderable_descriptors() -> None:
    earthquake = asyncio.run(USGSProvider().fetch(ProviderRequest(capability_id="usgs_earthquakes")))
    alerts = asyncio.run(NOAAProvider().fetch(ProviderRequest(capability_id="noaa_weather_alerts")))
    flood = asyncio.run(FEMAProvider().fetch(ProviderRequest(capability_id="fema_nfhl_flood_zones")))
    fires = asyncio.run(
        NASAFIRMSProvider(api_key="nasa-test").fetch(
            ProviderRequest(capability_id="nasa_firms_active_fires")
        )
    )

    assert earthquake.payload["renderingMode"] == "clustered-points"
    assert alerts.payload["renderingMode"] == "geojson"
    assert flood.payload["renderingMode"] == "wms"
    assert fires.payload["renderingMode"] == "clustered-points"
