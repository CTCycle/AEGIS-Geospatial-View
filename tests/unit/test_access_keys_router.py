from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from AEGIS.server.api.access_keys import get_access_keys_service, router
from AEGIS.server.domain.access_keys import AccessKeyResponse
from AEGIS.server.services.access_keys import (
    AccessKeyNotFoundError,
    AccessKeysService,
    AccessKeyValidationError,
)


def _app(service: AccessKeysService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_access_keys_service] = lambda: service
    return TestClient(app)


def test_access_keys_router_status_codes_and_domain_exception_mappings(monkeypatch) -> None:
    response = AccessKeyResponse(
        id=1,
        provider="openai",
        is_active=True,
        fingerprint="fp",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_used_at=None,
    )

    service = AccessKeysService()
    monkeypatch.setattr(service, "create_key", lambda provider, access_key: response)
    monkeypatch.setattr(service, "list_keys", lambda provider: [response])
    monkeypatch.setattr(service, "activate_key", lambda key_id, provider: response)
    monkeypatch.setattr(service, "delete_key", lambda key_id, provider: None)

    client = _app(service)
    assert (
        client.post(
            "/access-keys", json={"provider": "openai", "access_key": "sk-value"}
        ).status_code
        == 201
    )
    assert client.get("/access-keys?provider=openai").status_code == 200
    assert client.put("/access-keys/1/activate?provider=openai").status_code == 200
    assert client.delete("/access-keys/1?provider=openai").status_code == 200


def test_access_keys_router_422_and_404_translation_paths(monkeypatch) -> None:
    service = AccessKeysService()
    monkeypatch.setattr(
        service,
        "create_key",
        lambda provider, access_key: (_ for _ in ()).throw(
            AccessKeyValidationError("bad provider")
        ),
    )
    monkeypatch.setattr(
        service,
        "activate_key",
        lambda key_id, provider: (_ for _ in ()).throw(AccessKeyNotFoundError("missing")),
    )
    monkeypatch.setattr(
        service,
        "delete_key",
        lambda key_id, provider: (_ for _ in ()).throw(AccessKeyNotFoundError("missing")),
    )
    monkeypatch.setattr(
        service,
        "list_keys",
        lambda provider: (_ for _ in ()).throw(AccessKeyValidationError("bad provider")),
    )

    client = _app(service)
    assert client.post("/access-keys", json={"provider": "x", "access_key": "k"}).status_code == 422
    assert client.get("/access-keys?provider=x").status_code == 422
    assert client.put("/access-keys/999/activate?provider=openai").status_code == 404
    assert client.delete("/access-keys/999?provider=openai").status_code == 404