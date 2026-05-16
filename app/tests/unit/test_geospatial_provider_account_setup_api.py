from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app


def test_provider_account_setup_api_returns_setup_list() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    assert any(item["provider_id"] == "geoapify" for item in response.json())


def test_provider_account_setup_api_returns_one_setup() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/providers/geoapify/account-setup")

    assert response.status_code == 200
    assert response.json()["provider_id"] == "geoapify"


def test_provider_account_setup_api_unknown_provider_returns_not_found() -> None:
    client = TestClient(create_app())

    response = client.get("/api/geospatial/providers/missing-provider/account-setup")

    assert response.status_code == 404


def test_provider_credentials_validate_returns_result() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/geospatial/providers/geoapify/credentials/validate",
        json={"credentials": {}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "invalid"


def test_provider_credentials_validate_does_not_persist_credentials() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/geospatial/providers/openmeteo/credentials/validate",
        json={"credentials": {"api_key": "secret-key"}},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    status = client.get("/api/geospatial/sources/geoapify/credential-status")
    assert "secret-key" not in status.text
