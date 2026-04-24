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


@dataclass(frozen=True)
class LLMResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)
