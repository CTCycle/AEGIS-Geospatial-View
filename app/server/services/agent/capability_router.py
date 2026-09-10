"""Deterministic validation of the model-owned capability route."""

from __future__ import annotations

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentState,
    CapabilityRoute,
    CapabilityRouteDecision,
)
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class CapabilityRouter:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

    # -------------------------------------------------------------------------
    def validate_route(
        self,
        proposed: CapabilityRoute,
        *,
        user_message: str,
        active_state: AgentState,
    ) -> CapabilityRouteDecision:
        """Validate route semantics and return only an eligible shortlist."""

        reasons: list[str] = []
        rejected: list[str] = []
        valid_explicit_ids: list[str] = []
        for capability_id in proposed.explicit_capability_ids:
            normalized_id = capability_id.strip()
            capability = self.capability_registry.get_capability(normalized_id)
            if capability is None:
                rejected.append(normalized_id)
                reasons.append("unknown_capability_id")
                continue
            if not self.runtime_registry.is_enabled(normalized_id):
                rejected.append(normalized_id)
                reasons.append("capability_disabled")
                continue
            if not self.runtime_registry.access_available(normalized_id):
                rejected.append(normalized_id)
                reasons.append("capability_unavailable")
                continue
            valid_explicit_ids.append(normalized_id)

        # A new map cannot be prepared without a validated location.  Keep this
        # prerequisite server-owned so a model route that asks for a map but
        # forgets it still enters the typed location tool phase.
        if (
            proposed.task_mode == "execute"
            and proposed.presentation in {"map", "both"}
            and active_state.active_map_session is None
            and not proposed.requires_location
        ):
            proposed = proposed.model_copy(update={"requires_location": True})
            reasons.append("location_required_for_new_map")

        route_domains = {proposed.primary_domain, *proposed.secondary_domains}
        if proposed.primary_domain is CapabilityDomain.MAP_STATE:
            if active_state.active_map_session is None:
                return CapabilityRouteDecision(
                    status="clarification",
                    route=proposed,
                    rejected_capability_ids=rejected,
                    reason_codes=[*dict.fromkeys([*reasons, "active_map_required"])],
                    clarification_question=(
                        "Which active map should I update, or would you like me to "
                        "prepare a new map first?"
                    ),
                )

        if proposed.task_mode == "clarify":
            if not proposed.clarification_question:
                return CapabilityRouteDecision(
                    status="rejected",
                    route=proposed,
                    rejected_capability_ids=rejected,
                    reason_codes=[*dict.fromkeys([*reasons, "clarification_question_missing"])],
                )
            return CapabilityRouteDecision(
                status="clarification",
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=[*dict.fromkeys([*reasons, "model_requested_clarification"])],
                clarification_question=proposed.clarification_question,
            )

        if proposed.clarification_question is not None:
            reasons.append("clarification_question_not_allowed")

        candidates = (
            []
            if proposed.explicit_capability_ids and not valid_explicit_ids
            else self.capability_registry.shortlist(
                domains=route_domains,
                queries=proposed.capability_queries,
                explicit_ids=valid_explicit_ids,
                runtime_registry=self.runtime_registry,
                limit=12,
            )
        )
        capability_ids = [
            str(item.get("id") or "").strip()
            for item in candidates
            if str(item.get("id") or "").strip() and _is_executable_candidate(item)
        ]

        if proposed.task_mode == "execute" and not capability_ids:
            return CapabilityRouteDecision(
                status="no_capability",
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=[*dict.fromkeys([*reasons, "no_eligible_capability"])],
            )

        status = "rejected" if reasons and "clarification_question_not_allowed" in reasons else "accepted"
        return CapabilityRouteDecision(
            status=status,
            route=proposed,
            capability_ids=capability_ids,
            rejected_capability_ids=rejected,
            reason_codes=list(dict.fromkeys(reasons)),
        )


def _is_executable_candidate(capability: dict[str, object]) -> bool:
    """Keep renderer-only descriptors out of the generic provider tool."""

    kind = str(
        capability.get("capabilityKind")
        or capability.get("capability_kind")
        or ""
    ).strip().casefold()
    return kind != "basemap"
