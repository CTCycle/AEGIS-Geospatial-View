from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ModelRoleSettings(BaseModel):
    provider: str
    model: str
    capabilities: list[str] = []
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    tool_support_source: Literal[
        "catalog",
        "provider",
        "ollama_show",
        "ollama_probe",
        "unknown",
    ] = "unknown"


class RuntimeModelSettings(BaseModel):
    parser: ModelRoleSettings
    agent: ModelRoleSettings
    chat: ModelRoleSettings
