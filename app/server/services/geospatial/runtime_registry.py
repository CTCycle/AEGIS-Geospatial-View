from __future__ import annotations

import os
from typing import Any

from server.domain.geospatial.registry import RuntimeRegistrySnapshot
from server.repositories.credentials import CredentialRepository
from server.services.geospatial.manifest_loader import GeospatialManifestLoader


class RuntimeRegistry:
    CREDENTIAL_ENV_BY_PROVIDER = {
        "arcgis": "ARCGIS_API_KEY",
        "census": "CENSUS_API_KEY",
        "fred": "FRED_API_KEY",
        "geoapify": "GEOAPIFY_API_KEY",
        "google": "GOOGLE_API_KEY",
        "google_maps": "GOOGLE_MAPS_API_KEY",
        "nasa": "NASA_API_KEY",
        "nasa_firms": "NASA_API_KEY",
        "nrel": "NREL_API_KEY",
        "openaq": "OPENAQ_API_KEY",
        "openchargemap": "OPENCHARGEMAP_API_KEY",
        "openaip": "OPENAIP_API_KEY",
        "openai": "OPENAI_API_KEY",
        "opentripmap": "OPENTRIPMAP_API_KEY",
        "sentinel_hub": "SENTINEL_HUB_CLIENT_ID",
        "tomtom": "TOMTOM_API_KEY",
        "transitland": "TRANSITLAND_API_KEY",
        "windy_webcams": "WINDY_WEBCAMS_API_KEY",
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
        manifests: dict[str, dict[str, Any]] = {}
        for collection_name in ("providers", "basemaps", "overlays", "cameras", "transit", "tools"):
            for item in list(manifest.get(collection_name) or []):
                capability_id = str(item.get("id") or "").strip()
                if capability_id:
                    manifests[capability_id] = dict(item)
        self._snapshot = RuntimeRegistrySnapshot(profiles=profiles, manifests=manifests)
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
        manifest = self._ensure().manifests.get(str(capability_id), {})
        auth = manifest.get("auth") if isinstance(manifest, dict) else None
        auth_payload = auth if isinstance(auth, dict) else {}
        if not bool(auth_payload.get("required", False)):
            return True
        provider = str(auth_payload.get("providerKey") or "").strip().lower()
        if not provider:
            return False
        env_name = self.CREDENTIAL_ENV_BY_PROVIDER.get(provider)
        if not env_name:
            return False
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
