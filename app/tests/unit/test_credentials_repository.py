from __future__ import annotations

from server.repositories.credentials import CredentialRepository

###############################################################################
def test_credentials_repository_upsert_and_lookup(sqlite_backend) -> None:
    repository = CredentialRepository(sqlite_backend)
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
