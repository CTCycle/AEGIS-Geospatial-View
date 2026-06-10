from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from server.domain.crypto import EncryptedSecret
from server.repositories.credential_material import (
    DEFAULT_KEY_PURPOSE,
    CredentialEncryptionMaterialRepository,
)


###############################################################################
def _load_fernet_from_material(key_material: str) -> Fernet:
    normalized = str(key_material or "").strip()
    if not normalized:
        raise RuntimeError("Encryption key material is missing")
    return Fernet(normalized.encode("utf-8"))


###############################################################################
class CredentialEncryptionService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        material_repo: CredentialEncryptionMaterialRepository | None = None,
    ) -> None:
        self._material_repo = material_repo or CredentialEncryptionMaterialRepository()
        self._material = self._material_repo.get_active_material(DEFAULT_KEY_PURPOSE)
        if self._material is None:
            raise RuntimeError(
                "No active credential encryption material found. "
                "Ensure the database is initialized."
            )
        self._fernet = _load_fernet_from_material(self._material.key_material)

    # -------------------------------------------------------------------------
    def encrypt(self, raw_value: str) -> EncryptedSecret:
        token = self._fernet.encrypt(raw_value.encode("utf-8")).decode("utf-8")
        return EncryptedSecret(value=token, key_version=self._material.key_version)

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        try:
            decrypted = self._fernet.decrypt(encrypted_value.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError(
                "Credential cannot be decrypted with current key."
            ) from exc
        return decrypted.decode("utf-8")

    # -------------------------------------------------------------------------
    def decrypt_with_key_version(
        self, encrypted_value: str, key_version: int
    ) -> str:
        if key_version == self._material.key_version:
            return self.decrypt(encrypted_value)
        material = self._material_repo.get_material_by_version(key_version)
        if material is None:
            raise ValueError(
                f"Encryption material for version {key_version} is not available."
            )
        fernet = _load_fernet_from_material(material.key_material)
        try:
            decrypted = fernet.decrypt(encrypted_value.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError(
                "Credential cannot be decrypted with the stored key version."
            ) from exc
        return decrypted.decode("utf-8")

    # -------------------------------------------------------------------------
    def mask(self, encrypted_value: str | None) -> str | None:
        if not encrypted_value:
            return None
        return "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
