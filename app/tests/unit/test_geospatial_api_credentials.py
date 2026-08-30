from __future__ import annotations

from fastapi.testclient import TestClient
from server.app import create_app


###############################################################################
def create_started_client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    return client


###############################################################################
def test_credential_status_does_not_return_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("WINDY_WEBCAMS_API_KEY", "windy-secret")
    client = create_started_client()

    response = client.get("/api/geospatial/sources/windy_webcams/credential-status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "windy-secret" not in response.text
