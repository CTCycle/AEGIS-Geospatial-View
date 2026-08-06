from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

REALTIME_PROTOCOL_VERSION = 1
REALTIME_SUBPROTOCOL = "aegis.realtime.v1"
MAX_REALTIME_MESSAGE_BYTES = 64 * 1024
MAX_REALTIME_MESSAGE_ID_LENGTH = 160

RealtimeClientMessageType = Literal[
    "session.resume",
    "run.start",
    "run.steer",
    "run.cancel",
    "heartbeat.pong",
    "heartbeat.ping",
]


class RealtimeClientMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = REALTIME_PROTOCOL_VERSION
    type: RealtimeClientMessageType
    message_id: str = Field(min_length=1, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH)
    payload: dict[str, Any] = Field(default_factory=dict)


class RealtimeResumePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = Field(default=None, max_length=160)
    after_sequence: int = Field(default=0, ge=0)


class RealtimeStartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=12000)
    client_request_id: str = Field(min_length=1, max_length=160)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    @field_validator("client_request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_request_id must not be empty")
        return normalized


class RealtimeSteerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    client_mutation_id: str = Field(min_length=1, max_length=160)

    @field_validator("run_id", "client_mutation_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifier must not be empty")
        return normalized

    @field_validator("message")
    @classmethod
    def normalize_steering_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized


class RealtimeCancelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=400)


class RealtimeServerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = REALTIME_PROTOCOL_VERSION
    type: str = Field(min_length=1, max_length=80)
    message_id: str | None = Field(default=None, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH)
    correlation_id: str | None = Field(default=None, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH)
    conversation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
