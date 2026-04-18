from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from AEGIS.server.services.cryptography import (
    build_access_key_fingerprint,
    decrypt_access_key,
    encrypt_access_key,
)


def test_access_key_crypto_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode("utf-8")

    class _FakeResult:
        @staticmethod
        def scalars():
            return _FakeResult()

        @staticmethod
        def first():
            class _Record:
                value = key

            return _Record()

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def execute(_statement):
            return _FakeResult()

    class _FakeBackend:
        @staticmethod
        def session():
            return _FakeSession()

    class _FakeDatabase:
        backend = _FakeBackend()

    monkeypatch.setattr(
        "AEGIS.server.services.cryptography.get_database", lambda: _FakeDatabase()
    )
    ciphertext = encrypt_access_key("  sk-secret-value  ")
    assert ciphertext
    assert decrypt_access_key(ciphertext) == "sk-secret-value"
    assert build_access_key_fingerprint(ciphertext)


def test_access_key_crypto_requires_database_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResult:
        @staticmethod
        def scalars():
            return _FakeResult()

        @staticmethod
        def first():
            return None

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def execute(_statement):
            return _FakeResult()

    class _FakeBackend:
        @staticmethod
        def session():
            return _FakeSession()

    class _FakeDatabase:
        backend = _FakeBackend()

    monkeypatch.setattr(
        "AEGIS.server.services.cryptography.get_database", lambda: _FakeDatabase()
    )
    with pytest.raises(
        RuntimeError, match="Database access key encryption secret is not configured"
    ):
        encrypt_access_key("sk-secret-value")
