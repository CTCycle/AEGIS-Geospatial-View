from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.common.time import utc_now
from server.domain.agent.decision import PolicyDecision
from server.domain.extraction.models import TurnParseResult
from server.domain.geographics import MapSession

ChatRole = Literal["user", "assistant", "system", "tool"]
ModelProviderMode = Literal["local", "cloud"]

###############################################################################
class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)

###############################################################################
class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int | None = None
    title: str | None = None
    message: str
    datetime: str | None = None
    request_id: str | None = None

###############################################################################
class ContextUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_input_tokens: int
    selected_context_window: int | None = None
    model_context_limit: int | None = None
    usage_percent: float
    provider: str
    model: str

###############################################################################
class ChatOperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "map_session",
        "direct_answer",
        "capability_catalog",
        "clarification",
        "rejection",
        "error",
    ]
    status: Literal["success", "partial", "failed"]
    message: str
    warnings: list[str] = Field(default_factory=list)
    map_session: MapSession | None = None
    direct_result: dict[str, Any] | None = None

###############################################################################
class ChatTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: int
    assistant_message: str
    turn_contract: TurnParseResult
    decision: PolicyDecision
    operation: ChatOperationResult | None = None
    tool_payload: dict[str, Any] | None = None
    map_session: MapSession | None = None
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    context_usage: ContextUsageResponse | None = None

###############################################################################
class ChatStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal[
        "status",
        "parsed",
        "policy",
        "tool_call_started",
        "tool_call_completed",
        "map_session_created",
        "assistant_delta",
        "final",
        "error",
    ]
    data: dict[str, Any]

###############################################################################
class ModelCardDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    provider: str
    capabilities: list[str] = Field(default_factory=list)
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    tool_support_source: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class ModelSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_provider_mode: ModelProviderMode
    chat_model_provider: str
    chat_model_name: str
    parser_model_provider: str
    parser_model_name: str
    agent_model_provider: str
    agent_model_name: str
    ollama_url: str
    openai_base_url: str | None = None
    google_base_url: str | None = None
    deepseek_base_url: str | None = None
    credentials: dict[str, dict[str, bool]]
    credential_health: dict[str, dict[str, str]] = Field(default_factory=dict)

###############################################################################
class ModelSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_provider_mode: ModelProviderMode | None = None
    chat_model_provider: str | None = None
    chat_model_name: str | None = None
    parser_model_provider: str | None = None
    parser_model_name: str | None = None
    agent_model_provider: str | None = None
    agent_model_name: str | None = None
    ollama_url: str | None = None
    openai_base_url: str | None = None
    google_base_url: str | None = None
    deepseek_base_url: str | None = None
    credentials: dict[str, dict[str, str]] = Field(default_factory=dict)

    # -------------------------------------------------------------------------
    @field_validator(
        "ollama_url", "openai_base_url", "google_base_url", "deepseek_base_url"
    )
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            return normalized
        if not (normalized.startswith("http://") or normalized.startswith("https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return normalized

###############################################################################
class ModelLibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloud: list[ModelCardDescriptor] = Field(default_factory=list)
    local: list[ModelCardDescriptor] = Field(default_factory=list)

###############################################################################
class OllamaRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    library_models: list[str] = Field(default_factory=list)
    local_models: list[str] = Field(default_factory=list)
    local_model_capabilities: list[ModelCardDescriptor] = Field(default_factory=list)

###############################################################################
class OllamaPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str

###############################################################################
class OllamaPullResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

###############################################################################
class OllamaHealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool | None = None
    detail: str | None = None
