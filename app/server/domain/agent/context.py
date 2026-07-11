from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now


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


class AgentContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_user_message: str
    active_instructions: list[ConversationDirective] = Field(default_factory=list)
    task_state: dict[str, Any] | None = None
    map_memory: dict[str, Any] = Field(default_factory=dict)
    conversation_summary: dict[str, Any] | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    relevant_tool_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    policy_constraints: dict[str, Any] = Field(default_factory=dict)
    included_message_ids: list[int] = Field(default_factory=list)
    summarized_through_turn_index: int = 0
    omitted_message_ids: list[int] = Field(default_factory=list)
