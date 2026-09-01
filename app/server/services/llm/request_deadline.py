from __future__ import annotations

from time import monotonic
from typing import Any

from server.services.llm.types import LLMRequest


REQUEST_DEADLINE_METADATA_KEY = "deadline_monotonic"


def remaining_request_seconds(request: LLMRequest) -> float | None:
    """Return the bounded request time left, if the caller supplied one."""

    value: Any = request.metadata.get(REQUEST_DEADLINE_METADATA_KEY)
    if isinstance(value, bool):
        return None
    try:
        deadline = float(value)
    except (TypeError, ValueError):
        return None
    if deadline != deadline or deadline in {float("inf"), float("-inf")}:
        return None
    return deadline - monotonic()


def request_is_expired(request: LLMRequest) -> bool:
    remaining = remaining_request_seconds(request)
    return remaining is not None and remaining <= 0.0
