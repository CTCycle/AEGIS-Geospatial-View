from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now

###############################################################################
class ConversationDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directive_id: str
    normalized_text: str
    original_user_text: str
    source_turn_index: int
    scope: Literal["conversation", "current_task"] = "conversation"
    status: Literal["active", "superseded", "revoked"] = "active"
    superseding_directive_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

###############################################################################
class AgentContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_user_message: str
    active_directives: list[ConversationDirective] = Field(
        default_factory=lambda: list[ConversationDirective]()
    )
    task_state: dict[str, Any] | None = None
    map_memory: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    summary: dict[str, Any] | None = None
    recent_messages: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    relevant_tool_outcomes: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    policy_constraints: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    included_message_ids: list[int] = Field(default_factory=lambda: list[int]())
    summarized_through_turn_index: int = 0
    omitted_message_ids: list[int] = Field(default_factory=lambda: list[int]())
    context_allocation: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


###############################################################################
class AgentContextView(BaseModel):
    """Ephemeral, bounded semantic projection for one model decision.

    Conversation state and the checkpointable run state remain authoritative;
    this view is rebuilt before every model call and is never used as a durable
    source of truth.
    """

    model_config = ConfigDict(extra="forbid")

    active_directives: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    task_state: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    map_memory: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    summary: dict[str, Any] | None = None
    relevant_tool_outcomes: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    recent_observations: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    render_observations: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    policy_constraints: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )
    context_selection: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )

    @classmethod
    def from_state(
        cls,
        state: Any,
        *,
        recent_observations: list[dict[str, Any]] | None = None,
        render_observations: list[dict[str, Any]] | None = None,
    ) -> "AgentContextView":
        """Build a model view without persisting or mutating state."""

        return cls(
            active_directives=[dict(item) for item in state.active_directives],
            task_state=dict(state.task_state),
            map_memory=dict(state.map_memory),
            summary=(
                dict(state.summary)
                if state.summary is not None
                else None
            ),
            relevant_tool_outcomes=[
                dict(item) for item in state.relevant_tool_outcomes
            ],
            recent_observations=[
                dict(item) for item in (recent_observations or [])
            ],
            render_observations=[
                dict(item) for item in (render_observations or [])
            ],
            policy_constraints=dict(state.policy_constraints),
            context_selection={
                "included_message_ids": list(state.included_message_ids),
                "omitted_message_ids": list(state.omitted_message_ids),
                "summarized_through_turn_index": state.summarized_through_turn_index,
            },
        )
