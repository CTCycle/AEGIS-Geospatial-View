"""Native policy boundary for typed tool execution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from server.common.typing import is_json_array
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.policies import ToolAuthorizationResult
from server.domain.agent.tools import RegisteredTool
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


class PolicyEngine:
    """Authorize model actions after route and schema validation.

    The model may select a semantic action, but this boundary owns catalog
    membership, runtime access, route domains, provider allowlists, and
    geography coverage checks.
    """

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        location_resolver: Any | None = None,
        **_: Any,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry
        self.location_resolver = location_resolver

    def authorize(
        self,
        tool: RegisteredTool,
        arguments: BaseModel,
        state: AgentRunState,
    ) -> ToolAuthorizationResult:
        constraints = state.policy_constraints
        if constraints.get("blocked_patterns"):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Request contains blocked policy patterns.",
                metadata={"code": "policy_rejection"},
            )

        allowed_tools = constraints.get("allowed_tool_names")
        if (
            is_json_array(allowed_tools)
            and allowed_tools
            and tool.definition.name not in {str(item) for item in allowed_tools}
        ):
            return ToolAuthorizationResult(
                allowed=False,
                reason=f"Tool '{tool.definition.name}' is not allowed by the run policy.",
                metadata={"code": "tool_not_allowed"},
            )

        route = state.route
        if route is None:
            return ToolAuthorizationResult(
                allowed=False,
                reason="A validated capability route is required.",
                metadata={"code": "route_required"},
            )

        if not self._route_allows_tool(tool, route):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Tool is outside the validated capability route.",
                metadata={"code": "route_domain_mismatch"},
            )

        capability_id = str(getattr(arguments, "capability_id", "") or "").strip()
        if not capability_id:
            return ToolAuthorizationResult(allowed=True)

        if (
            state.capability_ids
            and capability_id not in state.capability_ids
            and capability_id not in state.excluded_capability_ids
        ):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Capability is outside the validated shortlist.",
                metadata={"code": "capability_not_shortlisted"},
            )

        capability = (
            self.capability_registry.get_capability(capability_id)
            if self.capability_registry is not None
            else None
        )
        if capability is None:
            return ToolAuthorizationResult(
                allowed=False,
                reason="Capability is not present in the catalog.",
                metadata={"code": "unknown_capability"},
            )

        if self.runtime_registry is not None:
            if not self.runtime_registry.is_enabled(capability_id):
                return ToolAuthorizationResult(
                    allowed=False,
                    reason="Capability is disabled.",
                    metadata={"code": "capability_disabled"},
                )
            if not self.runtime_registry.access_available(capability_id):
                reason = (
                    self.runtime_registry.access_reason(capability_id)
                    if callable(getattr(self.runtime_registry, "access_reason", None))
                    else None
                )
                return ToolAuthorizationResult(
                    allowed=False,
                    reason=reason or "Capability access is unavailable.",
                    metadata={"code": "capability_unavailable"},
                )

        coverage = str(capability.get("coverage") or "").strip().casefold()
        location = self._location_for_arguments(arguments, state)
        country = str(getattr(location, "country", "") or "").strip().casefold()
        if coverage == "united-states" and country and country not in {
            "us",
            "usa",
            "united states",
            "united states of america",
        }:
            return ToolAuthorizationResult(
                allowed=False,
                reason="Capability is outside its declared geographic coverage.",
                metadata={
                    "code": "unavailable_coverage",
                    "coverage": coverage,
                    "country": country,
                },
            )

        allowed_provider_ids = constraints.get("allowed_provider_ids")
        provider_id = str(capability.get("providerId") or capability.get("provider_id") or "")
        if (
            is_json_array(allowed_provider_ids)
            and allowed_provider_ids
            and provider_id
            and provider_id.casefold()
            not in {str(item).casefold() for item in allowed_provider_ids}
        ):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Capability provider is outside the validated provider allowlist.",
                metadata={"code": "provider_not_allowed"},
            )

        return ToolAuthorizationResult(allowed=True)

    @staticmethod
    def _route_allows_tool(tool: RegisteredTool, route: Any) -> bool:
        if not tool.domains or CapabilityDomain.MIXED in tool.domains:
            return True
        route_domains = {route.primary_domain, *route.secondary_domains}
        special_tools = {
            "resolve_geospatial_location",
            "inspect_evidence",
            "transform_evidence",
        }
        if tool.definition.name in special_tools:
            return True
        if tool.definition.name == "apply_map_plan":
            return route.presentation in {"map", "both"}
        return bool(tool.domains.intersection(route_domains))

    @staticmethod
    def _location_for_arguments(arguments: BaseModel, state: AgentRunState) -> Any | None:
        location_ref = str(getattr(arguments, "location_ref", "") or "").strip()
        if location_ref:
            for key, location in state.location_refs.items():
                if str(key).casefold() == location_ref.casefold():
                    return location
            return None
        if len(state.location_refs) == 1:
            return next(iter(state.location_refs.values()))
        if state.active_map_session is not None:
            return state.active_map_session.resolved_location
        return None


__all__ = ["PolicyEngine"]
