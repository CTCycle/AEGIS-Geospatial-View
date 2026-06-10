from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from server.domain.geographics import LayerHealthStatus


###############################################################################
@dataclass(frozen=True)
class SourceHealthRecord:
    provider_id: str
    status: LayerHealthStatus
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    stale: bool = False
