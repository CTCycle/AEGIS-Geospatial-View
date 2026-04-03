from __future__ import annotations

from AEGIS.server.repositories.credentials import CredentialRepository


def test_credentials_repository_upsert_and_lookup() -> None:
    repository = CredentialRepository()
    record = repository.upsert(
        provider="openai",
        label="api_key",
        encrypted_value="encrypted-token",
        key_version="v1",
    )
    assert record.provider == "openai"
    loaded = repository.get_active(provider="openai", label="api_key")
    assert loaded is not None
    assert loaded.encrypted_value == "encrypted-token"
