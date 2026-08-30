from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CapabilityState = Literal["supported", "unsupported", "unknown"]
FailureCategory = Literal[
    "model_capability",
    "provider_api",
    "schema_definition",
    "response_parsing",
    "context_limit",
]


###############################################################################
@dataclass(frozen=True)
class ModelDescriptor:
    name: str
    description: str
    provider: str
    capabilities: list[str] = field(default_factory=lambda: list[str]())
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


###############################################################################
@dataclass(frozen=True)
class ModelContextProfile:
    provider: str
    model: str
    context_window_tokens: int | None
    maximum_output_tokens: int | None
    default_output_reserve: int
    tokenizer_strategy: str = "chars_per_token_4"
    supports_context_caching: bool = False
    supports_server_compaction: bool = False
    metadata_source: str = "catalog"


###############################################################################
@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.2
    provider: str | None = None
    tools: list["LLMToolDefinition"] | None = None
    tool_choice: Literal["auto", "none", "required"] | str | None = "auto"
    response_json_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())

    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        # Providers perform final request validation so malformed combinations
        # can be reported with a categorized diagnostic at the LLM boundary.
        return None


###############################################################################
@dataclass(frozen=True)
class LLMResult:
    content: str
    raw: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    tool_calls: list["LLMToolCall"] = field(
        default_factory=lambda: list["LLMToolCall"]()
    )
    finish_reason: str | None = None


###############################################################################
@dataclass(frozen=True)
class LLMToolDefinition:
    name: str
    description: str
    parameters_json_schema: dict[str, Any]


###############################################################################
@dataclass(frozen=True)
class LLMToolCall:
    id: str | None = None
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


###############################################################################
@dataclass(frozen=True)
class LLMToolResult:
    tool_call_id: str | None = None
    name: str = ""
    content: dict[str, Any] | list[Any] | str | int | float | bool | None = field(
        default_factory=lambda: dict[str, Any]()
    )
    error: str | None = None
    is_error: bool = False


###############################################################################
@dataclass(frozen=True)
class LLMAssistantToolCallMessage:
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=lambda: list[LLMToolCall]())


###############################################################################
@dataclass(frozen=True)
class LLMToolResultMessage:
    role: Literal["tool"] = "tool"
    tool_call_id: str | None = None
    name: str = ""
    content: str = ""


###############################################################################
@dataclass(frozen=True)
class ContextUsage:
    estimated_input_tokens: int
    selected_context_window: int | None
    model_context_limit: int | None
    usage_percent: float | None
    provider: str
    model: str
    reserved_output_tokens: int = 0
    tool_schema_tokens: int = 0
    response_schema_tokens: int = 0
    safety_margin_tokens: int = 512
    usage_source: str = "estimated"
    usable_prompt_budget_tokens: int | None = None
    current_conversation_tokens: int | None = None
    expected_output_tokens: int | None = None
    context_profile_source: str = "unknown"
    compaction_applied: bool = False

    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_input_tokens": self.estimated_input_tokens,
            "selected_context_window": self.selected_context_window,
            "model_context_limit": self.model_context_limit,
            "usage_percent": self.usage_percent,
            "provider": self.provider,
            "model": self.model,
            "reserved_output_tokens": self.reserved_output_tokens,
            "tool_schema_tokens": self.tool_schema_tokens,
            "response_schema_tokens": self.response_schema_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "usage_source": self.usage_source,
            "usable_prompt_budget_tokens": self.usable_prompt_budget_tokens,
            "current_conversation_tokens": self.current_conversation_tokens,
            "expected_output_tokens": self.expected_output_tokens,
            "context_profile_source": self.context_profile_source,
            "compaction_applied": self.compaction_applied,
        }
