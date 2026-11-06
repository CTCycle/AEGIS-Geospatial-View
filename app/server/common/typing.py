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

###############################################################################
def with_nested_scalars(record: dict[str, Any]) -> dict[str, Any]:
    """Return ``record`` plus its nested objects' scalars under dotted keys.

    A single-object payload keeps its measurements in sub-objects
    (``current.temperature_2m``); exposing them as flat keys lets a record
    operation address them by the exact path the model is shown.
    """

    flat = dict(record)
    for key, value in record.items():
        if is_json_object(value):
            flat.update(
                {
                    f"{key}.{name}": item
                    for name, item in value.items()
                    if isinstance(item, (str, int, float)) and not isinstance(item, bool)
                }
            )
    return flat
