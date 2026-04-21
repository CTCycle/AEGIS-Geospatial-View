from __future__ import annotations

import json
from typing import Any

from AEGIS.server.domain.extraction.models import (
    ExtractedIntent,
    ExtractedIntentPatch,
    StageAParserIntent,
    StageBSearchExtraction,
)


###############################################################################
def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


###############################################################################
def _to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return default


###############################################################################
def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


###############################################################################
def parse_structured_json(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return normalize_structured_payload(payload)


###############################################################################
def normalize_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = ExtractedIntent.model_validate(payload)
    return model.model_dump(mode="json")


###############################################################################
def normalize_patch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = ExtractedIntentPatch.model_validate(payload)
    return model.model_dump(mode="json", exclude_none=True)


###############################################################################
def normalize_stage_a_payload(payload: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "location_present": "has_location",
        "hasLocation": "has_location",
        "time_present": "has_time_reference",
        "hasTimeReference": "has_time_reference",
        "search_required": "requires_search",
        "data_required": "requires_data",
        "tools": "required_tools",
        "confidence": "certainty",
    }
    normalized = dict(payload)
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]
    model = StageAParserIntent.model_validate(
        {
            "has_location": _to_bool(normalized.get("has_location"), default=False),
            "location_type": str(normalized.get("location_type")).strip() or None
            if normalized.get("location_type") is not None
            else None,
            "has_time_reference": _to_bool(
                normalized.get("has_time_reference"), default=False
            ),
            "requires_search": _to_bool(
                normalized.get("requires_search"), default=False
            ),
            "requires_data": _to_bool(normalized.get("requires_data"), default=False),
            "required_tools": _to_str_list(normalized.get("required_tools")),
            "certainty": max(
                0.0, min(1.0, _to_float(normalized.get("certainty"), default=0.0))
            ),
        }
    )
    return model.model_dump(mode="json")


###############################################################################
def normalize_stage_b_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "base_map" not in normalized and "basemap" in normalized:
        normalized["base_map"] = normalized.get("basemap")
    if "required_overlays" not in normalized and "overlays" in normalized:
        normalized["required_overlays"] = normalized.get("overlays")
    location = normalized.get("location")
    if not isinstance(location, dict):
        location = {}
    coordinates = normalized.get("coordinates")
    if not isinstance(coordinates, dict):
        coordinates = {}
    model = StageBSearchExtraction.model_validate(
        {
            "location": {
                "address": str(location.get("address")).strip() or None
                if location.get("address") is not None
                else None,
                "city": str(location.get("city")).strip() or None
                if location.get("city") is not None
                else None,
                "country": str(location.get("country")).strip() or None
                if location.get("country") is not None
                else None,
                "location_type": (
                    str(location.get("location_type")).strip() or None
                    if location.get("location_type") is not None
                    else None
                ),
            },
            "coordinates": {
                "latitude": _to_float(coordinates.get("latitude"), default=None)
                if coordinates.get("latitude") not in (None, "")
                else None,
                "longitude": _to_float(coordinates.get("longitude"), default=None)
                if coordinates.get("longitude") not in (None, "")
                else None,
            },
            "time_reference": str(normalized.get("time_reference")).strip() or None
            if normalized.get("time_reference") is not None
            else None,
            "base_map": str(normalized.get("base_map")).strip() or None
            if normalized.get("base_map") is not None
            else None,
            "required_overlays": _to_str_list(normalized.get("required_overlays")),
        }
    )
    return model.model_dump(mode="json")
