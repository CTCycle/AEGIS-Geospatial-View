from __future__ import annotations

from typing import Any

from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry


class GeospatialCatalogService:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.runtime_registry = runtime_registry or RuntimeRegistry()

    def _descriptor(self, item: dict[str, Any], kind: str) -> dict[str, Any]:
        metadata = dict(item.get("metadata") or {})
        capability_id = str(item.get("id") or "")
        requires_credentials = bool(item.get("provider") in {"tomtom", "geoapify"})
        is_available = (
            self.runtime_registry.is_enabled(capability_id)
            and self.runtime_registry.credentials_present(capability_id)
        )
        return {
            "id": capability_id,
            "name": str(item.get("name") or capability_id),
            "kind": kind,
            "provider": str(item.get("provider") or "unknown"),
            "requires_credentials": requires_credentials,
            "is_available": is_available,
            "supports_map": self.runtime_registry.supports_mode(capability_id, "map"),
            "supports_direct_text": self.runtime_registry.supports_mode(
                capability_id, "direct_text"
            ),
            "coverage": str(item.get("coverage") or "global"),
            "intent_tags": list(metadata.get("intent_tags") or []),
            "task_tags": list(metadata.get("task_tags") or []),
            "metadata": metadata,
        }

    def list_catalog(self) -> dict[str, list[dict[str, Any]]]:
        self.capability_registry.load_capabilities()
        self.runtime_registry.build_snapshot()

        basemaps = [
            self._descriptor(item, "basemap") for item in self.capability_registry.list_basemaps()
        ]
        overlays = [
            self._descriptor(item, "overlay") for item in self.capability_registry.list_overlays()
        ]
        tools = [self._descriptor(item, "tool") for item in self.capability_registry.list_tools()]
        return {"capabilities": basemaps + overlays + tools}
