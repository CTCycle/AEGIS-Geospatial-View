"""Native capability discovery handler."""

from __future__ import annotations

import re
import time
from typing import Any, cast

from server.domain.agent.capability_domains import CapabilityDomain
from server.common.identifiers import location_ref_matches
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.services.agent.tool_registry import follow_up_investigation_open
from server.services.agent.completion import follow_up_location_keys
from server.services.agent.tool_definitions import (
    CapabilityDiscoveryInput,
    DescribeCapabilityInput,
)
from server.services.geospatial.capability_registry import (
    CapabilityArgumentSchemaError,
    CapabilityRegistry,
)
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class CatalogToolHandler:

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
    async def discover(
        self,
        request: CapabilityDiscoveryInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        diagnostics: dict[str, Any] | None = None
        route_domains = {CapabilityDomain.MIXED}
        route = state.route
        catalog_discovery = (
            route is not None
            and route.operation == "discover_available_map_data"
        )
        if route is not None and not catalog_discovery:
            route_domains = {route.primary_domain, *route.secondary_domains}
        location = (
            next(iter(state.location_refs.values()))
            if len(state.location_refs) == 1
            else state.active_map_session.resolved_location
            if state.active_map_session is not None
            else None
        )
        if route is not None and route.location_mode == "search_area":
            location = next((item for key, item in state.location_refs.items()
                             if any(location_ref_matches(ref, key, item.label) for ref in route.target_refs)), None)
        query_values = (
            list(route.capability_queries)
            if catalog_discovery and route is not None
            else [request.query]
            if request.query
            else (
            list(route.capability_queries)
            if route is not None
            else []
            )
        )
        # A follow-up query (the weather at a derived epicentre) is a new
        # source for a new point: the route's operation and time window
        # describe the first source and must not filter it out.
        follow_up = request.query is not None and follow_up_investigation_open(state)
        if follow_up:
            follow_up_keys = follow_up_location_keys(state)
            location = next(
                (item for key, item in reversed(list(state.location_refs.items()))
                 if key in follow_up_keys),
                location,
            )
        route_filters = route if route is not None and not follow_up else None
        if catalog_discovery and any("basemap" in query.casefold() for query in query_values):
            # A basemap inventory is the catalog's basemap list, not a ranked
            # search that pages through every overlay and provider.
            candidates = [
                item
                for item in self.capability_registry.list_basemaps()
                if self.runtime_registry.is_enabled(str(item.get("id") or ""))
            ]
        else:
            constraints: dict[str, Any] = {
                "domains": route_domains,
                "queries": query_values,
                "explicit_ids": request.capability_ids,
                "runtime_registry": self.runtime_registry,
                # Pagination is applied after deterministic ranking so a cursor
                # always addresses the same catalog snapshot.
                "limit": None if catalog_discovery else 50,
                "operation": (
                    None
                    if catalog_discovery or route_filters is None
                    else route_filters.operation
                ),
                "scope_kind": (
                    None
                    if catalog_discovery or follow_up
                    else _resolved_scope_kind(route, location)
                ),
                "temporal_mode": (
                    route_filters.temporal_scope.mode
                    if route_filters is not None and route_filters.temporal_scope.mode != "none"
                    else None
                ),
                "temporal_granularity": (
                    route_filters.temporal_scope.granularity if route_filters is not None else None
                ),
                "has_explicit_time_range": (
                    route_filters is not None
                    and any(
                        value is not None
                        for value in (
                            route_filters.temporal_scope.reference_time_iso,
                            route_filters.temporal_scope.start_time_iso,
                            route_filters.temporal_scope.end_time_iso,
                        )
                    )
                ),
                "requires_render": (
                    route_filters is not None and route_filters.presentation in {"map", "both"}
                ),
                "location": location,
            }
            candidates = self.capability_registry.shortlist(**constraints)
            if not candidates and not catalog_discovery:
                diagnostics = self._empty_diagnostics(constraints, state)
        if state.excluded_capability_ids:
            excluded = set(state.excluded_capability_ids)
            candidates = [
                item
                for item in candidates
                if str(item.get("id") or "").strip() not in excluded
            ]
        if request.provider_id:
            provider_id = request.provider_id.casefold()
            candidates = [
                item
                for item in candidates
                if str(item.get("provider") or "").casefold() == provider_id
            ]
        offset = _cursor_offset(request.cursor)
        if offset is None:
            return _failure(
                tool_name="discover_geospatial_capabilities",
                code="invalid_cursor",
                message="The discovery cursor must be a non-negative integer.",
                recovery="correct_arguments",
                started=started,
            )
        # Keep catalog pages within the model observation projection, which
        # retains at most twelve capability records and their continuation
        # cursor. Returning a larger page here would hide the remaining items
        # while reporting that pagination had finished.
        page_limit = min(request.limit, 12) if catalog_discovery else request.limit
        page = candidates[offset : offset + page_limit]
        descriptors = [
            _descriptor(self.capability_registry, self.runtime_registry, item, query_values)
            for item in page
        ]
        discovered_ids = [str(item["id"]) for item in descriptors if item.get("id")]
        state.capability_ids = list(
            dict.fromkeys([*state.capability_ids, *discovered_ids])
        )[:12]
        status = "success" if descriptors else "valid_empty"
        return ToolResult(
            call_id="handler-call",
            tool_name="discover_geospatial_capabilities",
            status=status,
            summary=(
                f"Found {len(descriptors)} eligible capabilities."
                if descriptors
                else str((diagnostics or {}).get("summary") or "No eligible capabilities matched the request.")
            ),
            data={
                "capabilities": descriptors,
                **({"diagnostics": diagnostics} if diagnostics and not descriptors else {}),
                "provider_id": request.provider_id,
                "next_cursor": (
                    str(offset + len(descriptors))
                    if offset + len(descriptors) < len(candidates)
                    else None
                ),
                "total": len(candidates),
            },
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000))
            ),
        )

    # -------------------------------------------------------------------------
    def _empty_diagnostics(
        self,
        constraints: dict[str, Any],
        state: AgentRunState,
    ) -> dict[str, Any]:
        """Explain an empty shortlist by relaxing one canonical constraint.

        The same registry policy is re-run with a single filter removed, so
        the explanation can never disagree with eligibility itself.
        """

        relaxations: list[tuple[str, str, dict[str, Any]]] = []
        if constraints["operation"]:
            relaxations.append(("operation", f"operation '{constraints['operation']}'", {"operation": None}))
        if constraints["scope_kind"]:
            relaxations.append(("spatial_scope", f"{constraints['scope_kind']} scope", {"scope_kind": None}))
        if constraints["temporal_mode"] or constraints["has_explicit_time_range"]:
            relaxations.append(("time", "requested time window", {
                "temporal_mode": None, "temporal_granularity": None, "has_explicit_time_range": False,
            }))
        if constraints["requires_render"]:
            relaxations.append(("map_rendering", "map rendering", {"requires_render": False}))
        if constraints["location"] is not None:
            relaxations.append(("coverage", "geographic coverage of the place", {"location": None}))
        unmet: list[dict[str, Any]] = []
        for kind, label, override in relaxations:
            relaxed: dict[str, Any] = {**constraints, **override, "limit": 3}
            alternatives = self.capability_registry.shortlist(**relaxed)
            excluded = set(state.excluded_capability_ids)
            alternatives = [item for item in alternatives if str(item.get("id") or "") not in excluded]
            if alternatives:
                unmet.append({
                    "constraint": kind,
                    "description": label,
                    "alternatives": [
                        _descriptor(self.capability_registry, self.runtime_registry, item)
                        for item in alternatives
                    ],
                })
        # The subject itself is never relaxed: a source for another subject is
        # not an alternative, and offering one invites irrelevant evidence.
        unavailable = self.capability_registry.unavailable_matches(
            constraints, self.runtime_registry
        )
        parts: list[str] = []
        if unmet:
            first = unmet[0]
            names = ", ".join(str(item["id"]) for item in first["alternatives"])
            parts.append(
                f"No enabled capability satisfies the {first['description']}; "
                f"without it these match: {names}."
            )
        if unavailable:
            parts.append("Matching but unavailable: " + ", ".join(
                f"{item['capability_id']} ({item['reason']})" for item in unavailable
            ) + ".")
        if state.excluded_capability_ids:
            parts.append(
                "Excluded after failing in this run: "
                + ", ".join(state.excluded_capability_ids[:4]) + "."
            )
        if not parts:
            parts.append("No enabled catalog capability covers this subject.")
        return {
            "summary": " ".join(parts),
            "unmet_constraints": unmet[:3],
            "unavailable": unavailable,
            "hint": (
                "Repeating the same discovery will return the same result. Use a listed "
                "alternative with arguments it supports, or answer with what is known "
                "and state what no available source provides."
            ),
        }

    # -------------------------------------------------------------------------
    async def describe(
        self,
        request: DescribeCapabilityInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        capability_id = request.capability_id
        if state.capability_ids and capability_id not in state.capability_ids:
            return _failure(
                code="capability_not_shortlisted",
                message="The capability was not returned by the validated route.",
                recovery="choose_alternate_tool",
                started=started,
            )
        capability = self.capability_registry.get_capability(capability_id)
        if capability is None:
            return _failure(
                code="unknown_capability",
                message=f"Unknown geospatial capability '{capability_id}'.",
                recovery="choose_alternate_tool",
                started=started,
            )
        try:
            argument_schema = self.capability_registry.argument_schema(capability_id)
        except CapabilityArgumentSchemaError as exc:
            return _failure(
                code="missing_argument_schema",
                message=str(exc),
                recovery="terminal",
                started=started,
            )
        provider_id = str(capability.get("provider") or "") or None
        return ToolResult(
            call_id="handler-call",
            tool_name="describe_geospatial_capability",
            status="success",
            summary=f"Described geospatial capability {capability_id}.",
            data={
                "capability_id": capability_id,
                # Selection and audit metadata is spent by the time a capability
                # is described, and this result stays in every later model call.
                "manifest": {
                    key: value
                    for key, value in capability.items()
                    if key not in {"agenticUse", "reliability"}
                },
                "argument_schema": argument_schema,
                "execution_contract": self.capability_registry.execution_contract(
                    capability_id
                ),
            },
            metadata=ToolExecutionMetadata(
                capability_id=capability_id,
                provider_id=provider_id,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            ),
        )

###############################################################################
def _resolved_scope_kind(route: Any, location: Any) -> str | None:
    """Lower semantic route scope to the concrete catalog scope."""

    if route is None or route.spatial_scope is None:
        return None
    kind = str(route.spatial_scope.kind)
    # The visible map area executes as its bounding box; every catalog entry
    # that accepts a viewport also accepts a bbox.
    if kind in {"administrative_geometry", "feature_geometry", "point", "viewport"}:
        return "bbox" if location is not None and location.bbox else None
    return kind

###############################################################################
def _cursor_offset(cursor: str | None) -> int | None:
    if cursor is None or not cursor.strip():
        return 0
    try:
        offset = int(cursor)
        return offset if offset >= 0 else None
    except ValueError:
        return None

###############################################################################
def _descriptor(
    registry: CapabilityRegistry,
    runtime_registry: RuntimeRegistry,
    capability: dict[str, Any],
    queries: list[str] | None = None,
) -> dict[str, Any]:
    capability_id = str(capability.get("id") or "").strip()
    execution_contract = registry.execution_contract(capability_id)
    render_support = str(
        execution_contract.get("render_support") or "none"
    ).casefold()
    return {
        "id": capability_id,
        "name": str(capability.get("name") or capability_id),
        "summary": str(
            capability.get("summary") or capability.get("description") or ""
        )[:240],
        "provider": str(capability.get("provider") or ""),
        "operations": [
            str(operation)
            for operation in execution_contract.get("supported_operations", [])
            if str(operation).strip()
        ],
        "render_support": render_support,
        "reason": _match_reason(capability, execution_contract, queries or []),
    }

###############################################################################
def _match_reason(
    capability: dict[str, Any],
    execution_contract: dict[str, Any],
    queries: list[str],
) -> str:
    """Say why a candidate was shortlisted, from catalog fields only."""

    metadata = capability.get("metadata")
    agentic = capability.get("agenticUse")
    vocabulary: list[str] = [str(capability.get("name") or "")]
    for source, keys in ((metadata, ("keywords", "action_tags")), (agentic, ("plannerHints",))):
        if isinstance(source, dict):
            for key in keys:
                values = cast(dict[str, Any], source).get(key)
                if isinstance(values, list):
                    vocabulary.extend(str(item) for item in cast(list[Any], values))
    query_terms = {term for query in queries for term in re.findall(r"[a-z0-9]+", query.casefold()) if len(term) > 2}
    matched = sorted(
        {
            term
            for entry in vocabulary
            for term in re.findall(r"[a-z0-9]+", entry.casefold())
            if term in query_terms
        }
    )
    domains = cast(dict[str, Any], agentic).get("domains") if isinstance(agentic, dict) else None
    parts: list[str] = []
    if matched:
        parts.append("matches " + ", ".join(matched[:4]))
    elif isinstance(domains, list) and domains:
        parts.append("domain " + ", ".join(str(item) for item in cast(list[Any], domains)[:2]))
    coverage = execution_contract.get("coverage")
    if coverage:
        parts.append(f"coverage {coverage}")
    return "; ".join(parts)[:120]

###############################################################################
def _failure(
    *,
    tool_name: str = "describe_geospatial_capability",
    code: str,
    message: str,
    recovery: str,
    started: float,
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name=tool_name,
        status="failed",
        summary=message,
        error=ToolExecutionError(
            error_type=(
                "state_conflict"
                if code in {"unknown_capability", "capability_not_shortlisted"}
                else "semantic_validation"
            ),
            code=code,
            message=message,
            retryable=False,
            recovery=recovery,  # type: ignore[arg-type]
        ),
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )


__all__ = ["CatalogToolHandler"]
