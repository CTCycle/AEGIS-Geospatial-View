from __future__ import annotations

from fastapi.testclient import TestClient

from server.api import geospatial
from server.app import create_app
from server.services.geospatial.api_service import GeospatialApiService


###############################################################################
def test_camera_detail_uses_provider_backed_lookup() -> None:

    ###############################################################################
    class CameraService(GeospatialApiService):

        # -------------------------------------------------------------------------
        async def _fetch_provider_payload(self, provider_id, request):
            assert provider_id == "windy_webcams"
            assert request.params["camera_id"] == "camera-1"
            return {
                "status": "ok",
                "provider": provider_id,
                "payload": {
                    "features": [
                        {
                            "id": "camera-1",
                            "name": "Pass view",
                            "official_url": "https://example.test/camera-1",
                            "embedding_allowed": False,
                        }
                    ]
                },
                "attribution": ["Windy"],
                "warnings": [],
                "stale": False,
            }

    client = TestClient(create_app())
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = (
        lambda: CameraService()
    )

    response = client.get("/api/geospatial/cameras/windy_webcams%2Fcamera-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["provider"] == "windy_webcams"
    assert payload["camera"]["official_url"] == "https://example.test/camera-1"


###############################################################################
def test_camera_detail_preserves_safe_fallback_without_provider_data() -> None:

    ###############################################################################
    class MissingCredentialService(GeospatialApiService):

        # -------------------------------------------------------------------------
        async def _fetch_provider_payload(self, provider_id, request):
            del request
            return {
                "status": "missing-credential",
                "provider": provider_id,
                "message": "Windy Webcams API key is required.",
            }

    client = TestClient(create_app())
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = (
        lambda: MissingCredentialService()
    )

    response = client.get("/api/geospatial/cameras/windy%2Fcamera-1")

    assert response.status_code == 200
    assert response.json()["status"] == "missing-credential"
    assert response.json()["provider"] == "windy_webcams"
