from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AccessKeyProvider = Literal["openai", "gemini"]


class AccessKeyCreateRequest(BaseModel):
    provider: AccessKeyProvider
    access_key: str = Field(max_length=8192)

    @field_validator("access_key", mode="before")
    @classmethod
    def normalize_access_key(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("access_key must be a string")
        no_control = "".join(ch for ch in value if ord(ch) >= 32)
        normalized = no_control.strip()
        if not normalized:
            raise ValueError("Access key must not be empty")
        return normalized


class AccessKeyResponse(BaseModel):
    id: int
    provider: AccessKeyProvider
    is_active: bool
    fingerprint: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class AccessKeyDeleteResponse(BaseModel):
    success: bool
