from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant", "system", "tool"]
ModelProviderMode = Literal["local", "cloud"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StructuredSearchIntent(BaseModel):
    location_text: str | None = None
    coordinates: dict[str, float] | None = None
    search_radius_m: float | None = None
    representation_type: str | None = None
    requested_overlays: list[str] = Field(default_factory=list)
    user_intent: str | None = None
    datetime_inference: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    should_execute_search: bool = True
    follow_up_question: str | None = None


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
    map_session: dict[str, Any] | None = None
    tool_payload: dict[str, Any] | None = None
    follow_up_required: bool = False


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
    agent_model_provider: str
    agent_model_name: str
    ollama_url: str
    openai_base_url: str | None = None
    google_base_url: str | None = None
    credentials: dict[str, dict[str, bool]]


class VectorizationResponse(BaseModel):
    status: str
    indexed_documents: int
    vector_path: str
