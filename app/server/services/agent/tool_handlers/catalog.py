"""Native capability discovery handler."""

from __future__ import annotations

import time
from typing import Any

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
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
        candidates = self.capability_registry.shortlist(
            domains=route_domains,
            queries=query_values,
            explicit_ids=request.capability_ids,
            runtime_registry=self.runtime_registry,
            # Pagination is applied after deterministic ranking so a cursor
            # always addresses the same catalog snapshot.
            limit=50,
            operation=(
                None
                if catalog_discovery
                else route.operation if route is not None else None
            ),
            scope_kind=(
                None
                if catalog_discovery
                else _resolved_scope_kind(route, location)
            ),
            temporal_mode=(
                route.temporal_scope.mode
                if route is not None and route.temporal_scope.mode != "none"
                else None
            ),
            temporal_granularity=(
                route.temporal_scope.granularity if route is not None else None
            ),
            has_explicit_time_range=(
                route is not None
                and any(
                    value is not None
                    for value in (
                        route.temporal_scope.reference_time_iso,
                        route.temporal_scope.start_time_iso,
                        route.temporal_scope.end_time_iso,
                    )
                )
            ),
            requires_render=(
                route is not None and route.presentation in {"map", "both"}
            ),
            location=location,
        )
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
            _descriptor(self.capability_registry, self.runtime_registry, item)
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
                else "No eligible capabilities matched the request."
            ),
            data={
                "capabilities": descriptors,
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
                "manifest": capability,
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
    if kind in {"administrative_geometry", "feature_geometry"}:
        return "bbox" if location is not None and location.bbox else None
    return kind


###############################################################################
def _cursor_offset(cursor: str | None) -> int | None:
    if cursor is None or not cursor.strip():
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return None

###############################################################################
def _descriptor(
    registry: CapabilityRegistry,
    runtime_registry: RuntimeRegistry,
    capability: dict[str, Any],
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
    }

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
