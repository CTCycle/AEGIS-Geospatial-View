from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from AEGIS.server.api.access_keys import router, serializer


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_access_keys_router_status_codes_and_domain_exception_mappings(
    monkeypatch,
) -> None:
    class Row:
        id = 1
        provider = "openai"
        is_active = True
        fingerprint = "fp"
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)
        last_used_at = None

    monkeypatch.setattr(serializer, "create_key", lambda provider, access_key: Row())
    monkeypatch.setattr(serializer, "list_keys", lambda provider: [Row()])
    monkeypatch.setattr(serializer, "activate_key", lambda key_id, provider: Row())
    monkeypatch.setattr(serializer, "delete_key", lambda key_id, provider: None)

    client = _app()
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
    monkeypatch.setattr(
        serializer,
        "create_key",
        lambda provider, access_key: (_ for _ in ()).throw(ValueError("bad provider")),
    )
    monkeypatch.setattr(
        serializer,
        "activate_key",
        lambda key_id, provider: (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(
        serializer,
        "delete_key",
        lambda key_id, provider: (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(
        serializer,
        "list_keys",
        lambda provider: (_ for _ in ()).throw(ValueError("bad provider")),
    )

    client = _app()
    assert (
        client.post(
            "/access-keys", json={"provider": "x", "access_key": "k"}
        ).status_code
        == 422
    )
    assert client.get("/access-keys?provider=x").status_code == 422
    assert client.put("/access-keys/999/activate?provider=openai").status_code == 404
    assert client.delete("/access-keys/999?provider=openai").status_code == 404
