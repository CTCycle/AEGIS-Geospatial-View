from __future__ import annotations

import re
from typing import Any, cast

from server.common.typing import json_object
from server.domain.geospatial.registry import (
    CapabilityRegistrySnapshot,
    GeospatialManifestSnapshot,
)
from server.services.geospatial.manifest_loader import GeospatialManifestLoader

###############################################################################
def normalized_execution_contract(capability: dict[str, Any]) -> dict[str, Any]:
    """Return explicit or conservatively inferred execution semantics.

    Older catalog entries predate ``executionContract`` but still declare the
    geometry, capability kind, and retrieval behavior needed for a bounded
    routing decision.  Infer only those facts from typed metadata; an explicit
    contract, including an explicitly empty one, remains authoritative.
    """

    metadata = json_object(capability.get("metadata"))
    raw_value: object = capability.get("executionContract")
    if raw_value is None:
        raw_value = capability.get("execution_contract")
    if raw_value is None:
        raw_value = metadata.get("execution_contract")
    raw = json_object(raw_value)

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
        field: [
            str(item).strip()
            for item in raw.get(field, [])
            if str(item).strip()
        ]
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
    if isinstance(raw_value, dict):
        return contract

    capability_type = str(capability.get("type") or "").strip().casefold()
    capability_kind = str(
        capability.get("capabilityKind")
        or capability.get("capability_kind")
        or ""
    ).strip().casefold()
    geometry = str(
        metadata.get("geometry_type") or capability.get("geometry_type") or ""
    ).strip().casefold().replace("_", "-")
    queryable = bool(metadata.get("queryable", False))
    vectorizable = bool(metadata.get("vectorizable", False))
    raster = (
        capability_kind == "raster-overlay"
        or capability_type in {"tile", "wms", "wmts", "raster", "raster-overlay"}
        or geometry in {"raster-grid", "raster", "tile"}
    )
    analysis = capability_kind in {"analysis-tool", "analysis_tool"} or capability_type in {
        "direct-tool",
        "direct_tool",
        "point-insight",
        "time-series-insight",
    }
    vector = (
        capability_kind in {"vector-overlay", "dataset-ingestion", "search-index"}
        or queryable
        or vectorizable
    ) and not analysis
    capability_values: list[str] = []
    for value in (
        capability.get("name"),
        capability.get("description"),
        capability.get("capabilities"),
        metadata.get("keywords"),
        metadata.get("action_tags"),
    ):
        if isinstance(value, list):
            capability_values.extend(
                str(item) for item in cast(list[object], value)
            )
        else:
            capability_values.append(str(value or ""))
    capability_tokens = {
        token.casefold()
        for value in capability_values
        for token in re.findall(r"[a-z0-9]+", value.casefold())
    }

    if raster:
        contract["supported_scope_kinds"] = ["bbox"]
        contract["render_support"] = "raster"
        contract["output_geometry_type"] = "raster-grid"
    elif analysis and geometry in {"point", "not-applicable", "none", ""}:
        contract["supported_scope_kinds"] = ["point", "bbox"]
        contract["render_support"] = "metadata_only"
        contract["output_geometry_type"] = "Point"
    elif vector and geometry in {"point", "line", "linestring", "polygon", "multipolygon"}:
        contract["render_support"] = "vector"
        contract["output_geometry_type"] = (
            "Point" if geometry == "point" else geometry
        )
    elif geometry:
        contract["supported_scope_kinds"] = ["bbox"]
        contract["render_support"] = "vector" if vector else "none"
        contract["output_geometry_type"] = geometry

    operations = ["show"]
    if queryable:
        operations.extend(["search", "filter"])
    if "forecast" in capability_tokens:
        operations.append("forecast")
    contract["supported_operations"] = operations
    if metadata.get("requires_location") is True or geometry not in {"", "global"}:
        contract["required_inputs"] = ["location"]
    if "forecast" in capability_tokens:
        contract["temporal_modes"] = ["current", "forecast"]
    contract["coverage"] = str(
        capability.get("coverage") or ""
    ).strip() or None
    return contract

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
        return normalized_execution_contract(capability)
