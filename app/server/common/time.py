from __future__ import annotations

import math

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

###############################################################################
def utc_now() -> datetime:
    return datetime.now(UTC)

###############################################################################
def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)

###############################################################################
def parse_retry_after(raw: str | None) -> float | None:
    """Seconds to wait from a Retry-After value: delta-seconds or HTTP-date."""

    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        pass
    else:
        return max(0.0, seconds) if math.isfinite(seconds) else None
    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at.astimezone(UTC) - utc_now()).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None
