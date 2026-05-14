from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.api import geospatial
from server.app import create_app
from server.services.geospatial.providers.base import ProviderRateLimitError, ProviderTimeoutError


def test_geospatial_capabilities_include_camera_network() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert any(item["id"] == "windy_webcams" for item in payload["cameras"])


def test_geospatial_layers_endpoint_groups_layers() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/layers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["basemaps"]
    assert payload["overlays"]
    assert payload["cameras"]
    assert payload["transit"]


def test_geospatial_transit_features_return_metadata_until_feed_configured() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/layers/gtfs_realtime/features")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["payload"]["renderingMode"] == "metadata-only"


def test_geospatial_layer_health_returns_manifest_reliability() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/layers/rainviewer_precipitation_radar/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "rainviewer_precipitation_radar"
    assert payload["reliability"]["status"] in {"functional", "partial", "unknown"}


def test_geospatial_features_reports_missing_credentials_without_500() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/layers/tomtom_traffic_flow/features")

    assert response.status_code == 200
    assert response.json()["status"] in {"missing-credential", "ok"}


def test_geospatial_features_accepts_live_provider_flags_without_500() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/geospatial/layers/tomtom_traffic_flow/features"
        "?bbox=12,41,13,42&live=true&incidents=true"
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"missing-credential", "ok", "unavailable"}


@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [
        (ProviderRateLimitError("provider quota exceeded"), "rate-limited"),
        (ProviderTimeoutError("provider request timed out"), "unavailable"),
    ],
)
def test_geospatial_features_map_provider_failures_without_500(
    monkeypatch, provider_error: Exception, expected_status: str
) -> None:
    class FailingRegistry:
        def build_from_manifests(self) -> None:
            return None

        async def fetch(self, provider_id, request):
            del provider_id, request
            raise provider_error

    monkeypatch.setattr(geospatial, "ProviderRegistry", FailingRegistry)
    client = TestClient(create_app())

    response = client.get("/api/geospatial/layers/usgs_earthquakes/features?live=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected_status
    assert payload["provider"] == "usgs"


def test_geospatial_cameras_report_missing_windy_key_without_500(monkeypatch) -> None:
    monkeypatch.delenv("WINDY_WEBCAMS_API_KEY", raising=False)
    client = TestClient(create_app())

    response = client.get("/api/geospatial/cameras?bbox=12,41,13,42")

    assert response.status_code == 200
    assert response.json()["status"] == "missing-credential"


def test_geospatial_camera_detail_returns_provider_payload_shape() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/cameras/windy%2Fcamera-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "windy/camera-1"
    assert payload["status"] in {"missing-credential", "metadata-unavailable", "ok"}
    assert payload["provider"] == "windy_webcams"


def test_geospatial_credential_status_uses_existing_env_pattern(monkeypatch) -> None:
    monkeypatch.setenv("WINDY_WEBCAMS_API_KEY", "test-key")
    client = TestClient(create_app())

    response = client.get("/api/geospatial/sources/windy_webcams/credential-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["required"] is True
    assert payload["configured"] is True
    assert payload["environmentVariable"] == "WINDY_WEBCAMS_API_KEY"


@pytest.mark.parametrize(
    ("provider_id", "env_name"),
    [
        ("opentripmap", "OPENTRIPMAP_API_KEY"),
        ("openchargemap", "OPENCHARGEMAP_API_KEY"),
        ("nrel", "NREL_API_KEY"),
    ],
)
def test_phase8_credential_status_uses_provider_environment(
    monkeypatch, provider_id: str, env_name: str
) -> None:
    monkeypatch.delenv(env_name, raising=False)
    client = TestClient(create_app())

    missing = client.get(f"/api/geospatial/sources/{provider_id}/credential-status")
    assert missing.status_code == 200
    assert missing.json()["environmentVariable"] == env_name
    assert missing.json()["configured"] is False

    monkeypatch.setenv(env_name, "test-key")
    configured = client.get(f"/api/geospatial/sources/{provider_id}/credential-status")
    assert configured.status_code == 200
    assert configured.json()["configured"] is True


def test_geospatial_audit_endpoint_passes() -> None:
    client = TestClient(create_app())

    response = client.post("/api/geospatial/audit")

    assert response.status_code == 200
    assert response.json()["error_count"] == 0
