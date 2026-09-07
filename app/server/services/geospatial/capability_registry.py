from __future__ import annotations

from typing import Any, cast

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

    # -------------------------------------------------------------------------
    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        """Return normalized provider-neutral facts for deterministic routing."""

        capability = self.get_capability(capability_id) or {}
        raw_value: object = capability.get("executionContract") or capability.get(
            "execution_contract"
        )
        if not isinstance(raw_value, dict):
            metadata_value: object = capability.get("metadata")
            metadata = (
                cast(dict[str, Any], metadata_value)
                if isinstance(metadata_value, dict)
                else {}
            )
            raw_value = metadata.get("execution_contract")
        raw: dict[str, Any] = (
            cast(dict[str, Any], raw_value)
            if isinstance(raw_value, dict)
            else {}
        )
        list_fields = (
            "supported_operations",
            "supported_scope_kinds",
            "temporal_modes",
            "temporal_windows",
            "supported_aggregations",
            "required_inputs",
            "limitations",
            "fallback_ids",
        )
        contract: dict[str, Any] = {
            field: [str(item).strip() for item in raw.get(field, []) if str(item).strip()]
            if isinstance(raw.get(field), list)
            else []
            for field in list_fields
        }
        contract["output_geometry_type"] = (
            str(raw.get("output_geometry_type")).strip()
            if raw.get("output_geometry_type") is not None
            else None
        )
        render_support = str(raw.get("render_support") or "none").strip().casefold()
        contract["render_support"] = (
            render_support
            if render_support in {"vector", "raster", "metadata_only", "none"}
            else "none"
        )
        contract["coverage"] = (
            str(raw.get("coverage")).strip() if raw.get("coverage") is not None else None
        )
        return contract
