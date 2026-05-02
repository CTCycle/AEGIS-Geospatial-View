from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.decision import PolicyDecision
from server.domain.extraction.models import TurnParseResult
from server.domain.geographics import MapSession

ChatRole = Literal["user", "assistant", "system", "tool"]
ModelProviderMode = Literal["local", "cloud"]

###############################################################################
def utc_chat_message_timestamp() -> datetime:
    return datetime.now(UTC)

###############################################################################
class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=utc_chat_message_timestamp)

###############################################################################
class ChatTurnRequest(BaseModel):
    session_id: int | None = None
    title: str | None = None
    message: str
    datetime: str | None = None
    request_id: str | None = None

###############################################################################
class ContextUsageResponse(BaseModel):
    estimated_input_tokens: int
    selected_context_window: int | None = None
    model_context_limit: int | None = None
    usage_percent: float
    provider: str
    model: str

###############################################################################
class ChatTurnResponse(BaseModel):
    request_id: str
    session_id: int
    assistant_message: str
    turn_contract: TurnParseResult
    decision: PolicyDecision
    tool_payload: dict[str, Any] | None = None
    map_session: MapSession | None = None
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    context_usage: ContextUsageResponse | None = None

###############################################################################
class ChatStreamEvent(BaseModel):
    event: Literal["status", "assistant_delta", "tool_status", "final", "error"]
    data: dict[str, Any]

###############################################################################
class ModelCardDescriptor(BaseModel):
    id: str
    name: str
    description: str
    provider: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class ModelSettingsResponse(BaseModel):
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
    credentials: dict[str, dict[str, str]] = Field(default_factory=dict)

###############################################################################
class ModelLibraryResponse(BaseModel):
    cloud: list[ModelCardDescriptor] = Field(default_factory=list)
    local: list[ModelCardDescriptor] = Field(default_factory=list)

###############################################################################
class OllamaRefreshResponse(BaseModel):
    status: str
    library_models: list[str] = Field(default_factory=list)
    local_models: list[str] = Field(default_factory=list)

###############################################################################
class OllamaPullRequest(BaseModel):
    model: str

###############################################################################
class OllamaPullResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

###############################################################################
class OllamaHealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool | None = None
    detail: str | None = None

###############################################################################
class VectorizationResponse(BaseModel):
    status: str
    indexed_documents: int
    vector_path: str
