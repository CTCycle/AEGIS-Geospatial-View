from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from AEGIS.server.repositories.credentials import CredentialRepository
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader


@dataclass(frozen=True)
class RuntimeRegistrySnapshot:
    profiles: dict[str, dict[str, Any]]


class RuntimeRegistry:
    CREDENTIAL_ENV_BY_PROVIDER = {
        "tomtom": "TOMTOM_API_KEY",
        "geoapify": "GEOAPIFY_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "google_maps": "GOOGLE_MAPS_API_KEY",
        "arcgis": "ARCGIS_API_KEY",
    }

    def __init__(
        self,
        *,
        manifest_loader: GeospatialManifestLoader | None = None,
        credentials_repo: CredentialRepository | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self._credentials_repo = credentials_repo
        self._snapshot: RuntimeRegistrySnapshot | None = None

    @property
    def credentials_repo(self) -> CredentialRepository:
        if self._credentials_repo is None:
            self._credentials_repo = CredentialRepository()
        return self._credentials_repo

    def build_snapshot(self) -> RuntimeRegistrySnapshot:
        manifest = self.manifest_loader.load_all()
        profiles = {
            str(item.get("capability_id")): dict(item)
            for item in list(manifest.get("runtime_profiles") or [])
            if str(item.get("capability_id") or "").strip()
        }
        self._snapshot = RuntimeRegistrySnapshot(profiles=profiles)
        return self._snapshot

    def _ensure(self) -> RuntimeRegistrySnapshot:
        return self._snapshot or self.build_snapshot()

    def _profile(self, capability_id: str) -> dict[str, Any] | None:
        return self._ensure().profiles.get(str(capability_id))

    def is_enabled(self, capability_id: str) -> bool:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return False
        return bool(profile.get("enabled_by_default", False))

    def credentials_present(self, capability_id: str) -> bool:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return False
        provider = str(profile.get("credential_provider") or "").strip().lower()
        if not provider:
            return True
        env_name = self.CREDENTIAL_ENV_BY_PROVIDER.get(provider)
        if not env_name:
            return True
        if os.getenv(env_name, "").strip():
            return True
        try:
            return self.credentials_repo.get_active(provider=provider, label="api_key") is not None
        except Exception:
            return False

    def supports_mode(self, capability_id: str, mode: str) -> bool:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return False
        normalized_mode = str(mode).strip().lower()
        if normalized_mode == "map":
            return bool(profile.get("supports_map", False))
        if normalized_mode in {"direct_text", "text"}:
            return bool(profile.get("supports_direct_text", False))
        return False

    def provider_health(self, capability_id: str) -> str:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return "unknown"
        if not self.is_enabled(capability_id):
            return "disabled"
        if not self.credentials_present(capability_id):
            return "missing_credentials"
        return "healthy"

    def handler_name(self, capability_id: str) -> str | None:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return None
        value = profile.get("handler_name")
        if not isinstance(value, str):
            return None
        return value.strip() or None

    def coverage_policy(self, capability_id: str) -> str:
        profile = self._profile(capability_id)
        if not isinstance(profile, dict):
            return "global"
        return str(profile.get("coverage_policy") or "global")
