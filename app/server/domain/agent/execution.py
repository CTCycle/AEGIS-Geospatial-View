from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from server.domain.geographics import MapSession
from server.domain.llm.types import LLMToolCall, LLMToolDefinition, LLMToolResult


###############################################################################
@dataclass(frozen=True)
class AgentExecutionContext:
    request_id: str | None = None
    session_id: str | None = None
    parsed_request: Any | None = None
    map_state: dict[str, Any] = field(default_factory=dict)
    policy_constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


###############################################################################
@dataclass(frozen=True)
class AgentToolLoopRequest:
    provider: str
    model: str
    messages: list[dict[str, Any]]
    tools: list[LLMToolDefinition]
    temperature: float
    max_tokens: int | None = None
    context: AgentExecutionContext = field(default_factory=AgentExecutionContext)


###############################################################################
@dataclass(frozen=True)
class AgentToolLoopResult:
    final_text: str
    tool_calls: list[LLMToolCall]
    tool_results: list[LLMToolResult]
    iterations: int
    stopped_reason: Literal["final", "max_iterations", "provider_error", "tool_error"]
    map_session: MapSession | None = None
