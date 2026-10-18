from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.configurations.settings import (
    JsonAgentExecutionSettings,
    JsonChatRuntimeSettings,
    JsonGeospatialSettings,
    JsonGIBSSettings,
    JsonJobsSettings,
    JsonMapSettings,
    JsonNominatimSettings,
    JsonOpenMeteoSettings,
    JsonOverpassSettings,
    JsonRainViewerSettings,
)


class RuntimeSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    nominatim: JsonNominatimSettings
    geospatial: JsonGeospatialSettings
    map: JsonMapSettings
    jobs: JsonJobsSettings
    chat: JsonChatRuntimeSettings
    openmeteo: JsonOpenMeteoSettings
    overpass: JsonOverpassSettings
    rainviewer: JsonRainViewerSettings
    gibs: JsonGIBSSettings
    agent_execution: JsonAgentExecutionSettings
    restart_required: bool = False
    message: str | None = None


class RuntimeSettingsUpdateRequest(BaseModel):
    """A strict top-level partial update; nested values are validated atomically."""

    model_config = ConfigDict(extra="forbid")

    nominatim: dict[str, Any] | None = None
    geospatial: dict[str, Any] | None = None
    map: dict[str, Any] | None = None
    jobs: dict[str, Any] | None = None
    chat: dict[str, Any] | None = None
    openmeteo: dict[str, Any] | None = None
    overpass: dict[str, Any] | None = None
    rainviewer: dict[str, Any] | None = None
    gibs: dict[str, Any] | None = None
    agent_execution: dict[str, Any] | None = None

    def as_patch(self) -> dict[str, dict[str, Any]]:
        return {
            key: value
            for key, value in self.model_dump(exclude_none=True).items()
            if isinstance(value, dict)
        }
