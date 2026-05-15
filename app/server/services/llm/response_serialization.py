from __future__ import annotations

from typing import Any


def dump_response_payload(response: object) -> dict[str, Any]:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(response, dict):
        return response
    return {}
