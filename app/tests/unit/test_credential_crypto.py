from __future__ import annotations

from server.services.cryptography import CredentialEncryptionService


def test_credential_crypto_roundtrip() -> None:
    service = CredentialEncryptionService(
        master_key="unit-test-master-key", key_version="v1"
    )
    encrypted = service.encrypt("secret-value")
    assert encrypted.value
    assert encrypted.key_version == "v1"
    decrypted = service.decrypt(encrypted.value)
    assert decrypted == "secret-value"
    assert service.mask(encrypted.value) == "••••••••"
