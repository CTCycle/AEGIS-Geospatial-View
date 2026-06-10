from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.actions import AgentAction
from server.domain.llm.types import LLMToolDefinition

###############################################################################
class AgentToolName(str, Enum):
    SEARCH_MAPS = "search_maps"
    RESOLVE_LOCATION = "resolve_location"
    RETRIEVE_GEOSPATIAL_DATA = "retrieve_geospatial_data"
    QUERY_DATA_LAYER_API = "query_data_layer_api"
    LOAD_MAP_OVERLAY = "load_map_overlay"
    TOGGLE_MAP_OVERLAY = "toggle_map_overlay"
    DISPLAY_DATASET_ON_MAP = "display_dataset_on_map"
    INTERROGATE_VISIBLE_LAYERS = "interrogate_visible_layers"
    COMBINE_MAP_DATA_WITH_EXTERNAL_SOURCES = "combine_map_data_with_external_sources"

###############################################################################
class AgentToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters_json_schema: dict[str, Any] = Field(default_factory=dict)
    action_scope: list[AgentAction] = Field(default_factory=list)
    requires_map_context: bool = False
    source_manifest_id: str | None = None
    source_capability_id: str | None = None

###############################################################################
class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str | None = None
    name: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


###############################################################################
@dataclass(frozen=True)
class ToolError:
    code: str
    message: str


###############################################################################
@dataclass(frozen=True)
class ToolExecutionEnvelope:
    ok: bool
    data: Any | None = None
    error: ToolError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": None
            if self.error is None
            else {"code": self.error.code, "message": self.error.message},
            "metadata": self.metadata,
        }


###############################################################################
@dataclass(frozen=True)
class RegisteredNativeTool:
    definition: LLMToolDefinition
    handler: Any
