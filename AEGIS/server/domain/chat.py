from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

ChatRole = Literal["user", "assistant", "system", "tool"]
ModelProviderMode = Literal["local", "cloud"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StructuredSearchIntent(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_text: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    map_preferences: dict[str, Any] = Field(default_factory=dict)
    task: dict[str, Any] = Field(default_factory=dict)
    temporal_context: dict[str, Any] = Field(default_factory=dict)
    planning: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    should_execute: bool = True
    follow_up_question: str | None = None
    reason: str | None = None


class ChatTurnRequest(BaseModel):
    session_id: int | None = None
    title: str | None = None
    message: str
    datetime: str | None = None


class ChatTurnResponse(BaseModel):
    session_id: int
    assistant_message: str
    structured_intent: dict[str, Any] | None = None
    extracted_state: dict[str, Any] | None = None
    map_session: dict[str, Any] | None = None
    tool_payload: dict[str, Any] | None = None
    follow_up_required: bool = False
    fallback_mode: str | None = None


class ChatStreamEvent(BaseModel):
    event: Literal["status", "assistant_delta", "tool_status", "final", "error"]
    data: dict[str, Any]


class ModelCardDescriptor(BaseModel):
    id: str
    name: str
    description: str
    provider: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class ModelSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
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
    credentials: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ModelLibraryResponse(BaseModel):
    cloud: list[ModelCardDescriptor] = Field(default_factory=list)
    local: list[ModelCardDescriptor] = Field(default_factory=list)


class OllamaRefreshResponse(BaseModel):
    status: str
    library_models: list[str] = Field(default_factory=list)
    local_models: list[str] = Field(default_factory=list)


class OllamaPullRequest(BaseModel):
    model: str


class OllamaPullResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class OllamaHealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    ok: bool | None = None
    detail: str | None = None


class VectorizationResponse(BaseModel):
    status: str
    indexed_documents: int
    vector_path: str
