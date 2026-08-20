from __future__ import annotations

from server.common.typing import is_json_object, json_object

from typing import Any

from server.domain.geospatial.registry import RuntimeRegistrySnapshot
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
        manifest_loader: GeospatialManifestLoader,
        credentials_repo: CredentialStore | None = None,
        credential_resolver: GeospatialCredentialResolver | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader
        self._credentials_repo = credentials_repo
        self._credential_resolver = credential_resolver or GeospatialCredentialResolver(
            credentials_repo=credentials_repo,
        )
        self._snapshot: RuntimeRegistrySnapshot | None = None

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

    # -------------------------------------------------------------------------
    def _ensure(self) -> RuntimeRegistrySnapshot:
        return self._snapshot or self.build_snapshot()

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
