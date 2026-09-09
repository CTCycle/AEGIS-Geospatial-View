from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    "map.render_ack",
]

###############################################################################
class RealtimeClientMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = REALTIME_PROTOCOL_VERSION
    type: RealtimeClientMessageType
    message_id: str = Field(min_length=1, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH)
    payload: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class RealtimeResumePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = Field(default=None, max_length=160)
    after_sequence: int = Field(default=0, ge=0)

###############################################################################
class RealtimeStartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=12000)
    client_request_id: str = Field(min_length=1, max_length=160)
    timezone: str | None = Field(default=None, max_length=64)

    # -------------------------------------------------------------------------
    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    # -------------------------------------------------------------------------
    @field_validator("client_request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_request_id must not be empty")
        return normalized

###############################################################################
class RealtimeSteerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    client_mutation_id: str = Field(min_length=1, max_length=160)

    # -------------------------------------------------------------------------
    @field_validator("run_id", "client_mutation_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifier must not be empty")
        return normalized

    # -------------------------------------------------------------------------
    @field_validator("message")
    @classmethod
    def normalize_steering_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

###############################################################################
class RealtimeCancelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=400)

###############################################################################
class RealtimeRenderAckPayload(BaseModel):
    """Bounded browser evidence for one prepared map revision."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    run_version: int = Field(ge=1)
    map_session_id: str = Field(min_length=1, max_length=160)
    collection_revision: int = Field(ge=0)
    status: Literal["ready", "failed"]
    viewport_bounds: list[float] | None = None
    checks: dict[str, bool] = Field(default_factory=lambda: dict[str, bool]())
    overlay_results: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    failure_code: str | None = Field(default=None, max_length=120)

    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def require_viewport_for_ready(self) -> "RealtimeRenderAckPayload":
        if self.status == "ready" and self.viewport_bounds is None:
            raise ValueError("A ready render acknowledgment must include viewport bounds")
        return self

    # -------------------------------------------------------------------------
    @field_validator("viewport_bounds")
    @classmethod
    def validate_viewport_bounds(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("viewport_bounds must contain four numeric values")
        normalized = [float(item) for item in value]
        if any(not (-float("inf") < item < float("inf")) for item in normalized):
            raise ValueError("viewport_bounds must be finite")
        west, south, east, north = normalized
        if not -180 <= west <= 180 or not -180 <= east <= 180 or not -90 <= south <= north <= 90:
            raise ValueError("viewport_bounds are outside EPSG:4326 limits")
        if west > east and (west < 150 or east > -150):
            raise ValueError("viewport_bounds longitude order is invalid")
        return normalized

    # -------------------------------------------------------------------------
    @field_validator("checks")
    @classmethod
    def validate_checks(cls, value: dict[str, bool]) -> dict[str, bool]:
        if len(value) > 32:
            raise ValueError("checks are too large")
        return value

    # -------------------------------------------------------------------------
    @field_validator("overlay_results")
    @classmethod
    def sanitize_overlay_results(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 256:
            raise ValueError("overlay_results are too large")
        allowed: set[str] = {
            "overlay_id",
            "capability_id",
            "source_present",
            "layer_present",
            "loaded",
            "metadata_only",
            "visibility_matches",
            "style_valid",
            "zoom_range_valid",
            "rendered_feature_count",
            "failure_code",
        }
        sanitized: list[dict[str, Any]] = []
        for raw in value:
            item: dict[str, Any] = {key: raw[key] for key in allowed if key in raw}
            if "overlay_id" in item and (
                not isinstance(item["overlay_id"], str)
                or len(item["overlay_id"]) > 160
            ):
                raise ValueError("overlay result identity is invalid")
            if "capability_id" in item and (
                not isinstance(item["capability_id"], str)
                or not item["capability_id"]
                or len(item["capability_id"]) > 160
            ):
                raise ValueError("overlay capability identity is invalid")
            for key in (
                "source_present",
                "layer_present",
                "loaded",
                "metadata_only",
                "visibility_matches",
            ):
                if key in item and not isinstance(item[key], bool):
                    raise ValueError(f"overlay result {key} must be boolean")
            if "rendered_feature_count" in item and (
                not isinstance(item["rendered_feature_count"], int)
                or item["rendered_feature_count"] < 0
            ):
                raise ValueError("rendered_feature_count must be non-negative")
            if "failure_code" in item and (
                item["failure_code"] is not None
                and (not isinstance(item["failure_code"], str) or len(item["failure_code"]) > 120)
            ):
                raise ValueError("overlay failure code is invalid")
            sanitized.append(item)
        return sanitized

###############################################################################
class RealtimeServerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = REALTIME_PROTOCOL_VERSION
    type: str = Field(min_length=1, max_length=80)
    message_id: str | None = Field(
        default=None, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH
    )
    correlation_id: str | None = Field(
        default=None, max_length=MAX_REALTIME_MESSAGE_ID_LENGTH
    )
    conversation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
