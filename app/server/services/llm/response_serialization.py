from __future__ import annotations

from server.common.typing import is_json_object, json_object

from typing import Any


###############################################################################
def dump_response_payload(response: object) -> dict[str, Any]:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return json_object(dumped)
    if is_json_object(response):
        return response
    return {}
