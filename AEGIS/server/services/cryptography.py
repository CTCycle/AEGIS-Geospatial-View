from __future__ import annotations

import base64
import os
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from AEGIS.server.configurations import server_settings

# -------------------------------------------------------------------------
def _derive_fernet_key(master_key: str) -> bytes:
    digest = hashlib.sha256(master_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

# -------------------------------------------------------------------------
def _load_access_key_fernet() -> Fernet:
    raw_key = (os.getenv("ACCESS_KEY_ENCRYPTION_KEY") or "").strip()
    if not raw_key:
        raise RuntimeError("ACCESS_KEY_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("ACCESS_KEY_ENCRYPTION_KEY is invalid") from exc


def encrypt_access_key(plaintext: str) -> str:
    normalized = plaintext.strip()
    if not normalized:
        raise ValueError("Access key must not be empty")
    return _load_access_key_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")


def decrypt_access_key(ciphertext: str) -> str:
    normalized = ciphertext.strip()
    if not normalized:
        raise ValueError("Access key must not be empty")
    fernet = _load_access_key_fernet()
    try:
        return fernet.decrypt(normalized.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Encrypted access key is invalid") from exc
    except Exception as exc:
        raise RuntimeError("Failed to decrypt access key") from exc


def build_access_key_fingerprint(ciphertext: str) -> str:
    return hashlib.sha256(ciphertext.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EncryptedSecret:
    value: str
    key_version: str


class CredentialEncryptionService:
    def __init__(
        self,
        *,
        master_key: str | None = None,
        key_version: str | None = None,
    ) -> None:
        self.master_key = master_key or server_settings.credential_master_key
        self.key_version = key_version or server_settings.credential_key_version
        self.fernet = Fernet(_derive_fernet_key(self.master_key))

    def encrypt(self, raw_value: str) -> EncryptedSecret:
        token = self.fernet.encrypt(raw_value.encode("utf-8")).decode("utf-8")
        return EncryptedSecret(value=token, key_version=self.key_version)

    def decrypt(self, encrypted_value: str) -> str:
        try:
            decrypted = self.fernet.decrypt(encrypted_value.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError("Credential cannot be decrypted with current key.") from exc
        return decrypted.decode("utf-8")

    def mask(self, encrypted_value: str | None) -> str | None:
        if not encrypted_value:
            return None
        return "••••••••"
