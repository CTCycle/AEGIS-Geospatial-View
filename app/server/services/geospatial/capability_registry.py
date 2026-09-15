from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

from server.common.typing import is_json_array, is_json_object, json_object
from server.domain.geospatial.registry import (
    CapabilityRegistrySnapshot,
    GeospatialManifestSnapshot,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.manifest_loader import GeospatialManifestLoader

###############################################################################
class CapabilityArgumentSchemaError(ValueError):
    """Raised when an executable manifest lacks a safe argument schema."""


###############################################################################
class RuntimeEligibility(Protocol):

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool: ...

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool: ...

###############################################################################
def normalized_execution_contract(capability: dict[str, Any]) -> dict[str, Any]:
    """Return the explicit schema-v2 execution semantics for a capability.

    Routing metadata is part of the manifest contract.  The registry must not
    infer executable behavior from capability kind, geometry, or free-text
    descriptions: an incomplete manifest is rejected from the executable
    shortlist instead of silently acquiring a second routing contract.
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
    return contract


###############################################################################
def capability_argument_schema(capability: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical bounded argument schema for one manifest entry."""

    metadata = json_object(capability.get("metadata"))
    schema = metadata.get("parameters_json_schema") or metadata.get(
        "argument_schema"
    )
    if is_json_object(schema):
        return dict(schema)
    if capability.get("source_path") or capability.get("source_filename"):
        string_value = {"type": "string", "minLength": 1}
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                "location": string_value,
                "location_text": string_value,
                "address": string_value,
                "city": string_value,
                "country": string_value,
                "query": string_value,
                "target_id": string_value,
                "location_ref": string_value,
                "location_refs": {
                    "type": "array",
                    "items": string_value,
                    "maxItems": 16,
                },
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "radius_m": {"type": "number", "exclusiveMinimum": 0},
                "radius_km": {"type": "number", "exclusiveMinimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                "requested_attributes": {
                    "type": "array",
                    "items": string_value,
                    "maxItems": 32,
                },
                "poi_categories": {
                    "type": "array",
                    "items": string_value,
                    "maxItems": 64,
                },
                "categories": {
                    "type": "array",
                    "items": string_value,
                    "maxItems": 64,
                },
                "temporal_mode": string_value,
                "time": string_value,
                "reference_time_iso": string_value,
                "start_time_iso": string_value,
                "end_time_iso": string_value,
                "temporal_granularity": string_value,
                "aggregation": string_value,
                "viewport": {"type": "object"},
                "basemap": string_value,
                "scope": string_value,
                "show_marker": {"type": "boolean"},
                "show_label": {"type": "boolean"},
            },
        }
    capability_id = str(capability.get("id") or "unknown")
    raise CapabilityArgumentSchemaError(
        f"Capability '{capability_id}' does not declare an executable argument schema."
    )

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
    def argument_schema(self, capability_id: str) -> dict[str, Any]:
        capability = self.get_capability(capability_id)
        if capability is None:
            raise CapabilityArgumentSchemaError(
                f"Unknown geospatial capability '{capability_id}'."
            )
        return capability_argument_schema(capability)

    # -------------------------------------------------------------------------
    def shortlist(
        self,
        *,
        domains: set[CapabilityDomain],
        queries: list[str],
        explicit_ids: list[str],
        runtime_registry: RuntimeEligibility,
        limit: int = 12,
        operation: str | None = None,
        scope_kind: str | None = None,
        temporal_mode: str | None = None,
        temporal_granularity: str | None = None,
        has_explicit_time_range: bool = False,
        requires_render: bool = False,
        location: ResolvedLocation | None = None,
    ) -> list[dict[str, Any]]:
        """Return eligible routing candidates without selecting final tools.

        ``agenticUse.domains`` is the authoritative routing contract.  The
        shortlist leaves final capability choice and all execution arguments
        to the model/tool boundary.
        """

        bounded_limit = max(1, min(int(limit), 50))
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
            if not _has_explicit_execution_contract(item):
                continue
            declared_domains = _declared_domains(item)
            if requested_domains and CapabilityDomain.MIXED not in requested_domains:
                if not declared_domains.intersection(requested_domains):
                    continue
            contract = normalized_execution_contract(item)
            if not _contract_supports(
                contract,
                operation=operation,
                scope_kind=scope_kind,
                temporal_mode=temporal_mode,
                temporal_granularity=temporal_granularity,
                has_explicit_time_range=has_explicit_time_range,
                requires_render=requires_render
                and _has_explicit_execution_contract(item),
            ):
                continue
            if _avoid_when_conflicts(item, normalized_queries, location):
                continue
            if location is not None and not _coverage_matches(
                str(contract.get("coverage") or item.get("coverage") or ""),
                location,
            ):
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
            candidate["routing_contract"] = contract
            candidate["runtime_eligible"] = True
            candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                -float(item.get("routing_score") or 0.0),
                str(item.get("id") or ""),
            )
        )
        return candidates[:bounded_limit]


