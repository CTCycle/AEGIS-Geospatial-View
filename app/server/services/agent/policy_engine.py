"""Native policy boundary for typed tool execution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from server.common.identifiers import normalize_target_key
from server.common.typing import is_json_array, json_array, json_object
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.policies import ToolAuthorizationResult
from server.domain.agent.tools import RegisteredTool
from server.services.geospatial.capability_registry import CapabilityRegistry, coverage_matches
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class PolicyEngine:
    """Authorize model actions after route and schema validation.

    The model may select a semantic action, but this boundary owns catalog
    membership, runtime access, route domains, provider allowlists, and
    geography coverage checks.
    """

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
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

        if capability_id in state.excluded_capability_ids:
            return ToolAuthorizationResult(
                allowed=False,
                reason="Capability was excluded after a failed attempt in this run.",
                metadata={"code": "capability_excluded"},
            )

        if state.capability_ids and capability_id not in state.capability_ids:
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

        failed_id = state.failed_data_targets.get(
            normalize_target_key(str(getattr(arguments, "location_ref", "") or ""))
        )
        failed = (
            self.capability_registry.get_capability(failed_id)
            if failed_id and self.capability_registry is not None
            else None
        )
        if failed is not None and not _is_substitute(capability, failed):
            return ToolAuthorizationResult(
                allowed=False,
                reason=(
                    "The source for this place failed and this capability does not supply the "
                    "same variable and kind of data. Do not substitute it; answer with what "
                    "was retrieved and state that this place's data could not be retrieved."
                ),
                metadata={"code": "not_a_substitute"},
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

        location = self._location_for_arguments(arguments, state)
        coverage = _declared_coverage(capability)
        if location is not None and not coverage_matches(coverage, location):
            alternative = self._covering_alternative(capability, location, state)
            return ToolAuthorizationResult(
                allowed=False,
                reason=_coverage_explanation(capability, coverage, location, alternative),
                metadata={
                    "code": "unavailable_coverage",
                    "coverage": coverage,
                    "country": location.country or "",
                    "alternative_id": str(alternative.get("id") or "") if alternative else "",
                    "rejected_name": _capability_name(capability),
                    "alternative_name": _capability_name(alternative) if alternative else "",
                    "region": _coverage_region(coverage),
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

    # -------------------------------------------------------------------------
    @staticmethod
    def _route_allows_tool(tool: RegisteredTool, route: Any) -> bool:
        if tool.definition.name == "execute_geospatial_capability":
            if not route_allows_capability_execution(route):
                return False
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

    # -------------------------------------------------------------------------
    def _covering_alternative(
        self,
        capability: dict[str, Any],
        location: ResolvedLocation,
        state: AgentRunState,
    ) -> dict[str, Any] | None:
        """Return the next eligible source for the same phenomenon at ``location``.

        Candidates are the manifest's own ``fallback_ids``, the run's ranked
        shortlist, and finally any catalog source that substitutes for the
        rejected one (same phenomenon and kind of data, ``_is_substitute``);
        one qualifies when it is enabled and accessible, not excluded, and
        covers the place.
        """

        if self.capability_registry is None:
            return None
        rejected_id = str(capability.get("id") or "")
        phenomena = _routing_hints(capability)
        contract = json_object(capability.get("executionContract"))
        fallback_ids = [str(item) for item in json_array(contract.get("fallback_ids"))]
        for candidate_id in dict.fromkeys([*fallback_ids, *state.capability_ids]):
            candidate = self.capability_registry.get_capability(candidate_id)
            if (
                candidate is not None
                and phenomena & _routing_hints(candidate)
                and self._covers_place(candidate, rejected_id, location, state)
            ):
                return candidate
        substitutes = [
            item
            for item in self.capability_registry.list_capabilities()
            if json_object(item.get("executionContract")) and _is_substitute(item, capability)
        ]
        substitutes.sort(
            key=lambda item: (-len(phenomena & _routing_hints(item)), str(item.get("id") or ""))
        )
        return next(
            (
                item
                for item in substitutes
                if self._covers_place(item, rejected_id, location, state)
            ),
            None,
        )

    # -------------------------------------------------------------------------
    def _covers_place(
        self,
        candidate: dict[str, Any],
        rejected_id: str,
        location: ResolvedLocation,
        state: AgentRunState,
    ) -> bool:
        candidate_id = str(candidate.get("id") or "")
        if candidate_id == rejected_id or candidate_id in state.excluded_capability_ids:
            return False
        if self.runtime_registry is not None and not (
            self.runtime_registry.is_enabled(candidate_id)
            and self.runtime_registry.access_available(candidate_id)
        ):
            return False
        return coverage_matches(_declared_coverage(candidate), location)

    # -------------------------------------------------------------------------
    @staticmethod
    def _location_for_arguments(arguments: BaseModel, state: AgentRunState) -> ResolvedLocation | None:
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


###############################################################################
def _is_substitute(candidate: dict[str, Any], failed: dict[str, Any]) -> bool:
    """Whether a source supplies the failed one's variable in the same kind of data."""

    kind = "render_support"
    return bool(_routing_hints(candidate) & _routing_hints(failed)) and (
        json_object(candidate.get("executionContract")).get(kind)
        == json_object(failed.get("executionContract")).get(kind)
    )

