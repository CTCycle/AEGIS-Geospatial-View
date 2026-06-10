from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


###############################################################################
def test_windy_webcam_provider_builds_bbox_camera_request() -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append((url, headers))
        return {"webcams": []}

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="windy_webcams",
                bbox=(7.0, 45.0, 7.5, 45.5),
                params={"live": True, "camera_type": "traffic"},
            )
        )
    )

    assert "bbox=7.0,45.0,7.5,45.5" in calls[0][0]
    assert "category=traffic" in calls[0][0]
    assert calls[0][1] == {"x-windy-api-key": "windy-test"}
    assert response.payload["renderingMode"] == "camera-points"


###############################################################################
def test_camera_manifest_templates_are_registered() -> None:
    from server.services.geospatial.manifest_loader import GeospatialManifestLoader

    cameras = {
        item["id"] for item in GeospatialManifestLoader().load_all()["cameras"]
    }

    assert {
        "dot_traffic_cameras",
        "public_transport_cameras",
        "tourism_webcams",
        "ski_resort_webcams",
        "port_airport_webcams",
        "environmental_monitoring_cameras",
    }.issubset(cameras)


###############################################################################
def test_local_open_data_camera_template_fetches_configured_source() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "cameras": [
                {
                    "id": "dot-1",
                    "name": "Main Street",
                    "latitude": 41.9,
                    "longitude": 12.5,
                    "officialUrl": "https://agency.example/cameras/dot-1",
                }
            ]
        }

    response = asyncio.run(
        LocalOpenDataProvider(
            source_map={"dot_traffic_cameras": "https://agency.example/cameras.json"},
            fetcher=fetcher,
        ).fetch(ProviderRequest(capability_id="dot_traffic_cameras"))
    )

    assert response.payload["renderingMode"] == "camera-points"
    assert response.payload["features"][0]["id"] == "dot-1"
    assert response.payload["features"][0]["properties"]["officialUrl"].startswith("https://")
