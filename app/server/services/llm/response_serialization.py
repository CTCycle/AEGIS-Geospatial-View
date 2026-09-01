from __future__ import annotations

from server.common.typing import is_json_object

from typing import Any


###############################################################################
def _object_mapping(value: object) -> dict[str, Any]:
    if is_json_object(value):
        return dict(value)
    attributes = getattr(value, "__dict__", None)
    return dict(attributes) if is_json_object(attributes) else {}


###############################################################################
def dump_response_payload(response: object) -> dict[str, Any]:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        payload = _object_mapping(dumped)
    else:
        payload = _object_mapping(response)
    for key in ("usage", "usage_metadata", "response"):
        nested = payload.get(key)
        nested_payload = _object_mapping(nested)
        if nested_payload:
            payload[key] = nested_payload
    return payload
