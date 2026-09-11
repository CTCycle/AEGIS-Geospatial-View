from __future__ import annotations

import re
from typing import Any, Protocol, cast

from server.common.typing import json_object
from server.domain.geospatial.registry import (
    CapabilityRegistrySnapshot,
    GeospatialManifestSnapshot,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.services.geospatial.manifest_loader import GeospatialManifestLoader

###############################################################################
class RuntimeEligibility(Protocol):

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool: ...

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool: ...

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

    # -------------------------------------------------------------------------
    def shortlist(
        self,
        *,
        domains: set[CapabilityDomain],
        queries: list[str],
        explicit_ids: list[str],
        runtime_registry: RuntimeEligibility,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Return eligible routing candidates without selecting final tools.

        The current catalog is being migrated to explicit ``agenticUse``
        domains.  Until that migration is complete, the fallback domain map is
        derived only from the manifest's typed capability kind.  It keeps the
        new shortlist useful while leaving final capability choice and all
        execution arguments to the model/tool boundary.
        """

        bounded_limit = max(1, min(int(limit), 12))
        normalized_queries = _query_tokens(queries)
        normalized_explicit = [
            str(value).strip() for value in explicit_ids if str(value).strip()
        ]
        requested_domains = set(domains)
        candidates: list[dict[str, Any]] = []
        snapshot = self._ensure_snapshot()
        for item in (
            *snapshot.basemaps,
            *snapshot.overlays,
            *snapshot.cameras,
            *snapshot.transit,
            *snapshot.tools,
        ):
            capability_id = str(item.get("id") or "").strip()
            if not capability_id:
                continue
            if not runtime_registry.is_enabled(capability_id):
                continue
            if not runtime_registry.access_available(capability_id):
                continue
            declared_domains = _declared_domains(item)
            if requested_domains and CapabilityDomain.MIXED not in requested_domains:
                if not declared_domains.intersection(requested_domains):
                    continue
            searchable = _searchable_text(item)
            query_score = sum(1 for token in normalized_queries if token in searchable)
            explicit_index = (
                normalized_explicit.index(capability_id)
                if capability_id in normalized_explicit
                else None
            )
            if normalized_explicit and explicit_index is None and not normalized_queries:
                continue
            score = (
                1000.0 - float(explicit_index)
                if explicit_index is not None
                else 0.0
            )
            score += float(len(declared_domains.intersection(requested_domains))) * 100.0
            score += float(query_score * 10)
            if capability_id.casefold() in {item.casefold() for item in normalized_queries}:
                score += 50.0
            candidate = dict(item)
            candidate["routing_score"] = score
            candidate["routing_domains"] = sorted(domain.value for domain in declared_domains)
            candidate["runtime_eligible"] = True
            candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                -float(item.get("routing_score") or 0.0),
                str(item.get("id") or ""),
            )
        )
        return candidates[:bounded_limit]

###############################################################################
def _declared_domains(capability: dict[str, Any]) -> set[CapabilityDomain]:
    agentic_use = capability.get("agenticUse")
    if not isinstance(agentic_use, dict):
        agentic_use = capability.get("agentic_use")
    raw_domains = agentic_use.get("domains") if isinstance(agentic_use, dict) else None
    declared: set[CapabilityDomain] = set()
    if isinstance(raw_domains, list):
        for value in raw_domains:
            try:
                declared.add(CapabilityDomain(str(value)))
            except ValueError:
                continue
    if declared:
        return declared
    return _legacy_domains(capability)

###############################################################################
def _legacy_domains(capability: dict[str, Any]) -> set[CapabilityDomain]:
    kind = str(
        capability.get("capabilityKind")
        or capability.get("capability_kind")
        or ""
    ).strip().casefold()
    if kind == "basemap":
        return {CapabilityDomain.MAP_RENDERING}
    if kind in {"search-index", "camera-network"}:
        return {CapabilityDomain.PLACE_SEARCH, CapabilityDomain.DATA_RETRIEVAL}
    if kind in {"analysis-tool"}:
        # Direct point insights (weather, air quality, elevation, etc.) are
        # executable data retrieval even when their legacy kind predates the
        # explicit agenticUse domain declaration.
        return {CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.SPATIAL_ANALYSIS}
    if kind in {"vector-overlay", "raster-overlay", "dataset-ingestion"}:
        return {CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING}
    if kind == "metadata-only":
        return {CapabilityDomain.PROVIDER_DISCOVERY}
    return {CapabilityDomain.DATA_RETRIEVAL}

###############################################################################
def _searchable_text(capability: dict[str, Any]) -> set[str]:
    agentic_use = capability.get("agenticUse")
    if not isinstance(agentic_use, dict):
        agentic_use = capability.get("agentic_use")
    metadata = capability.get("metadata")
    values: list[object] = [
        capability.get("id"),
        capability.get("name"),
        capability.get("description"),
        capability.get("capabilities"),
        agentic_use.get("plannerHints") if isinstance(agentic_use, dict) else None,
        agentic_use.get("intentTags") if isinstance(agentic_use, dict) else None,
        metadata.get("keywords") if isinstance(metadata, dict) else None,
        metadata.get("action_tags") if isinstance(metadata, dict) else None,
        metadata.get("supported_categories") if isinstance(metadata, dict) else None,
        metadata.get("task_tags") if isinstance(metadata, dict) else None,
        metadata.get("primary_use_cases") if isinstance(metadata, dict) else None,
        metadata.get("search_examples") if isinstance(metadata, dict) else None,
        metadata.get("human_summary") if isinstance(metadata, dict) else None,
    ]
    return {
        token
        for value in values
        for token in _query_tokens(value if isinstance(value, list) else [value])
    }

###############################################################################
def _query_tokens(values: list[object]) -> set[str]:
    return {
        token
        for value in values
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) > 1
    }