###############################################################################
def _declared_coverage(capability: dict[str, Any]) -> str:
    contract = json_object(capability.get("executionContract"))
    return str(contract.get("coverage") or capability.get("coverage") or "").strip()

###############################################################################
def _routing_hints(capability: dict[str, Any]) -> set[str]:
    hints = json_array(json_object(capability.get("agenticUse")).get("plannerHints"))
    return {str(item).strip().casefold() for item in hints if str(item).strip()}

###############################################################################
def _capability_name(capability: dict[str, Any]) -> str:
    label = json_object(capability.get("metadata")).get("label")
    return str(capability.get("name") or label or capability.get("id") or "This source")

###############################################################################
def _coverage_region(coverage: str) -> str:
    words = coverage.replace("-", " ").replace("_", " ").split()
    return " ".join(word.upper() if len(word) <= 3 else word.capitalize() for word in words)

###############################################################################
def _coverage_explanation(
    capability: dict[str, Any],
    coverage: str,
    location: ResolvedLocation,
    alternative: dict[str, Any] | None,
) -> str:
    """User-facing reason a source cannot serve a place, with the next option."""

    region = _coverage_region(coverage)
    place = location.label
    text = (
        f"{_capability_name(capability)} only covers {region or 'a limited area'}, "
        f"so it has no data for {place}."
    )
    if alternative is not None:
        return (
            f"{text} {_capability_name(alternative)} covers {place} for the same kind "
            "of data and is now available: use it instead, and tell the user plainly "
            f"that {_capability_name(capability)} only covers {region or 'a limited area'} "
            f"and {_capability_name(alternative)} is shown in its place."
        )
    return (
        f"{text} No other available source covers {place}. "
        "Which other data should I show there?"
    )

###############################################################################
def route_allows_capability_execution(route: Any) -> bool:
    """Whether a route may execute provider capabilities at all.

    Shared by tool exposure and authorization so a tool is never offered to
    the model only to be rejected when called.
    """

    route_domains = {route.primary_domain, *route.secondary_domains}
    return route.primary_domain is not CapabilityDomain.MAP_STATE and bool(
        route_domains
        & {CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.SPATIAL_ANALYSIS}
    )


def is_text_location_lookup(route: Any) -> bool:
    """Whether a route asks only for where a place is, answered as text.

    The location resolver alone answers it: no provider capability can add
    to the result, and the resolved coordinates are what must be delivered.
    """

    return (
        route is not None
        and route.task_mode == "execute"
        and route.primary_domain is CapabilityDomain.PLACE_SEARCH
        and route.presentation == "text"
        and route.operation in {"geocode", "resolve_location"}
        and not route_allows_capability_execution(route)
    )


__all__ = [
    "PolicyEngine",
    "is_text_location_lookup",
    "route_allows_capability_execution",
]
