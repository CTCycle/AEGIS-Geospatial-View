from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

###############################################################################
class AgentAction(str, Enum):
    MAP_SEARCH = "map_search"
    LOCATION_RENDER = "location_render"
    GEOSPATIAL_DATA_RETRIEVAL = "geospatial_data_retrieval"
    DATA_LAYER_QUERY = "data_layer_query"
    OVERLAY_CONTROL = "overlay_control"
    DATASET_DISPLAY = "dataset_display"
    VISIBLE_LAYER_INTERROGATION = "visible_layer_interrogation"
    MAP_EXTERNAL_SOURCE_COMBINATION = "map_external_source_combination"
    CHAT_RESPONSE = "chat_response"
    UNKNOWN = "unknown"

###############################################################################
class ActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AgentAction
    label: str
    description: str
    tool_groups: list[str]
    requires_map_context: bool = False
    allows_external_sources: bool = False

###############################################################################
ACTION_CATALOG: dict[AgentAction, ActionDefinition] = {
    AgentAction.MAP_SEARCH: ActionDefinition(
        action=AgentAction.MAP_SEARCH,
        label="Map search",
        description="Search for a place or map view and prepare a viewport.",
        tool_groups=["location", "map"],
        requires_map_context=False,
    ),
    AgentAction.LOCATION_RENDER: ActionDefinition(
        action=AgentAction.LOCATION_RENDER,
        label="Location render",
        description="Resolve a location and render it on the map.",
        tool_groups=["location", "map"],
        requires_map_context=False,
    ),
    AgentAction.GEOSPATIAL_DATA_RETRIEVAL: ActionDefinition(
        action=AgentAction.GEOSPATIAL_DATA_RETRIEVAL,
        label="Geospatial data retrieval",
        description="Retrieve geospatial source data for a resolved area.",
        tool_groups=["location", "data"],
        requires_map_context=True,
    ),
    AgentAction.DATA_LAYER_QUERY: ActionDefinition(
        action=AgentAction.DATA_LAYER_QUERY,
        label="Data layer query",
        description="Query a manifest-backed layer or dataset API.",
        tool_groups=["layer", "data"],
        requires_map_context=True,
    ),
    AgentAction.OVERLAY_CONTROL: ActionDefinition(
        action=AgentAction.OVERLAY_CONTROL,
        label="Overlay control",
        description="Load, toggle, or configure map overlays.",
        tool_groups=["overlay"],
        requires_map_context=True,
    ),
    AgentAction.DATASET_DISPLAY: ActionDefinition(
        action=AgentAction.DATASET_DISPLAY,
        label="Dataset display",
        description="Display a dataset or layer on the map.",
        tool_groups=["overlay", "dataset"],
        requires_map_context=True,
    ),
    AgentAction.VISIBLE_LAYER_INTERROGATION: ActionDefinition(
        action=AgentAction.VISIBLE_LAYER_INTERROGATION,
        label="Visible layer interrogation",
        description="Summarize or inspect currently visible layers.",
        tool_groups=["layer", "summary"],
        requires_map_context=True,
    ),
    AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION: ActionDefinition(
        action=AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION,
        label="Map and external source combination",
        description="Combine map state or layer data with permitted external sources.",
        tool_groups=["layer", "external"],
        requires_map_context=True,
        allows_external_sources=True,
    ),
    AgentAction.CHAT_RESPONSE: ActionDefinition(
        action=AgentAction.CHAT_RESPONSE,
        label="Chat response",
        description="Answer conversationally without map operations.",
        tool_groups=[],
        requires_map_context=False,
    ),
    AgentAction.UNKNOWN: ActionDefinition(
        action=AgentAction.UNKNOWN,
        label="Unknown",
        description="The requested action is unclear or too low-confidence.",
        tool_groups=[],
        requires_map_context=False,
    ),
}
