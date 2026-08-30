from __future__ import annotations

from fastapi.testclient import TestClient

from server.api import geospatial
from server.app import create_app
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def create_started_client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    return client


###############################################################################
class _NoCredentials:
    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None


###############################################################################
def _service_dependencies() -> dict[str, object]:
    manifest_loader = GeospatialManifestLoader()
    runtime_registry = RuntimeRegistry(
        manifest_loader=manifest_loader,
        credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
    )
    return {
        "catalog_service": GeospatialCatalogService(
            capability_registry=CapabilityRegistry(manifest_loader=manifest_loader),
            runtime_registry=runtime_registry,
        ),
        "manifest_loader": manifest_loader,
        "runtime_registry": runtime_registry,
        "provider_registry": object(),
    }


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

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        CameraService(**_service_dependencies())
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

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        MissingCredentialService(**_service_dependencies())
    )

    response = client.get("/api/geospatial/cameras/windy%2Fcamera-1")

    assert response.status_code == 200
    assert response.json()["status"] == "missing-credential"
    assert response.json()["provider"] == "windy_webcams"
