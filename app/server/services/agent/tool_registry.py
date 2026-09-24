"""Single source of truth for tools exposed by the native agent harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.tools import RegisteredTool
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition

if TYPE_CHECKING:
    from server.domain.agent.capability_route import AgentRunState

###############################################################################
class ToolRegistry:
    """Register, expose, and retrieve the typed native tool catalogue.

    Capability manifests are data, while this registry contains only the small
    permanent meta-tool surface. Capability-specific eligibility is applied by
    the route compiler and the registered semantic validators at execution
    time; there is no second registry.
    """

    # -------------------------------------------------------------------------
    def __init__(self, *, runtime_registry: RuntimeRegistry | None = None) -> None:
        # Retain the shared runtime reference for diagnostics and composition
        # checks. Tool eligibility is intentionally not inferred from it here.
        self.runtime_registry = runtime_registry
        self._registered_tools: dict[str, RegisteredTool] = {}

    # -------------------------------------------------------------------------
    def register(self, tool: RegisteredTool) -> None:
        """Register one typed tool and reject duplicate definitions."""

        name = tool.definition.name.strip()
        if not name:
            raise ValueError("Registered tools must have a non-empty name.")
        if name != tool.definition.name:
            raise ValueError(
                "Registered tool names must not contain surrounding whitespace."
            )
        if name in self._registered_tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._registered_tools[name] = tool

    # -------------------------------------------------------------------------
    def get(self, name: str) -> RegisteredTool | None:
        """Return one registered tool by its exact public name."""

        return self._registered_tools.get(str(name).strip())

    # -------------------------------------------------------------------------
    def expose(self, state: "AgentRunState") -> list[LLMToolDefinition]:
        """Return only tools valid for the current native run state."""

        exposed: list[LLMToolDefinition] = []
        active_map_update = _is_active_map_update(state)
        for registered in self._registered_tools.values():
            if (
                registered.visibility == "internal"
                and state.phase.value != "route_request"
            ):
                continue
            if state.phase not in registered.phases:
                continue
            if not _task_mode_allows_tool(registered, state):
                continue
            if not _domain_allows_tool(registered, state):
                continue
            if active_map_update and registered.definition.name in {
                "discover_geospatial_capabilities",
                "discover_geospatial_provider_layers",
                "describe_geospatial_capability",
                "inspect_evidence",
                "transform_evidence",
            }:
                continue
            if not self._prerequisites_satisfied(registered.prerequisites, state):
                continue
            definition = registered.definition
            if definition.name == "execute_geospatial_capability" and state.capability_ids:
                schema = dict(definition.parameters_json_schema)
                properties = dict(schema.get("properties") or {})
                capability_schema = dict(properties.get("capability_id") or {})
                capability_schema["enum"] = list(state.capability_ids)
                properties["capability_id"] = capability_schema
                if len(state.capability_ids) == 1 and registered.argument_schema_provider:
                    try:
                        request = registered.input_model.model_validate(
                            {"capability_id": state.capability_ids[0]}
                        )
                        argument_schema = registered.argument_schema_provider(
                            request, state
                        )
                    except Exception:
                        argument_schema = None
                    if isinstance(argument_schema, dict):
                        properties["arguments"] = dict(argument_schema)
                schema["properties"] = properties
                definition = LLMToolDefinition(
                    name=definition.name,
                    description=definition.description,
                    parameters_json_schema=schema,
                )
            exposed.append(definition)
            if len(state.exposure_trace) < 64:
                state.exposure_trace.append(
                    {
                        "phase": state.phase.value,
                        "tool": definition.name,
                        "reason": "task_mode_domain_phase_and_prerequisites_satisfied",
                    }
                )
        return exposed

    # -------------------------------------------------------------------------
    @staticmethod
    def _prerequisites_satisfied(
        prerequisites: frozenset[str], state: "AgentRunState"
    ) -> bool:
        has_location = _route_target_location_available(state)
        for prerequisite in prerequisites:
            if prerequisite == "route" and state.route is None:
                return False
            if prerequisite == "capability_shortlist" and not state.capability_ids:
                return False
            if (
                prerequisite == "capability_shortlist_missing"
                and state.capability_ids
                and not _catalog_discovery_can_continue(state)
            ):
                return False
            if prerequisite == "location" and not has_location:
                return False
            if prerequisite == "location_required" and (
                state.route is None or not state.route.requires_location
            ):
                return False
            if prerequisite == "location_missing" and has_location:
                return False
            if prerequisite == "location_if_required" and (
                state.route is not None
                and state.route.requires_location
                and not has_location
            ):
                return False
            if prerequisite == "evidence" and not _evidence_available_for_route(state):
                return False
            if prerequisite == "evidence_analysis_required" and not _evidence_analysis_required(state):
                return False
            if prerequisite == "history_recall_required" and not _history_recall_required(state):
                return False
            if prerequisite == "data_obligation_unmet" and not _data_obligation_unmet(state):
                return False
            if prerequisite == "active_map" and state.active_map_session is None:
                return False
            if prerequisite == "provider_discovery_route":
                if state.route is None:
                    return False
                route_domains = {
                    state.route.primary_domain,
                    *state.route.secondary_domains,
                }
                if CapabilityDomain.PROVIDER_DISCOVERY not in route_domains:
                    return False
            if prerequisite == "data_route":
                if state.route is None:
                    return False
                if state.route.operation == "discover_available_map_data":
                    return False
                route_domains = {
                    state.route.primary_domain,
                    *state.route.secondary_domains,
                }
                if state.route.primary_domain is CapabilityDomain.MAP_STATE or (
                    state.route.primary_domain is CapabilityDomain.MAP_RENDERING
                    and CapabilityDomain.DATA_RETRIEVAL not in route_domains
                ):
                    return False
            if prerequisite == "map_presentation":
                if state.route is None or state.route.presentation not in {"map", "both"}:
                    return False
        return True


###############################################################################
def _catalog_discovery_can_continue(state: "AgentRunState") -> bool:
    """Expose discovery again only while a catalog page remains or a retry is needed."""

    route = state.route
    if route is None or route.operation != "discover_available_map_data":
        return False
    discovery_results = [
        result
        for result in state.tool_results
        if result.tool_name == "discover_geospatial_capabilities"
    ]
    if not discovery_results:
        return True
    latest = discovery_results[-1]
    if latest.status not in {"success", "valid_empty"}:
        return True
    return bool(
        isinstance(latest.data, dict)
        and latest.data.get("next_cursor") not in {None, ""}
    )

_ACTIVE_MAP_UPDATE_OPERATIONS = frozenset(
    {
        "remove_layer",
        "set_layer_visibility",
        "set_layer_opacity",
        "set_basemap",
        "keep_only_layers",
        "fit_layer",
        "reset_view",
    }
)


###############################################################################
def _route_target_location_available(state: "AgentRunState") -> bool:
    """Check the validated route targets, not merely any prior map state."""

    route = state.route
    if _is_active_map_update(state):
        return state.active_map_session is not None
    target_refs = (
        list(route.spatial_scope.target_refs)
        if route is not None
        and route.spatial_scope is not None
        and route.spatial_scope.target_refs
        else list(route.target_refs) if route is not None else []
    )
    if not target_refs:
        return bool(state.location_refs) or state.active_map_session is not None
    resolved_keys = {" ".join(str(key).casefold().split()) for key in state.location_refs}
    return all(
        " ".join(str(target).casefold().split()) in resolved_keys
        for target in target_refs
    )


###############################################################################
def _is_active_map_update(state: "AgentRunState") -> bool:
    route = state.route
    return bool(
        route is not None
        and route.task_mode == "execute"
        and route.primary_domain is CapabilityDomain.MAP_STATE
        and state.active_map_session is not None
        and str(route.operation or "").strip().casefold()
        in _ACTIVE_MAP_UPDATE_OPERATIONS
        and route.spatial_scope is None
    )


###############################################################################
def _evidence_available_for_route(state: "AgentRunState") -> bool:
    """Do not expose stale evidence tools before a new map-data retrieval."""

    route = state.route
    route_domains: set[CapabilityDomain] = (
        {
            route.primary_domain,
            *route.secondary_domains,
        }
        if route is not None
        else set()
    )
    if (
        route is not None
        and CapabilityDomain.DATA_RETRIEVAL in route_domains
        and route.presentation in {"map", "both"}
        and str(route.operation or "").strip().casefold()
        in {"", "retrieve", "search", "query", "add_layer"}
    ):
        return any(
            result.status in {"success", "valid_empty", "partial"}
            and bool(result.evidence_refs)
            for result in state.tool_results
        )
    return bool(state.evidence_refs)


###############################################################################
def _task_mode_allows_tool(
    registered: RegisteredTool, state: "AgentRunState"
) -> bool:
    """Keep execution tools out of answer/clarify model turns."""

    if registered.visibility == "internal":
        return True
    if state.route is None and state.phase.value == "route_request":
        return True
    return state.route is not None and state.route.task_mode == "execute"


###############################################################################
def _route_domains(state: "AgentRunState") -> set[CapabilityDomain]:
    route = state.route
    if route is None:
        return set()
    return {route.primary_domain, *route.secondary_domains}


###############################################################################
def _domain_allows_tool(registered: RegisteredTool, state: "AgentRunState") -> bool:
    """Expose only tools that can satisfy the validated route's domains."""

    if registered.visibility == "internal" or state.route is None:
        return True
    route = state.route
    route_domains = _route_domains(state)
    if registered.definition.name == "resolve_geospatial_location":
        return route.requires_location and not _route_target_location_available(state)
    if registered.definition.name == "apply_map_plan":
        return route.presentation in {"map", "both"}
    if route.primary_domain is CapabilityDomain.MAP_STATE:
        return registered.definition.name == "apply_map_plan"
    if (
        route.primary_domain is CapabilityDomain.MAP_RENDERING
        and route.presentation in {"map", "both"}
        and not (
            CapabilityDomain.DATA_RETRIEVAL in route_domains
            or CapabilityDomain.SPATIAL_ANALYSIS in route_domains
        )
    ):
        return registered.definition.name == "apply_map_plan"
    if not registered.domains:
        return True
    if CapabilityDomain.MIXED in registered.domains:
        return True
    if CapabilityDomain.MIXED in route_domains:
        return True
    return bool(registered.domains.intersection(route_domains))


