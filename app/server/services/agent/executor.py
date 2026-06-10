from __future__ import annotations

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
    planning = (
        action_payload.get("planning")
        if isinstance(action_payload.get("planning"), dict)
        else action_payload
    )
    location = (
        action_payload.get("location")
        if isinstance(action_payload.get("location"), dict)
        else {}
    )
    display_area = (
        action_payload.get("display_area")
        if isinstance(action_payload.get("display_area"), dict)
        else {}
    )
    follow_up = planning.get("follow_up_question")
    if isinstance(follow_up, str) and follow_up.strip():
        return True
    missing = planning.get("missing_information", [])
    if isinstance(missing, list):
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
