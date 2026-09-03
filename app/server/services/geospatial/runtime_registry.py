from __future__ import annotations

from server.common.typing import is_json_object, json_object

import os
from typing import Any

from server.domain.geospatial.registry import (
    GeospatialManifestSnapshot,
    RuntimeRegistrySnapshot,
)
from server.services.geospatial.credential_resolver import (
    CredentialStore,
    GeospatialCredentialResolver,
)
from server.services.geospatial.manifest_loader import GeospatialManifestLoader


###############################################################################
class RuntimeRegistry:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        catalog_snapshot: GeospatialManifestSnapshot | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        credentials_repo: CredentialStore | None = None,
        credential_resolver: GeospatialCredentialResolver | None = None,
        allow_restricted_sources: bool | None = None,
    ) -> None:
        loader = manifest_loader or GeospatialManifestLoader()
        self.catalog_snapshot = (
            catalog_snapshot
            or GeospatialManifestSnapshot.from_payload(loader.load_all())
        )
        self._credentials_repo = credentials_repo
        self._credential_resolver = credential_resolver or GeospatialCredentialResolver(
            credentials_repo=credentials_repo,
        )
        self.allow_restricted_sources = (
            allow_restricted_sources
            if allow_restricted_sources is not None
            else _read_boolean_env("AEGIS_ALLOW_RESTRICTED_SOURCES")
        )
        self._snapshot = self._build_snapshot(self.catalog_snapshot)

    # -------------------------------------------------------------------------
    @property
    def credentials_repo(self) -> CredentialStore | None:
        return self._credentials_repo

    # -------------------------------------------------------------------------
    @property
    def credential_resolver(self) -> GeospatialCredentialResolver:
        return self._credential_resolver

    # -------------------------------------------------------------------------
    def build_snapshot(self) -> RuntimeRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    @property
    def snapshot(self) -> RuntimeRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_snapshot(
        catalog_snapshot: GeospatialManifestSnapshot,
    ) -> RuntimeRegistrySnapshot:
        profiles = {
            str(item.get("capability_id")): dict(item)
            for item in catalog_snapshot.runtime_profiles
            if str(item.get("capability_id") or "").strip()
        }
        manifests: dict[str, dict[str, Any]] = {}
        for collection_name in (
            "providers",
            "basemaps",
            "overlays",
            "cameras",
            "transit",
            "tools",
        ):
            for item in getattr(catalog_snapshot, collection_name):
                capability_id = str(item.get("id") or "").strip()
                if capability_id:
                    manifests[capability_id] = dict(item)
        return RuntimeRegistrySnapshot(profiles=profiles, manifests=manifests)

    # -------------------------------------------------------------------------
    def _ensure(self) -> RuntimeRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    def _profile(self, capability_id: str) -> dict[str, Any] | None:
        return self._ensure().profiles.get(str(capability_id))

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return False
        restricted_public = self._is_restricted_public_source(capability_id)
        if restricted_public and not self.allow_restricted_sources:
            return False
        if bool(profile.get("enabled_by_default", False)):
            return True
        return bool(profile.get("manual_toggle", False)) and restricted_public

    # -------------------------------------------------------------------------
    def _is_restricted_public_source(self, capability_id: str) -> bool:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return False
        if str(profile.get("health_policy") or "").strip().casefold() != (
            "restricted_usage_opt_in"
        ):
            return False
        manifest = self._ensure().manifests.get(str(capability_id))
        if not is_json_object(manifest):
            return False
        license_data = json_object(manifest.get("license"))
        restricted = (
            str(license_data.get("commercialUse") or "").strip().casefold()
            == "restricted"
        )
        auth = json_object(manifest.get("auth"))
        return restricted and not bool(auth.get("required", False))

    # -------------------------------------------------------------------------
    def credentials_present(self, capability_id: str) -> bool:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return False
        manifest = self._ensure().manifests.get(str(capability_id), {})
        auth = manifest.get("auth") if is_json_object(manifest) else None
        auth_payload = json_object(auth)
        if not bool(auth_payload.get("required", False)):
            return True
        provider = str(auth_payload.get("providerKey") or "").strip().lower()
        if not provider:
            return False
        return self._credential_resolver.is_configured(provider)

    # -------------------------------------------------------------------------
    def provider_credentials_present(self, provider_id: str) -> bool:
        return self._credential_resolver.is_configured(provider_id)

    # -------------------------------------------------------------------------
    def supports_mode(self, capability_id: str, mode: str) -> bool:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return False
        normalized_mode = str(mode).strip().lower()
        if normalized_mode == "map":
            return bool(profile.get("supports_map", False))
        if normalized_mode in {"direct_text", "text"}:
            return bool(profile.get("supports_direct_text", False))
        return False

    # -------------------------------------------------------------------------
    def provider_health(self, capability_id: str) -> str:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return "unknown"
        if not self.is_enabled(capability_id):
            return "disabled"
        if not self.credentials_present(capability_id):
            return "missing_credentials"
        return "healthy"

    # -------------------------------------------------------------------------
    def handler_name(self, capability_id: str) -> str | None:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return None
        value = profile.get("handler_name")
        if not isinstance(value, str):
            return None
        return value.strip() or None

    # -------------------------------------------------------------------------
    def coverage_policy(self, capability_id: str) -> str:
        profile = self._profile(capability_id)
        if not is_json_object(profile):
            return "global"
        return str(profile.get("coverage_policy") or "global")


###############################################################################
def _read_boolean_env(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}
