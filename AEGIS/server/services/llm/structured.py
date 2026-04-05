from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

MAP_TYPE_ENUM = {"street", "satellite", "terrain", "light", "dark", "thematic", "auto"}
FALLBACK_MODES = {"none", "missing_location", "partial_location", "invalid_scope", "needs_clarification"}
SCOPE_CLASSIFICATIONS = {"concrete_area", "broad_but_usable_area", "missing_area", "requires_area_discovery"}


INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_text": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "coordinates": {"type": ["object", "null"]},
                "bbox": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "granularity": {"type": ["string", "null"]},
                "is_partial": {"type": "boolean"},
                "ambiguity_reason": {"type": ["string", "null"]},
            },
            "required": ["name", "coordinates", "bbox", "granularity", "is_partial", "ambiguity_reason"],
        },
        "map_preferences": {
            "type": "object",
            "properties": {
                "map_type": {"type": "string"},
                "map_type_confidence": {"type": "number"},
                "basemap_preference": {"type": ["string", "null"]},
                "overlay_candidates": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["map_type", "map_type_confidence", "basemap_preference", "overlay_candidates"],
        },
        "task": {
            "type": "object",
            "properties": {
                "user_intent": {"type": "string"},
                "scope": {"type": "string"},
                "requires_external_fact_finding": {"type": "boolean"},
                "is_geographically_actionable": {"type": "boolean"},
            },
            "required": ["user_intent", "scope", "requires_external_fact_finding", "is_geographically_actionable"],
        },
        "temporal_context": {
            "type": "object",
            "properties": {
                "raw_text": {"type": ["string", "null"]},
                "normalized_datetime": {"type": ["string", "null"]},
                "date_range": {"type": ["array", "null"], "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
            },
            "required": ["raw_text", "normalized_datetime", "date_range"],
        },
        "planning": {
            "type": "object",
            "properties": {
                "confidence": {"type": "number"},
                "missing_information": {"type": "array", "items": {"type": "string"}},
                "should_execute_search": {"type": "boolean"},
                "follow_up_question": {"type": ["string", "null"]},
                "fallback_mode": {"type": "string"},
            },
            "required": [
                "confidence",
                "missing_information",
                "should_execute_search",
                "follow_up_question",
                "fallback_mode",
            ],
        },
    },
    "required": ["request_text", "location", "map_preferences", "task", "temporal_context", "planning"],
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
    legacy_coordinates = payload.get("coordinates")
    legacy_location_text = payload.get("location_text")
    legacy_overlays = payload.get("requested_overlays")
    legacy_map_type = payload.get("representation_type")
    legacy_user_intent = payload.get("user_intent")
    legacy_dt = payload.get("datetime_inference")
    legacy_missing = payload.get("missing_information")
    legacy_follow_up = payload.get("follow_up_question")
    legacy_should_execute = payload.get("should_execute_search")

    location = payload.get("location")
    if not isinstance(location, dict):
        location = {}
    map_preferences = payload.get("map_preferences")
    if not isinstance(map_preferences, dict):
        map_preferences = {}
    task = payload.get("task")
    if not isinstance(task, dict):
        task = {}
    temporal_context = payload.get("temporal_context")
    if not isinstance(temporal_context, dict):
        temporal_context = {}
    planning = payload.get("planning")
    if not isinstance(planning, dict):
        planning = {}

    overlay_candidates = map_preferences.get("overlay_candidates", legacy_overlays if isinstance(legacy_overlays, list) else [])
    if not isinstance(overlay_candidates, list):
        overlay_candidates = []
    missing_information = planning.get("missing_information", legacy_missing if isinstance(legacy_missing, list) else [])
    if not isinstance(missing_information, list):
        missing_information = []
    map_type = _normalize_map_type(map_preferences.get("map_type", legacy_map_type))
    map_type_confidence = _normalize_confidence(map_preferences.get("map_type_confidence", 0.0))
    planning_confidence = _normalize_confidence(planning.get("confidence", 0.0))
    fallback_mode = str(planning.get("fallback_mode") or "none").strip().lower()
    if fallback_mode not in FALLBACK_MODES:
        fallback_mode = "none"
    should_execute = bool(planning.get("should_execute_search", True if legacy_should_execute is None else legacy_should_execute))
    location_name = location.get("name", location.get("text", legacy_location_text))
    location_bbox = location.get("bbox", payload.get("bbox"))
    is_partial = bool(location.get("is_partial", False))
    granularity = str(location.get("granularity") or "").strip().lower() or None
    if not is_partial and granularity in {"country", "region", "state"}:
        is_partial = True
    if not is_partial and _is_partial_location_name(location_name):
        is_partial = True
    if _requires_area_discovery(str(payload.get("request_text") or legacy_location_text or "")):
        should_execute = False
        fallback_mode = "invalid_scope"
        missing_information.append("concrete_target_area")

    return {
        "request_text": str(payload.get("request_text") or legacy_location_text or ""),
        "location": {
            "name": location_name,
            "coordinates": location.get("coordinates", legacy_coordinates),
            "bbox": location_bbox,
            "granularity": granularity,
            "is_partial": is_partial,
            "ambiguity_reason": location.get("ambiguity_reason"),
        },
        "map_preferences": {
            "map_type": map_type,
            "map_type_confidence": map_type_confidence,
            "basemap_preference": map_preferences.get("basemap_preference"),
            "overlay_candidates": [str(item) for item in overlay_candidates if str(item).strip()],
        },
        "task": {
            "user_intent": str(task.get("user_intent") or legacy_user_intent or "map_search"),
            "scope": _normalize_scope(str(task.get("scope") or "")),
            "requires_external_fact_finding": bool(task.get("requires_external_fact_finding", False)),
            "is_geographically_actionable": bool(task.get("is_geographically_actionable", True)),
        },
        "temporal_context": {
            "raw_text": temporal_context.get("raw_text"),
            "normalized_datetime": temporal_context.get("normalized_datetime", legacy_dt or datetime.now(UTC).isoformat()),
            "date_range": temporal_context.get("date_range"),
        },
        "planning": {
            "confidence": planning_confidence,
            "missing_information": [str(item) for item in missing_information if str(item).strip()],
            "should_execute_search": should_execute,
            "follow_up_question": planning.get("follow_up_question", legacy_follow_up),
            "fallback_mode": fallback_mode,
        },
    }


def _normalize_map_type(value: Any) -> str:
    normalized = str(value or "auto").strip().lower()
    aliases = {"streets": "street", "standard": "street", "photo": "satellite"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in MAP_TYPE_ENUM else "auto"


def _normalize_confidence(value: Any) -> float:
    try:
        parsed = float(value or 0.0)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


def _is_partial_location_name(location_name: Any) -> bool:
    if not isinstance(location_name, str):
        return False
    name = location_name.strip().lower()
    tokens = {"italy", "france", "germany", "europe", "usa", "united states"}
    return name in tokens


def _requires_area_discovery(text: str) -> bool:
    lowered = text.lower()
    patterns = ("best place in", "least rainy place", "where it rains the least", "find me the best place")
    return any(pattern in lowered for pattern in patterns)


def _normalize_scope(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in SCOPE_CLASSIFICATIONS else "concrete_area"
