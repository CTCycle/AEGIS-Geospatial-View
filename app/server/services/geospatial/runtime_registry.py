from __future__ import annotations

from server.common.typing import is_json_object, json_object

from typing import Any

from server.domain.geospatial.registry import (
    GeospatialManifestSnapshot,
    RuntimeRegistrySnapshot,
)
from server.services.geospatial.credential_resolver import (
    GEOSPATIAL_CREDENTIAL_ENV_BY_PROVIDER,
    CredentialStore,
    GeospatialCredentialResolver,
)
from server.services.geospatial.manifest_loader import GeospatialManifestLoader


###############################################################################
class RuntimeRegistry:
    CREDENTIAL_ENV_BY_PROVIDER = GEOSPATIAL_CREDENTIAL_ENV_BY_PROVIDER

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        catalog_snapshot: GeospatialManifestSnapshot | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        credentials_repo: CredentialStore | None = None,
        credential_resolver: GeospatialCredentialResolver | None = None,
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
        return bool(profile.get("enabled_by_default", False))

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
