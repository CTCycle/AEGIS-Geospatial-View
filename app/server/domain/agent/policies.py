from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

###############################################################################
@dataclass(frozen=True)
class ToolAuthorizationResult:
    allowed: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())

###############################################################################
@dataclass(frozen=True)
class ToolValidationResult:
    valid: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
