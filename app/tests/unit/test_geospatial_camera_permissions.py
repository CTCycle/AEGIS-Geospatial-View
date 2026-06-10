from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


###############################################################################
def test_webcam_embedding_requires_explicit_provider_permission() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Allowed",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                    "urls": {"detail": "https://example.test/allowed"},
                    "player": {
                        "embeddingAllowed": True,
                        "day": {"url": "https://example.test/embed"},
                    },
                },
                {
                    "webcamId": "cam-2",
                    "title": "Denied",
                    "location": {"latitude": 1.0, "longitude": 2.1},
                    "urls": {"detail": "https://example.test/denied"},
                    "player": {"day": {"url": "https://example.test/noembed"}},
                },
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    allowed, denied = response.payload["features"]
    assert allowed["embedding_allowed"] is True
    assert allowed["embed_url"] == "https://example.test/embed"
    assert denied["embedding_allowed"] is False
    assert denied["embed_url"] is None
