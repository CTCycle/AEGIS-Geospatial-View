from __future__ import annotations

from server.domain.agent.actions import ACTION_CATALOG, AgentAction


###############################################################################
def test_every_concrete_action_has_definition() -> None:
    for action in AgentAction:
        assert action in ACTION_CATALOG


###############################################################################
def test_tool_groups_are_declared_for_non_chat_actions() -> None:
    for action, definition in ACTION_CATALOG.items():
        if action in {AgentAction.CHAT_RESPONSE, AgentAction.UNKNOWN}:
            continue
        assert definition.tool_groups


###############################################################################
def test_action_values_are_stable_strings() -> None:
    assert [item.value for item in AgentAction] == [
        "map_search",
        "location_render",
        "geospatial_data_retrieval",
        "data_layer_query",
        "overlay_control",
        "dataset_display",
        "visible_layer_interrogation",
        "map_external_source_combination",
        "chat_response",
        "unknown",
    ]
