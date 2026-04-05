from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from AEGIS.server.services.cryptography import (
    build_access_key_fingerprint,
    decrypt_access_key,
    encrypt_access_key,
)


def test_access_key_crypto_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCESS_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    ciphertext = encrypt_access_key("  sk-secret-value  ")
    assert ciphertext
    assert decrypt_access_key(ciphertext) == "sk-secret-value"
    assert build_access_key_fingerprint(ciphertext)


def test_access_key_crypto_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCESS_KEY_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ACCESS_KEY_ENCRYPTION_KEY is not configured"):
        encrypt_access_key("sk-secret-value")
