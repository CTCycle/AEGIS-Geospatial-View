"""Durable conversation state for the native AEGIS harness.

The conversation is the long-lived source of truth.  A model context is a
short-lived projection of this state and an ``AgentRunState`` is the
checkpointable state for one execution.  Keeping this contract independent of
the legacy task/planner models makes follow-up turns resumable without
reconstructing semantic state from a recent-message suffix.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import AgentGoal, CapabilityRoute
from server.domain.agent.decision import ResolvedLocation


class ConversationState(BaseModel):
    """Revisioned, durable state shared by all turns in one conversation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    conversation_id: str
    revision: int = Field(default=0, ge=0)
    active_directives: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
    summary_through_turn_index: int = Field(default=0, ge=0)
    goal: AgentGoal | None = None
    route: CapabilityRoute | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    resolved_locations: dict[str, ResolvedLocation] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    committed_map_session: MapSession | None = None
    unresolved_questions: list[str] = Field(default_factory=list)

    @classmethod
    def empty(cls, conversation_id: str, *, revision: int = 0) -> "ConversationState":
        return cls(conversation_id=conversation_id, revision=max(0, revision))

    @classmethod
    def from_persisted(
        cls,
        conversation_id: str,
        payload: object,
        *,
        revision: int = 0,
    ) -> "ConversationState":
        """Hydrate one validated state, or create the initial empty state."""

        if payload is None:
            return cls.empty(conversation_id, revision=revision)
        state = cls.model_validate(payload)
        if state.conversation_id != conversation_id:
            raise ValueError("Conversation state belongs to another conversation.")
        return state.model_copy(update={"revision": max(state.revision, revision)})

    def memory_projection(self) -> dict[str, Any]:
        """Return the bounded presentation projection used by the UI."""

        result: dict[str, Any] = {}
        if self.resolved_locations:
            key = "active_location" if "active_location" in self.resolved_locations else next(
                iter(self.resolved_locations)
            )
            result["active_location"] = self.resolved_locations[key].model_dump(mode="json")
        if self.committed_map_session is not None:
            result["active_visualization"] = self.committed_map_session.model_dump(mode="json")
        return result


__all__ = ["ConversationState"]
