from __future__ import annotations

from typing import Any, TypeGuard

###############################################################################
def is_json_object(value: object) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)

###############################################################################
def is_json_array(value: object) -> TypeGuard[list[Any]]:
    return isinstance(value, list)

###############################################################################
def json_object(value: Any) -> dict[str, Any]:
    return value if is_json_object(value) else {}

###############################################################################
def json_array(value: Any) -> list[Any]:
    return value if is_json_array(value) else []
