from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.providers.tomtom import TomTomProvider

###############################################################################
def test_rainviewer_provider_emits_renderable_raster_payload() -> None:
    rainviewer = run_async_in_thread(
        RainViewerProvider().fetch(
            ProviderRequest(capability_id="rainviewer_precipitation_radar")
        )
    )

    assert rainviewer.payload["renderingMode"] == "raster-tile"
    assert rainviewer.attribution

###############################################################################
def test_tomtom_traffic_flow_keeps_key_server_side() -> None:
    response = run_async_in_thread(
        TomTomProvider(api_key="tomtom-secret").fetch(
            ProviderRequest(capability_id="tomtom_traffic_flow")
        )
    )

    assert response.payload["credentialPolicy"] == "server-side-only"
    assert "tomtom-secret" not in str(response.payload)
