from __future__ import annotations

import os
from typing import Any

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class GeospatialCatalogService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.runtime_registry = runtime_registry or RuntimeRegistry()

    # -------------------------------------------------------------------------
    def _descriptor(self, item: dict[str, Any], kind: str) -> dict[str, Any]:
        metadata = dict(item.get("metadata") or {})
        capability_id = str(item.get("id") or "")
        auth = dict(item.get("auth") or {})
        reliability = dict(item.get("reliability") or {})
        requires_credentials = bool(auth.get("required", False))
        capability_kind = str(item.get("capabilityKind") or kind)
        is_available = (
            self.runtime_registry.is_enabled(capability_id)
            and self.runtime_registry.credentials_present(capability_id)
        )
        return {
            "id": capability_id,
            "name": str(item.get("name") or capability_id),
            "kind": capability_kind,
            "type": str(item.get("type") or kind),
            "description": str(item.get("description") or ""),
            "provider": str(item.get("provider") or "unknown"),
            "requires_credentials": requires_credentials,
            "is_available": is_available,
            "supports_map": self.runtime_registry.supports_mode(capability_id, "map"),
            "supports_direct_text": self.runtime_registry.supports_mode(
                capability_id, "direct_text"
            ),
            "coverage": str(item.get("coverage") or "global"),
            "action_tags": list(metadata.get("action_tags") or []),
            "task_tags": list(metadata.get("task_tags") or []),
            "source_protocol": str(metadata.get("source_protocol") or ""),
            "data_format": str(metadata.get("data_format") or ""),
            "geometry_type": str(metadata.get("geometry_type") or ""),
            "queryable": bool(metadata.get("queryable", False)),
            "endpoint_health": str(reliability.get("status") or "unknown"),
            "auth_mode": str(auth.get("type") or "none"),
            "official_docs_url": "; ".join(
                str(value) for value in item.get("sourceOfficialDocs") or []
            ),
            "capability_kind": capability_kind,
            "rendering_mode": str(item.get("renderingMode") or ""),
            "reliability": reliability,
            "auth": auth,
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    def _provider_descriptor(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(item.get("metadata") or {})
        provider_id = str(item.get("id") or item.get("provider") or "unknown")
        auth = dict(item.get("auth") or {})
        reliability = dict(item.get("reliability") or {})
        requires_credentials = bool(auth.get("required", False))
        is_available = True
        if requires_credentials:
            env_name = self.runtime_registry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_id)
            has_saved_key = False
            try:
                has_saved_key = self.runtime_registry.credentials_repo.get_active(
                    provider=provider_id,
                    label="api_key",
                ) is not None
            except Exception:
                has_saved_key = False
            is_available = has_saved_key or bool(env_name and os.getenv(env_name, "").strip())
        return {
            "id": provider_id,
            "name": str(item.get("name") or provider_id),
            "kind": "provider",
            "type": "provider",
            "description": str(item.get("description") or ""),
            "provider": provider_id,
            "requires_credentials": requires_credentials,
            "is_available": is_available,
            "supports_map": "tile" in list(item.get("capabilities") or [])
            or "wms" in list(item.get("capabilities") or [])
            or "wmts" in list(item.get("capabilities") or [])
            or "imagery" in list(item.get("capabilities") or []),
            "supports_direct_text": "forecast" in list(item.get("capabilities") or [])
            or "point-insight" in list(item.get("capabilities") or [])
            or "poi" in list(item.get("capabilities") or []),
            "coverage": str(item.get("coverage") or "global"),
            "action_tags": list(metadata.get("action_tags") or []),
            "task_tags": list(metadata.get("task_tags") or []),
            "source_protocol": str(metadata.get("source_protocol") or ""),
            "data_format": str(metadata.get("data_format") or ""),
            "geometry_type": str(metadata.get("geometry_type") or ""),
            "queryable": bool(metadata.get("queryable", False)),
            "endpoint_health": str(reliability.get("status") or "unknown"),
            "auth_mode": str(auth.get("type") or "none"),
            "official_docs_url": "; ".join(
                str(value) for value in item.get("sourceOfficialDocs") or []
            ),
            "capability_kind": str(item.get("capabilityKind") or "metadata-only"),
            "rendering_mode": str(item.get("renderingMode") or ""),
            "reliability": reliability,
            "auth": auth,
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    def list_catalog(self) -> dict[str, list[dict[str, Any]]]:
        snapshot = self.capability_registry.load_capabilities()
        self.runtime_registry.build_snapshot()

        providers = [
            self._provider_descriptor(item) for item in snapshot.providers
        ]
        basemaps = [
            self._descriptor(item, "basemap") for item in self.capability_registry.list_basemaps()
        ]
        overlays = [
            self._descriptor(item, "overlay") for item in self.capability_registry.list_overlays()
        ]
        cameras = [
            self._descriptor(item, "camera-network")
            for item in self.capability_registry.list_cameras()
        ]
        transit = [
            self._descriptor(item, "transit")
            for item in self.capability_registry.list_transit()
        ]
        tools = [self._descriptor(item, "tool") for item in self.capability_registry.list_tools()]
        return {
            "capabilities": basemaps + overlays + cameras + transit + tools,
            "providers": providers,
            "basemaps": basemaps,
            "overlays": overlays,
            "cameras": cameras,
            "transit": transit,
            "tools": tools,
        }
