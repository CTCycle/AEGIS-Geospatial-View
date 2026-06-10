from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


###############################################################################
def test_camera_normalization_never_embeds_without_explicit_permission() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Official link only",
                    "location": {"latitude": 45.2, "longitude": 7.3},
                    "urls": {"detail": "https://example.test/cam"},
                    "player": {"day": {"url": "https://example.test/player"}},
                }
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    feature = response.payload["features"][0]
    assert feature["official_url"] == "https://example.test/cam"
    assert feature["embedding_allowed"] is False
    assert feature["embed_url"] is None
