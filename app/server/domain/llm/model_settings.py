from __future__ import annotations

from pydantic import BaseModel


class ModelRoleSettings(BaseModel):
    provider: str
    model: str


class RuntimeModelSettings(BaseModel):
    parser: ModelRoleSettings
    agent: ModelRoleSettings
    chat: ModelRoleSettings
