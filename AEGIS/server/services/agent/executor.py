from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def infer_datetime(intent: dict[str, Any]) -> str:
    value = intent.get("datetime_inference")
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(UTC).isoformat()


def requires_follow_up(intent: dict[str, Any]) -> bool:
    follow_up = intent.get("follow_up_question")
    if isinstance(follow_up, str) and follow_up.strip():
        return True
    missing = intent.get("missing_information", [])
    return isinstance(missing, list) and "datetime" in [str(item).lower() for item in missing]
