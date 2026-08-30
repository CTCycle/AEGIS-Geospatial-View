from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from server.contracts.geospatial import MapSession
from server.domain.llm.types import LLMToolCall, LLMToolDefinition, LLMToolResult


###############################################################################
@dataclass(frozen=True)
class AgentExecutionContext:
    request_id: str | None = None
    conversation_id: str | None = None
    parsed_request: Any | None = None
    map_state: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    policy_constraints: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


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
    stopped_reason: Literal[
        "final",
        "max_iterations",
        "provider_error",
        "tool_error",
        "budget_exhausted",
        "no_progress",
    ]
    map_session: MapSession | None = None
    model_calls: int = 0
    duplicate_tool_calls: int = 0
    no_progress_steps: int = 0
    failure_category: (
        Literal[
            "model_capability",
            "provider_api",
            "schema_definition",
            "response_parsing",
            "context_limit",
        ]
        | None
    ) = None
    failure_detail: str | None = None
