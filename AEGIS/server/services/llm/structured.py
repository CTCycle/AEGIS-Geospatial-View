from __future__ import annotations

import json
from typing import Any

from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch

INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "location": {
            "type": "object",
            "properties": {
                "address": {"type": ["string", "null"]},
                "city": {"type": ["string", "null"]},
                "country": {"type": ["string", "null"]},
            },
            "required": ["address", "city", "country"],
        },
        "coordinates": {
            "type": "object",
            "properties": {
                "longitude": {"type": ["number", "null"]},
                "latitude": {"type": ["number", "null"]},
            },
            "required": ["longitude", "latitude"],
        },
        "base_map_type": {"type": ["string", "null"]},
        "time_references": {
            "type": "object",
            "properties": {
                "year": {"type": ["integer", "null"]},
                "month": {"type": ["integer", "null"]},
                "day": {"type": ["integer", "null"]},
                "time_range": {"type": "boolean"},
                "start_time": {"type": "array", "items": {"type": "string"}},
                "end_time": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["year", "month", "day", "time_range", "start_time", "end_time"],
        },
        "user_goal": {"type": "string"},
        "filters": {"type": "array", "items": {"type": "string"}},
        "area_of_interest": {"type": ["string", "null"]},
        "certainty": {"type": "number"},
    },
    "required": [
        "location",
        "coordinates",
        "base_map_type",
        "time_references",
        "user_goal",
        "filters",
        "area_of_interest",
        "certainty",
    ],
}


def parse_structured_json(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return normalize_structured_payload(payload)


def normalize_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = ExtractedIntent.model_validate(payload)
    return model.model_dump(mode="json")


def normalize_patch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = ExtractedIntentPatch.model_validate(payload)
    return model.model_dump(mode="json", exclude_none=True)
