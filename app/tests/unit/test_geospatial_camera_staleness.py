from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


def test_webcam_provider_marks_stale_and_expired_previews() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Old camera",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                    "urls": {"detail": "https://example.test/cam"},
                    "images": {
                        "current": {
                            "url": "https://example.test/expired.jpg",
                            "expiresAt": "2000-01-01T00:00:00Z",
                        }
                    },
                    "lastUpdatedOn": "2000-01-01T00:00:00Z",
                }
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    feature = response.payload["features"][0]
    assert feature["stale"] is True
    assert feature["preview_image_url"] is None
    assert feature["metadata"]["preview_expired"] is True
