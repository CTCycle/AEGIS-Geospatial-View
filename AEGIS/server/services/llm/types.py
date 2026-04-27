from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class LLMResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)


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
