from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

###############################################################################
# Browser map-capture contracts.
#
# The client captures the rendered MapLibre canvas and posts it to
# POST /api/geospatial/render-captures, keyed by the run identity tuple the
# render handshake already carries.  The agent loop reads the capture back on
# the next vision-enabled model step.
###############################################################################


class RenderCaptureCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    run_version: int = Field(ge=1)
    map_session_id: str = Field(min_length=1, max_length=160)
    collection_revision: int = Field(ge=0)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    image_base64: str = Field(min_length=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    viewport_bounds: list[float] | None = Field(default=None)


class RenderCaptureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    map_session_id: str
    collection_revision: int
    stored: bool
    message: str | None = Field(default=None)