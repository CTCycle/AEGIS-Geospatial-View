from __future__ import annotations

from typing import Any, Protocol


###############################################################################
class CredentialStore(Protocol):
    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str) -> Any:
        """Return the active encrypted credential record, if present."""

    # -------------------------------------------------------------------------
    def mark_used(self, *, provider: str, label: str) -> None:
        """Record that a stored credential was used."""


###############################################################################
class CredentialDecryptor(Protocol):
    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt a stored credential value."""
        ...


###############################################################################
class GeospatialCredentialResolutionError(RuntimeError):
    """Raised when a saved geospatial credential cannot be used."""


###############################################################################
class GeospatialCredentialResolver:
    """Resolve credentials exclusively from encrypted SQLite storage."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        credentials_repo: CredentialStore | None = None,
        crypto_service: CredentialDecryptor | None = None,
    ) -> None:
        self._credentials_repo = credentials_repo
        self._crypto_service = crypto_service

    # -------------------------------------------------------------------------
    @property
    def credentials_repo(self) -> CredentialStore | None:
        return self._credentials_repo

    # -------------------------------------------------------------------------
    def resolve(
        self,
        provider_id: str,
        *,
        label: str = "api_key",
        mark_used: bool = False,
    ) -> str | None:
        normalized_provider = str(provider_id).strip().lower()
        normalized_label = label.strip().casefold()
        credential = self._get_saved_credential(
            provider=normalized_provider,
            label=normalized_label,
        )
        if credential is not None:
            if self._crypto_service is None:
                raise GeospatialCredentialResolutionError(
                    "A credential decryption service is required for saved credentials."
                )
            encrypted_value = getattr(credential, "encrypted_value", None)
            if not isinstance(encrypted_value, str) or not encrypted_value.strip():
                raise GeospatialCredentialResolutionError(
                    f"Saved credentials for '{normalized_provider}' are invalid."
                )
            try:
                value = self._crypto_service.decrypt(encrypted_value)
            except ValueError as exc:
                raise GeospatialCredentialResolutionError(
                    f"Saved credentials for '{normalized_provider}' cannot be decrypted."
                ) from exc
            normalized_value = value.strip()
            if not normalized_value:
                raise GeospatialCredentialResolutionError(
                    f"Saved credentials for '{normalized_provider}' are empty."
                )
            if mark_used and self._credentials_repo is not None:
                self._credentials_repo.mark_used(
                    provider=normalized_provider,
                    label=normalized_label,
                )
            return normalized_value

        return None

    # -------------------------------------------------------------------------
    def is_configured(self, provider_id: str, *, label: str = "api_key") -> bool:
        normalized_provider = str(provider_id).strip().lower()
        normalized_label = label.strip().casefold()
        credential = self._get_saved_credential(
            provider=normalized_provider,
            label=normalized_label,
        )
        if credential is not None:
            if self._crypto_service is None:
                return True
            try:
                return bool(
                    self.resolve(
                        normalized_provider,
                        label=normalized_label,
                        mark_used=False,
                    )
                )
            except GeospatialCredentialResolutionError:
                return False
        return (
            self.resolve(
                normalized_provider,
                label=normalized_label,
                mark_used=False,
            )
            is not None
        )

    # -------------------------------------------------------------------------
    def _get_saved_credential(self, *, provider: str, label: str) -> Any | None:
        if self._credentials_repo is None:
            return None
        return self._credentials_repo.get_active(provider=provider, label=label)


__all__ = [
    "CredentialDecryptor",
    "CredentialStore",
    "GeospatialCredentialResolutionError",
    "GeospatialCredentialResolver",
]
