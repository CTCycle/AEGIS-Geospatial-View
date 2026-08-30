from __future__ import annotations

import os
from typing import Any, Protocol

###############################################################################
GEOSPATIAL_CREDENTIAL_ENV_BY_PROVIDER: dict[str, str] = {
    "arcgis": "ARCGIS_API_KEY",
    "census": "CENSUS_API_KEY",
    "google": "GOOGLE_API_KEY",
    "google_maps": "GOOGLE_MAPS_API_KEY",
    "mapillary": "MAPILLARY_ACCESS_TOKEN",
    "nasa": "NASA_API_KEY",
    "nasa_firms": "NASA_API_KEY",
    "openaq": "OPENAQ_API_KEY",
    "openchargemap": "OPENCHARGEMAP_API_KEY",
    "openaip": "OPENAIP_API_KEY",
    "openai": "OPENAI_API_KEY",
    "opentripmap": "OPENTRIPMAP_API_KEY",
    "sentinel_hub": "SENTINEL_HUB_CLIENT_ID",
    "tomtom": "TOMTOM_API_KEY",
    "windy_webcams": "WINDY_WEBCAMS_API_KEY",
}


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
    """Resolve saved geospatial credentials before environment fallbacks."""

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
    @staticmethod
    def environment_name(provider_id: str) -> str | None:
        return GEOSPATIAL_CREDENTIAL_ENV_BY_PROVIDER.get(
            str(provider_id).strip().lower()
        )

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

        environment_name = self.environment_name(normalized_provider)
        if environment_name is None:
            return None
        value = os.getenv(environment_name, "").strip()
        return value or None

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
    "GEOSPATIAL_CREDENTIAL_ENV_BY_PROVIDER",
    "GeospatialCredentialResolutionError",
    "GeospatialCredentialResolver",
]
