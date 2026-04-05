from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ScopeValidationResult:
    classification: str
    is_actionable: bool
    reason: str | None = None


class ScopeValidator:
    def validate(self, intent: dict[str, Any]) -> ScopeValidationResult:
        task = intent.get("task") if isinstance(intent.get("task"), dict) else {}
        location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
        scope = str(task.get("scope") or "concrete_area")
        if scope == "requires_area_discovery":
            return ScopeValidationResult("requires_area_discovery", False, "requires_area_discovery")
        if not location.get("name") and not location.get("coordinates") and not location.get("bbox"):
            return ScopeValidationResult("missing_area", False, "missing_location")
        if bool(location.get("is_partial")):
            return ScopeValidationResult("broad_but_usable_area", True, "partial_location")
        return ScopeValidationResult("concrete_area", True, None)
