from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app

###############################################################################
def test_credential_status_does_not_return_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("WINDY_WEBCAMS_API_KEY", "windy-secret")
    client = TestClient(create_app())

    response = client.get("/api/geospatial/sources/windy_webcams/credential-status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "windy-secret" not in response.text
