from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EndpointValidationResult:
    capability_id: str
    ok: bool
    status_code: int | None
    data_format: str
    message: str
