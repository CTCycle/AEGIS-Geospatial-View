from __future__ import annotations

from server.common.typing import is_json_array, json_object

from datetime import UTC, datetime
from typing import Any

###############################################################################
def infer_datetime(action_payload: dict[str, Any]) -> str:
    value = action_payload.get("datetime_inference")
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(UTC).isoformat()

###############################################################################
def requires_follow_up(action_payload: dict[str, Any]) -> bool:
    planning = json_object(action_payload.get("planning")) or action_payload
    location = json_object(action_payload.get("location"))
    display_area = json_object(action_payload.get("display_area"))
    follow_up = planning.get("follow_up_question")
    if isinstance(follow_up, str) and follow_up.strip():
        return True
    missing = planning.get("missing_information", [])
    if is_json_array(missing):
        normalized = {str(item).lower() for item in missing}
        if normalized.intersection(
            {
                "datetime",
                "location",
                "display_area",
                "unsupported_overlay",
                "conflicting_map_type",
                "low_confidence",
            }
        ):
            return True
    confidence = planning.get("confidence")
    if isinstance(confidence, (int, float)) and float(confidence) < 0.35:
        return True
    if location.get("ambiguity_reason"):
        return True
    if not display_area.get("mode"):
        return True
    return bool(planning.get("should_execute_search") is False)
