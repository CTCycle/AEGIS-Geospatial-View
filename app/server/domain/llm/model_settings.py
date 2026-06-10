from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelRoleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    capabilities: list[str] = Field(default_factory=list)
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
    model_config = ConfigDict(extra="forbid")

    parser: ModelRoleSettings
    agent: ModelRoleSettings
    chat: ModelRoleSettings
