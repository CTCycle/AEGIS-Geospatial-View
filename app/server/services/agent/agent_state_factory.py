"""Construction of bounded native-v2 agent state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from server.contracts.geospatial import MapSession
from server.domain.agent.context import AgentContextPackage
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.decision import ResolvedLocation

###############################################################################
class AgentStateFactory:
    """Create a typed state projection from request-scoped lifecycle data."""

    # -------------------------------------------------------------------------
    @staticmethod
    def create(
        *,
        request_id: str,
        run_id: str | None = None,
        conversation_id: str,
        user_message: str,
        active_map_session: MapSession | None = None,
        location_refs: Mapping[str, ResolvedLocation] | None = None,
        evidence_refs: list[str] | None = None,
        context_package: AgentContextPackage | None = None,
    ) -> AgentState:
        normalized_message = str(user_message).strip()
        if not normalized_message:
            raise ValueError("Agent requests require a non-empty user message.")
        if not str(request_id).strip() or not str(conversation_id).strip():
            raise ValueError("Agent requests require request and conversation IDs.")
        context_values: dict[str, Any] = {}
        if context_package is not None:
            context_values = {
                "active_instructions": [
                    item.model_dump(mode="json")
                    for item in context_package.active_instructions
                ],
                "task_state": dict(context_package.task_state or {}),
                "map_memory": dict(context_package.map_memory),
                "conversation_summary": (
                    dict(context_package.conversation_summary)
                    if context_package.conversation_summary is not None
                    else None
                ),
                "recent_messages": [
                    dict(item) for item in context_package.recent_messages
                ],
                "relevant_tool_outcomes": [
                    dict(item) for item in context_package.relevant_tool_outcomes
                ],
                "policy_constraints": dict(context_package.policy_constraints),
                "included_message_ids": list(context_package.included_message_ids),
                "omitted_message_ids": list(context_package.omitted_message_ids),
                "summarized_through_turn_index": (
                    context_package.summarized_through_turn_index
                ),
                "context_allocation": dict(context_package.context_allocation),
                "context_hydrated": True,
            }
        return AgentState(
            request_id=str(request_id),
            run_id=str(run_id) if run_id is not None else None,
            conversation_id=str(conversation_id),
            phase=AgentPhase.RECEIVE_REQUEST,
            user_message=normalized_message,
            active_map_session=active_map_session,
            location_refs=dict(location_refs or {}),
            evidence_refs=list(dict.fromkeys(str(item) for item in evidence_refs or [])),
            **context_values,
        )


__all__ = ["AgentStateFactory"]
