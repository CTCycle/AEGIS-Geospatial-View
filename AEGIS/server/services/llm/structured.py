from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_text": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "text": {"type": ["string", "null"]},
                "coordinates": {"type": ["object", "null"]},
                "bbox": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "place_kind": {"type": ["string", "null"]},
                "ambiguity_reason": {"type": ["string", "null"]},
            },
            "required": ["text", "coordinates", "bbox", "place_kind", "ambiguity_reason"],
        },
        "display_area": {
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
                "radius_m": {"type": ["number", "null"]},
                "map_size_m": {"type": ["number", "null"]},
                "bbox": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "admin_level": {"type": ["string", "null"]},
            },
            "required": ["mode", "radius_m", "map_size_m", "bbox", "admin_level"],
        },
        "view": {
            "type": "object",
            "properties": {
                "view_mode": {"type": "string"},
                "map_type": {"type": "string"},
                "basemap_preference": {"type": ["string", "null"]},
            },
            "required": ["view_mode", "map_type", "basemap_preference"],
        },
        "overlays": {
            "type": "object",
            "properties": {
                "requested": {"type": "array", "items": {"type": "string"}},
                "ranked_candidates": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["requested", "ranked_candidates"],
        },
        "planning": {
            "type": "object",
            "properties": {
                "user_intent": {"type": ["string", "null"]},
                "confidence": {"type": "number"},
                "missing_information": {"type": "array", "items": {"type": "string"}},
                "should_execute_search": {"type": "boolean"},
                "follow_up_question": {"type": ["string", "null"]},
                "reasoning_summary": {"type": ["string", "null"]},
                "datetime_inference": {"type": ["string", "null"]},
            },
            "required": [
                "user_intent",
                "confidence",
                "missing_information",
                "should_execute_search",
                "follow_up_question",
                "reasoning_summary",
                "datetime_inference",
            ],
        },
    },
    "required": ["request_text", "location", "display_area", "view", "overlays", "planning"],
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
    # Backward-compatible normalization from legacy flat schema.
    legacy_coordinates = payload.get("coordinates")
    legacy_location_text = payload.get("location_text")
    legacy_radius = payload.get("search_radius_m")
    legacy_overlays = payload.get("requested_overlays")
    legacy_representation = payload.get("representation_type")
    legacy_user_intent = payload.get("user_intent")
    legacy_dt = payload.get("datetime_inference")
    legacy_missing = payload.get("missing_information")
    legacy_follow_up = payload.get("follow_up_question")
    legacy_should_execute = payload.get("should_execute_search")

    location = payload.get("location")
    if not isinstance(location, dict):
        location = {}
    display_area = payload.get("display_area")
    if not isinstance(display_area, dict):
        display_area = {}
    view = payload.get("view")
    if not isinstance(view, dict):
        view = {}
    overlays = payload.get("overlays")
    if not isinstance(overlays, dict):
        overlays = {}
    planning = payload.get("planning")
    if not isinstance(planning, dict):
        planning = {}

    requested = overlays.get("requested", legacy_overlays if isinstance(legacy_overlays, list) else [])
    if not isinstance(requested, list):
        requested = []
    ranked_candidates = overlays.get("ranked_candidates", [])
    if not isinstance(ranked_candidates, list):
        ranked_candidates = []
    missing_information = planning.get("missing_information", legacy_missing if isinstance(legacy_missing, list) else [])
    if not isinstance(missing_information, list):
        missing_information = []

    mode = str(display_area.get("mode") or "inferred")
    if mode not in {"point", "radius", "bbox", "viewport", "administrative_area", "inferred"}:
        mode = "inferred"
    view_mode = str(view.get("view_mode") or "interactive_map")
    if view_mode not in {"interactive_map", "static_imagery"}:
        view_mode = "interactive_map"
    map_type = str(view.get("map_type") or "auto")
    if map_type not in {"streets", "satellite", "terrain", "light", "dark", "thematic", "auto"}:
        map_type = "auto"

    return {
        "request_text": str(payload.get("request_text") or legacy_location_text or ""),
        "location": {
            "text": location.get("text", legacy_location_text),
            "coordinates": location.get("coordinates", legacy_coordinates),
            "bbox": location.get("bbox", payload.get("bbox")),
            "place_kind": location.get("place_kind"),
            "ambiguity_reason": location.get("ambiguity_reason"),
        },
        "display_area": {
            "mode": mode,
            "radius_m": display_area.get("radius_m", legacy_radius),
            "map_size_m": display_area.get("map_size_m"),
            "bbox": display_area.get("bbox", payload.get("bbox")),
            "admin_level": display_area.get("admin_level"),
        },
        "view": {
            "view_mode": view_mode,
            "map_type": map_type,
            "basemap_preference": view.get("basemap_preference", legacy_representation),
        },
        "overlays": {
            "requested": [str(item) for item in requested if str(item).strip()],
            "ranked_candidates": [item for item in ranked_candidates if isinstance(item, dict)],
        },
        "planning": {
            "user_intent": planning.get("user_intent", legacy_user_intent or "map_search"),
            "confidence": float(planning.get("confidence", 0.0) or 0.0),
            "missing_information": [str(item) for item in missing_information if str(item).strip()],
            "should_execute_search": bool(
                planning.get("should_execute_search", True if legacy_should_execute is None else legacy_should_execute)
            ),
            "follow_up_question": planning.get("follow_up_question", legacy_follow_up),
            "reasoning_summary": planning.get("reasoning_summary"),
            "datetime_inference": planning.get("datetime_inference", legacy_dt or datetime.now(UTC).isoformat()),
        },
    }
