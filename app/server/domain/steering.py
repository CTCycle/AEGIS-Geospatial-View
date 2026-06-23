from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from server.domain.agent_runs import AgentRunState

MAX_STEERING_MESSAGE_LENGTH = 4000
MAX_CLIENT_MUTATION_ID_LENGTH = 160

###############################################################################
class SteeringMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    client_mutation_id: str | None = None

    # -------------------------------------------------------------------------
    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        if len(normalized) > MAX_STEERING_MESSAGE_LENGTH:
            raise ValueError("message is too long")
        return normalized

    # -------------------------------------------------------------------------
    @field_validator("client_mutation_id")
    @classmethod
    def normalize_mutation_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_CLIENT_MUTATION_ID_LENGTH:
            raise ValueError("client_mutation_id is too long")
        return normalized

###############################################################################
class SteeringMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    steering_id: str
    run_version: int
    aggregated_request: str
    state: AgentRunState

###############################################################################
class SteeringMessageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steering_id: str
    run_id: str
    run_version: int
    content: str
    client_mutation_id: str | None = None
    created_at: datetime
