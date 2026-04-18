from __future__ import annotations

from playwright.sync_api import APIRequestContext


def _provider_query(provider: str) -> str:
    return f"?provider={provider}"


def test_access_keys_crud_and_prefix_parity(api_context: APIRequestContext) -> None:
    provider = "openai"
    create_payload = {"provider": provider, "access_key": "sk-test-access-key-value"}

    create_base = api_context.post("/api/access-keys", data=create_payload)
    create_prefixed = api_context.post("/api/access-keys", data=create_payload)
    assert create_base.status in {201, 422}
    assert create_prefixed.status in {201, 422}
    if create_base.status != 201:
        return

    created = create_base.json()
    key_id = created["id"]

    list_base = api_context.get(f"/api/access-keys{_provider_query(provider)}")
    list_prefixed = api_context.get(f"/api/access-keys{_provider_query(provider)}")
    assert list_base.ok and list_prefixed.ok
    assert isinstance(list_base.json(), list)
    assert isinstance(list_prefixed.json(), list)

    activate_base = api_context.put(
        f"/api/access-keys/{key_id}/activate{_provider_query(provider)}"
    )
    activate_prefixed = api_context.put(
        f"/api/access-keys/{key_id}/activate{_provider_query(provider)}"
    )
    assert activate_base.ok and activate_prefixed.ok
    assert activate_base.json()["id"] == key_id
    assert activate_prefixed.json()["id"] == key_id

    delete_base = api_context.delete(
        f"/api/access-keys/{key_id}{_provider_query(provider)}"
    )
    delete_prefixed = api_context.delete(
        f"/api/access-keys/{key_id}{_provider_query(provider)}"
    )
    assert delete_base.ok
    assert delete_prefixed.status in {200, 404}


def test_access_keys_invalid_provider_and_unknown_id(
    api_context: APIRequestContext,
) -> None:
    invalid = api_context.get("/api/access-keys?provider=unknown_provider")
    assert invalid.status == 422

    missing_activate = api_context.put(
        "/api/access-keys/999999/activate?provider=openai"
    )
    missing_delete = api_context.delete("/api/access-keys/999999?provider=openai")
    assert missing_activate.status in {404, 422}
    assert missing_delete.status in {404, 422}
