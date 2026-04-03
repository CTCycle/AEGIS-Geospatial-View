from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "location_text": {"type": ["string", "null"]},
        "coordinates": {"type": ["object", "null"]},
        "search_radius_m": {"type": ["number", "null"]},
        "representation_type": {"type": ["string", "null"]},
        "requested_overlays": {"type": "array", "items": {"type": "string"}},
        "user_intent": {"type": ["string", "null"]},
        "datetime_inference": {"type": ["string", "null"]},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "should_execute_search": {"type": "boolean"},
        "follow_up_question": {"type": ["string", "null"]},
    },
    "required": [
        "location_text",
        "coordinates",
        "search_radius_m",
        "representation_type",
        "requested_overlays",
        "user_intent",
        "datetime_inference",
        "missing_information",
        "should_execute_search",
        "follow_up_question",
    ],
}


def parse_structured_json(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("location_text", None)
    payload.setdefault("coordinates", None)
    payload.setdefault("search_radius_m", 2500.0)
    payload.setdefault("representation_type", "map")
    payload.setdefault("requested_overlays", [])
    payload.setdefault("user_intent", "map_search")
    payload.setdefault("datetime_inference", datetime.now(UTC).isoformat())
    payload.setdefault("missing_information", [])
    payload.setdefault("should_execute_search", True)
    payload.setdefault("follow_up_question", None)
    return payload
