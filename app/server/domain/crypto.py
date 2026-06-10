from __future__ import annotations

from dataclasses import dataclass


###############################################################################
@dataclass(frozen=True)
class EncryptedSecret:
    value: str
    key_version: int
