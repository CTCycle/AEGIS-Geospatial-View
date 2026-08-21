from __future__ import annotations

from typing import Any

from server.common.typing import json_array, json_object

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class GeospatialCatalogService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

    # -------------------------------------------------------------------------
    def _descriptor(self, item: dict[str, Any], kind: str) -> dict[str, Any]:
        metadata = json_object(item.get("metadata"))
        capability_id = str(item.get("id") or "")
        auth = json_object(item.get("auth"))
        reliability = json_object(item.get("reliability"))
        requires_credentials = bool(auth.get("required", False))
        capability_kind = str(item.get("capabilityKind") or kind)
        is_available = (
            self.runtime_registry.is_enabled(capability_id)
            and self.runtime_registry.credentials_present(capability_id)
        )
        descriptor = {
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
                str(value) for value in json_array(item.get("sourceOfficialDocs"))
            ),
            "capability_kind": capability_kind,
            "rendering_mode": str(item.get("renderingMode") or ""),
            "reliability": reliability,
            "auth": auth,
            "metadata": metadata,
        }
        if kind == "basemap":
            descriptor["render"] = self._safe_basemap_render_descriptor(
                metadata=metadata,
                auth=auth,
            )
        return descriptor

    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_basemap_render_descriptor(
        *, metadata: dict[str, Any], auth: dict[str, Any]
    ) -> dict[str, Any]:
        """Expose only public render data needed by the map selector."""

        if bool(auth.get("required")):
            return {
                "status": "unavailable",
                "reason": "credentials_required",
            }
        tile_url = next(
            (
                str(metadata.get(key)).strip()
                for key in ("tile_url", "tile_url_template", "url_template")
                if isinstance(metadata.get(key), str) and str(metadata.get(key)).strip()
            ),
            None,
        )
        style_url = (
            str(metadata.get("style_url")).strip()
            if isinstance(metadata.get("style_url"), str)
            and str(metadata.get("style_url")).strip()
            else None
        )
        if tile_url is None and style_url is None:
            return {
                "status": "unavailable",
                "reason": "render_descriptor_missing",
            }
        return {
            "status": "available",
            "tile_url": tile_url,
            "style_url": style_url,
            "attribution": str(metadata.get("attribution") or ""),
        }

    # -------------------------------------------------------------------------
    def _provider_descriptor(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = json_object(item.get("metadata"))
        provider_id = str(item.get("id") or item.get("provider") or "unknown")
        auth = json_object(item.get("auth"))
        reliability = json_object(item.get("reliability"))
        requires_credentials = bool(auth.get("required", False))
        is_available = True
        if requires_credentials:
            is_available = self.runtime_registry.provider_credentials_present(provider_id)
        return {
            "id": provider_id,
            "name": str(item.get("name") or provider_id),
            "kind": "provider",
            "type": "provider",
            "description": str(item.get("description") or ""),
            "provider": provider_id,
            "requires_credentials": requires_credentials,
            "is_available": is_available,
            "supports_map": "tile" in json_array(item.get("capabilities"))
            or "wms" in json_array(item.get("capabilities"))
            or "wmts" in json_array(item.get("capabilities"))
            or "imagery" in json_array(item.get("capabilities")),
            "supports_direct_text": "forecast" in json_array(item.get("capabilities"))
            or "point-insight" in json_array(item.get("capabilities"))
            or "poi" in json_array(item.get("capabilities")),
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
                str(value) for value in json_array(item.get("sourceOfficialDocs"))
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
