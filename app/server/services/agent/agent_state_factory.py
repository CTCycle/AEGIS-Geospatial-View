"""Construction of bounded native-v2 agent state."""

from __future__ import annotations

from collections.abc import Mapping

from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.decision import ResolvedLocation


###############################################################################
class AgentStateFactory:
    """Create a typed state projection from request-scoped lifecycle data."""

    @staticmethod
    def create(
        *,
        request_id: str,
        conversation_id: str,
        user_message: str,
        active_map_session: MapSession | None = None,
        location_refs: Mapping[str, ResolvedLocation] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> AgentState:
        normalized_message = str(user_message).strip()
        if not normalized_message:
            raise ValueError("Agent requests require a non-empty user message.")
        if not str(request_id).strip() or not str(conversation_id).strip():
            raise ValueError("Agent requests require request and conversation IDs.")
        return AgentState(
            request_id=str(request_id),
            conversation_id=str(conversation_id),
            phase=AgentPhase.RECEIVE_REQUEST,
            user_message=normalized_message,
            active_map_session=active_map_session,
            location_refs=dict(location_refs or {}),
            evidence_refs=list(dict.fromkeys(str(item) for item in evidence_refs or [])),
        )


__all__ = ["AgentStateFactory"]