###############################################################################
def _evidence_analysis_required(state: "AgentRunState") -> bool:
    route = state.route
    if route is None:
        return False
    domains = _route_domains(state)
    if CapabilityDomain.SPATIAL_ANALYSIS in domains:
        return True
    terms = " ".join(
        [str(route.operation or ""), *[str(value) for value in route.capability_queries]]
    ).casefold()
    return any(
        marker in terms
        for marker in ("analy", "aggregate", "statistic", "transform", "inspect")
    )


###############################################################################
def _history_recall_required(state: "AgentRunState") -> bool:
    route = state.route
    if route is None:
        return False
    terms = " ".join(
        [str(route.operation or ""), *[str(value) for value in route.capability_queries]]
    ).casefold()
    return CapabilityDomain.CONVERSATION in _route_domains(state) and any(
        marker in terms
        for marker in ("history", "conversation", "earlier", "previous", "remember")
    )


###############################################################################
def _data_obligation_unmet(state: "AgentRunState") -> bool:
    contract = state.completion_contract
    if contract is not None and contract.data_requirement != "provider_data":
        return True
    successful_data_tools = {
        "execute_geospatial_capability",
        "inspect_evidence",
        "transform_evidence",
    }
    return not any(
        (
            result.status in {"success", "partial"}
            or (
                result.status == "valid_empty"
                and result.semantic_outcome != "not_found"
            )
        )
        and result.tool_name in successful_data_tools
        for result in state.tool_results
    )


__all__ = ["ToolRegistry"]
