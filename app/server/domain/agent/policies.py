from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


###############################################################################
@dataclass(frozen=True)
class AgentPolicyConstraints:
    requires_location: bool
    blocked_patterns: list[str] = field(default_factory=list)
    allowed_tool_names: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


###############################################################################
@dataclass(frozen=True)
class ToolAuthorizationResult:
    allowed: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


###############################################################################
@dataclass(frozen=True)
class ToolValidationResult:
    valid: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