def _contract_supports(
    contract: dict[str, Any],
    *,
    operation: str | None,
    scope_kind: str | None,
    temporal_mode: str | None,
    temporal_granularity: str | None,
    has_explicit_time_range: bool,
    requires_render: bool,
) -> bool:
    """Apply deterministic execution compatibility before relevance scoring."""

    normalized_operation = str(operation or "").strip().casefold()
    operations = {
        str(item).strip().casefold()
        for item in contract.get("supported_operations", [])
        if str(item).strip()
    }
    operation_candidates = _operation_candidates(normalized_operation)
    if (
        operation_candidates
        and operations
        and not operation_candidates.intersection(operations)
    ):
        return False

    normalized_scope = str(scope_kind or "").strip().casefold()
    scopes = {
        str(item).strip().casefold()
        for item in contract.get("supported_scope_kinds", [])
        if str(item).strip()
    }
    if normalized_scope and scopes and normalized_scope not in scopes:
        return False

    normalized_temporal = str(temporal_mode or "").strip().casefold()
    normalized_granularity = str(temporal_granularity or "").strip().casefold()
    # Models commonly describe a live/recent observation feed as "historical"
    # because its events happened in the immediate past.  Without an explicit
    # date boundary, recent/latest intent is compatible with a current feed;
    # dated historical requests remain strict.
    if (
        normalized_temporal == "historical"
        and not has_explicit_time_range
        and normalized_granularity
        in {"current", "latest", "live", "near_real_time", "recent"}
    ):
        normalized_temporal = "current"
    temporal_modes = {
        str(item).strip().casefold()
        for item in contract.get("temporal_modes", [])
        if str(item).strip()
    }
    if (
        normalized_temporal
        and temporal_modes
        and normalized_temporal not in temporal_modes
    ):
        return False

    if requires_render and str(contract.get("render_support") or "none") in {
        "none",
        "metadata_only",
    }:
        return False
    return True


def _operation_candidates(operation: str) -> set[str]:
    """Map compound user-semantic operations to manifest primitives."""

    if not operation:
        return set()
    aliases = {
        "display": "show",
        "find": "search",
        "get": "search",
        "locate": "search",
        "map": "show",
        "render": "show",
        "retrieve": "search",
        "visualize": "show",
    }
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", operation)
        if token not in {"and", "data", "then"}
    }
    return {operation, *tokens, *(aliases[token] for token in tokens if token in aliases)}


def _has_explicit_execution_contract(capability: dict[str, Any]) -> bool:
    if is_json_object(capability.get("executionContract")):
        return True
    if is_json_object(capability.get("execution_contract")):
        return True
    metadata = json_object(capability.get("metadata"))
    return is_json_object(metadata.get("execution_contract"))


