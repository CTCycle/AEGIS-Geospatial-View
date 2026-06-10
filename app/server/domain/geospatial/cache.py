from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


###############################################################################
class CacheLookupStatus(str, Enum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"


###############################################################################
@dataclass(frozen=True)
class CacheLookup:
    status: CacheLookupStatus
    value: Any | None = None

    # -------------------------------------------------------------------------
    @property
    def usable(self) -> bool:
        return self.status in {CacheLookupStatus.HIT, CacheLookupStatus.STALE}
