from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.providers.tomtom import TomTomProvider


def test_existing_raster_providers_emit_renderable_payloads() -> None:
    gibs = asyncio.run(
        NASAGIBSProvider().fetch(
            ProviderRequest(capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor")
        )
    )
    rainviewer = asyncio.run(
        RainViewerProvider().fetch(
            ProviderRequest(capability_id="rainviewer_precipitation_radar")
        )
    )

    assert gibs.payload["renderingMode"] == "wms"
    assert rainviewer.payload["renderingMode"] == "raster-tile"
    assert gibs.attribution
    assert rainviewer.attribution


def test_tomtom_traffic_flow_keeps_key_server_side() -> None:
    response = asyncio.run(
        TomTomProvider(api_key="tomtom-secret").fetch(
            ProviderRequest(capability_id="tomtom_traffic_flow")
        )
    )

    assert response.payload["credentialPolicy"] == "server-side-only"
    assert "tomtom-secret" not in str(response.payload)
