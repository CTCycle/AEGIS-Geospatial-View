from __future__ import annotations

from typing import Any

from server.domain.geospatial.registry import (
    CapabilityRegistrySnapshot,
    GeospatialManifestSnapshot,
)
from server.services.geospatial.manifest_loader import GeospatialManifestLoader


###############################################################################
class CapabilityRegistry:
    # -------------------------------------------------------------------------
    def __init__(
        self, *, manifest_loader: GeospatialManifestLoader | None = None
    ) -> None:
        loader = manifest_loader or GeospatialManifestLoader()
        self.catalog_snapshot = GeospatialManifestSnapshot.from_payload(
            loader.load_all()
        )
        self._snapshot = CapabilityRegistrySnapshot(
            providers=list(self.catalog_snapshot.providers),
            basemaps=list(self.catalog_snapshot.basemaps),
            overlays=list(self.catalog_snapshot.overlays),
            cameras=list(self.catalog_snapshot.cameras),
            transit=list(self.catalog_snapshot.transit),
            tools=list(self.catalog_snapshot.tools),
        )

    # -------------------------------------------------------------------------
    @classmethod
    def from_catalog_snapshot(
        cls, snapshot: GeospatialManifestSnapshot
    ) -> "CapabilityRegistry":
        registry = cls.__new__(cls)
        registry.catalog_snapshot = snapshot
        registry._snapshot = CapabilityRegistrySnapshot(
            providers=list(snapshot.providers),
            basemaps=list(snapshot.basemaps),
            overlays=list(snapshot.overlays),
            cameras=list(snapshot.cameras),
            transit=list(snapshot.transit),
            tools=list(snapshot.tools),
        )
        return registry

    # -------------------------------------------------------------------------
    def load_capabilities(self) -> CapabilityRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    @property
    def snapshot(self) -> CapabilityRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    def _ensure_snapshot(self) -> CapabilityRegistrySnapshot:
        return self._snapshot

    # -------------------------------------------------------------------------
    def list_basemaps(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().basemaps)

    # -------------------------------------------------------------------------
    def list_overlays(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().overlays)

    # -------------------------------------------------------------------------
    def list_cameras(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().cameras)

    # -------------------------------------------------------------------------
    def list_transit(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().transit)

    # -------------------------------------------------------------------------
    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._ensure_snapshot().tools)

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        normalized = str(capability_id).strip()
        if not normalized:
            return None
        snapshot = self._ensure_snapshot()
        for collection in (
            snapshot.basemaps,
            snapshot.overlays,
            snapshot.cameras,
            snapshot.transit,
            snapshot.tools,
        ):
            for item in collection:
                if str(item.get("id") or "") == normalized:
                    return dict(item)
        return None
