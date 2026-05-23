from __future__ import annotations

from server.services.agent.manifest_action_resolver import (
    UserCapabilityAccess,
    select_geospatial_capabilities,
)


def test_agentic_geospatial_policy_gates_general_factual_query() -> None:
    selected = select_geospatial_capabilities(
        "who founded Rome",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert selected == []


def test_agentic_geospatial_policy_gates_block_indiscriminate_layers() -> None:
    selected = select_geospatial_capabilities(
        "show all layers on the map",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert selected[0].status == "refused"
    assert selected[0].capability_id == "category_offer"


def test_agentic_geospatial_policy_gates_credentials_before_manual_use() -> None:
    selected = select_geospatial_capabilities(
        "show live traffic",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert any(
        item.capability_id == "tomtom_traffic_flow"
        and item.status == "missing-credential"
        for item in selected
    )
