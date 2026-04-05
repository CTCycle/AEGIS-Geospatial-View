from __future__ import annotations

from AEGIS.server.services.search.scope_validator import ScopeValidator


def test_scope_validator_requires_area_discovery() -> None:
    result = ScopeValidator().validate(
        {
            "task": {"scope": "requires_area_discovery"},
            "location": {"name": "Italy"},
        }
    )
    assert result.is_actionable is False
    assert result.classification == "requires_area_discovery"


def test_scope_validator_concrete_area() -> None:
    result = ScopeValidator().validate(
        {
            "task": {"scope": "concrete_area"},
            "location": {"name": "Venice", "is_partial": False},
        }
    )
    assert result.is_actionable is True
    assert result.classification == "concrete_area"
