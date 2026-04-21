from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader


@dataclass(frozen=True)
class CapabilityRegistrySnapshot:
    providers: list[dict[str, Any]]
    basemaps: list[dict[str, Any]]
    overlays: list[dict[str, Any]]
    tools: list[dict[str, Any]]


class CapabilityRegistry:
    def __init__(self, *, manifest_loader: GeospatialManifestLoader | None = None) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self._snapshot: CapabilityRegistrySnapshot | None = None

    def load_capabilities(self) -> CapabilityRegistrySnapshot:
        manifest = self.manifest_loader.load_all()
        self._snapshot = CapabilityRegistrySnapshot(
            providers=list(manifest.get("providers") or []),
            basemaps=list(manifest.get("basemaps") or []),
            overlays=list(manifest.get("overlays") or []),
            tools=list(manifest.get("tools") or []),
        )
        return self._snapshot

    def _ensure_snapshot(self) -> CapabilityRegistrySnapshot:
        return self._snapshot or self.load_capabilities()

    def list_basemaps(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().basemaps)

    def list_overlays(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().overlays)

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().tools)

    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        normalized = str(capability_id).strip()
        if not normalized:
            return None
        snapshot = self._ensure_snapshot()
        for collection in (snapshot.basemaps, snapshot.overlays, snapshot.tools):
            for item in collection:
                if str(item.get("id") or "") == normalized:
                    return dict(item)
        return None
