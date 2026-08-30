from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.contracts.runs import AgentRunState

MAX_STEERING_MESSAGE_LENGTH = 4000
MAX_CLIENT_MUTATION_ID_LENGTH = 160

SteeringDeltaKind = Literal[
    "scope_change",
    "exclusion",
    "add_dataset",
    "comparison",
    "clarification",
    "instruction",
]


###############################################################################
class SteeringDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SteeringDeltaKind
    text: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    preserve_evidence: bool = True
    invalidates_scope_dependent_evidence: bool = False


###############################################################################
def classify_steering_delta(message: str) -> SteeringDelta:
    normalized = message.strip()
    lowered = normalized.lower()
    radius = re.search(r"\b(\d+(?:\.\d+)?)\s*(km|mi|miles?)\b", lowered)
    if radius or any(
        token in lowered for token in ("expand the area", "radius", "zoom")
    ):
        return SteeringDelta(
            kind="scope_change",
            text=normalized,
            parameters={"radius_text": radius.group(0) if radius else None},
            invalidates_scope_dependent_evidence=True,
        )
    if any(
        token in lowered for token in ("exclude", "remove", "west of", "western side")
    ):
        return SteeringDelta(
            kind="exclusion",
            text=normalized,
            parameters={"filter": normalized},
            invalidates_scope_dependent_evidence=True,
        )
    if any(
        token in lowered
        for token in ("add ", "include ", "air-quality", "weather", "environment")
    ):
        return SteeringDelta(kind="add_dataset", text=normalized)
    if any(token in lowered for token in ("compare", "comparison", "summarize")):
        return SteeringDelta(kind="comparison", text=normalized)
    if "?" in normalized:
        return SteeringDelta(kind="clarification", text=normalized)
    return SteeringDelta(kind="instruction", text=normalized)


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
    duplicate: bool = False
    delta: SteeringDelta | None = None
    state_delta_applied: bool = False


###############################################################################
class SteeringMessageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steering_id: str
    run_id: str
    run_version: int
    content: str
    client_mutation_id: str | None = None
    state_delta_applied: bool = False
    created_at: datetime