def _coverage_matches(coverage: str, location: ResolvedLocation) -> bool:
    """Reject a known incompatible jurisdiction, but preserve unknown coverage."""

    normalized = re.sub(r"[^a-z0-9]+", " ", coverage.casefold()).strip()
    if not normalized or any(
        marker in normalized
        for marker in (
            "global",
            "world",
            "source defined",
            "jurisdiction defined",
            "facility defined",
            "regional",
            "local jurisdiction",
        )
    ):
        return True
    country = re.sub(
        r"[^a-z0-9]+", " ",
        " ".join(
            value
            for value in (location.country, location.location_class)
            if value
        ).casefold(),
    ).strip()
    if not country:
        return True
    coverage_tokens = set(normalized.split())
    country_tokens = set(country.split())
    if (
        "united" in coverage_tokens and "states" in coverage_tokens
    ) or "usa" in coverage_tokens or "us" in coverage_tokens:
        return (
            {"united", "states"}.issubset(country_tokens)
            or "usa" in country_tokens
            or "us" in country_tokens
        )
    if "europe" in coverage_tokens or "eu" in coverage_tokens or "eea" in coverage_tokens:
        return any(
            token in country
            for token in (
                "austria",
                "belgium",
                "croatia",
                "denmark",
                "finland",
                "france",
                "germany",
                "greece",
                "ireland",
                "italy",
                "netherlands",
                "norway",
                "poland",
                "portugal",
                "spain",
                "sweden",
                "switzerland",
                "united kingdom",
            )
        )
    return True


def _avoid_when_conflicts(
    capability: dict[str, Any],
    query_tokens: set[str],
    location: ResolvedLocation | None,
) -> bool:
    """Reject explicit manifest avoid-conditions before relevance ranking."""

    agentic_use = json_object(capability.get("agenticUse"))
    if not agentic_use:
        agentic_use = json_object(capability.get("agentic_use"))
    raw_avoid = agentic_use.get("avoidWhen")
    if not is_json_array(raw_avoid):
        return False

    ignored = {
        "a",
        "an",
        "and",
        "analysis",
        "chat",
        "context",
        "for",
        "general",
        "in",
        "not",
        "of",
        "or",
        "request",
        "requests",
        "source",
        "the",
        "use",
        "with",
    }
    for raw_phrase in raw_avoid:
        phrase = str(raw_phrase or "").casefold()
        phrase_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", phrase)
            if token not in ignored
        }
        if not phrase_tokens:
            continue
        if "no geographic context" in phrase and location is None:
            return True
        if phrase_tokens.intersection(query_tokens):
            return True
    return False

###############################################################################
def _declared_domains(capability: dict[str, Any]) -> set[CapabilityDomain]:
    agentic_use = json_object(capability.get("agenticUse"))
    if not agentic_use:
        agentic_use = json_object(capability.get("agentic_use"))
    raw_domains = agentic_use.get("domains")
    declared: set[CapabilityDomain] = set()
    if is_json_array(raw_domains):
        for value in raw_domains:
            try:
                declared.add(CapabilityDomain(str(value)))
            except ValueError:
                continue
    return declared

###############################################################################
def _searchable_text(capability: dict[str, Any]) -> set[str]:
    agentic_use = json_object(capability.get("agenticUse"))
    if not agentic_use:
        agentic_use = json_object(capability.get("agentic_use"))
    metadata = json_object(capability.get("metadata"))
    values: list[object] = [
        capability.get("id"),
        capability.get("name"),
        capability.get("description"),
        capability.get("capabilities"),
        agentic_use.get("plannerHints"),
        agentic_use.get("intentTags"),
        metadata.get("keywords"),
        metadata.get("action_tags"),
        metadata.get("supported_categories"),
        metadata.get("task_tags"),
        metadata.get("primary_use_cases"),
        metadata.get("search_examples"),
        metadata.get("human_summary"),
    ]
    return {
        token
        for value in values
        for token in _query_tokens(value if is_json_array(value) else [value])
    }

###############################################################################
def _query_tokens(values: Sequence[object]) -> set[str]:
    return {
        token
        for value in values
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) > 1
    }
