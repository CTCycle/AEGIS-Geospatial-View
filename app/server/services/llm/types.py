from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ModelDescriptor:
    name: str
    description: str
    provider: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0.2
    provider: str | None = None
    tools: list["LLMToolDefinition"] | None = None
    tool_choice: Literal["auto", "none", "required"] | str | None = "auto"
    response_json_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class LLMResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)
    tool_calls: list["LLMToolCall"] = field(default_factory=list)


@dataclass(frozen=True)
class LLMToolDefinition:
    name: str
    description: str
    parameters_json_schema: dict[str, Any]


@dataclass(frozen=True)
class LLMToolCall:
    id: str | None = None
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMToolResult:
    tool_call_id: str | None = None
    name: str = ""
    content: dict[str, Any] | str = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class ContextUsage:
    estimated_input_tokens: int
    selected_context_window: int | None
    model_context_limit: int | None
    usage_percent: float
    provider: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_input_tokens": self.estimated_input_tokens,
            "selected_context_window": self.selected_context_window,
            "model_context_limit": self.model_context_limit,
            "usage_percent": self.usage_percent,
            "provider": self.provider,
            "model": self.model,
        }
