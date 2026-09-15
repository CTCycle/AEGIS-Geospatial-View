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
        for registered in self._registered_tools.values():
            if (
                registered.visibility == "internal"
                and state.phase.value != "route_request"
            ):
                continue
            if state.phase not in registered.phases:
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
                        "reason": "phase_and_prerequisites_satisfied",
                    }
                )
        return exposed

    # -------------------------------------------------------------------------
    @staticmethod
    def _prerequisites_satisfied(
        prerequisites: frozenset[str], state: "AgentRunState"
    ) -> bool:
        has_location = ToolRegistry._route_target_location_available(state)
        for prerequisite in prerequisites:
            if prerequisite == "route" and state.route is None:
                return False
            if prerequisite == "capability_shortlist" and not state.capability_ids:
                return False
            if prerequisite == "capability_shortlist_missing" and state.capability_ids:
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
            if prerequisite == "evidence" and not state.evidence_refs:
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
                if state.route is None or state.route.primary_domain in {
                    CapabilityDomain.MAP_RENDERING,
                    CapabilityDomain.MAP_STATE,
                }:
                    return False
            if prerequisite == "map_presentation":
                if state.route is None or state.route.presentation not in {"map", "both"}:
                    return False
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def _route_target_location_available(state: "AgentRunState") -> bool:
        """Check the validated route targets, not merely any prior map state."""

        route = state.route
        target_refs = list(route.target_refs) if route is not None else []
        if not target_refs:
            return bool(state.location_refs) or state.active_map_session is not None
        resolved_keys = {
            " ".join(str(key).casefold().split()) for key in state.location_refs
        }
        return all(
            " ".join(str(target).casefold().split()) in resolved_keys
            for target in target_refs
        )


__all__ = ["ToolRegistry"]
