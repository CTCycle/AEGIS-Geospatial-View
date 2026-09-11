from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.agent.map_plan import MapPlan


###############################################################################
def test_map_plan_parses_discriminated_actions() -> None:
    plan = MapPlan.model_validate(
        {
            "expected_collection_revision": 7,
            "actions": [
                {
                    "action": "set_layer_opacity",
                    "instance_id": "traffic:zurich",
                    "opacity": 0.5,
                },
                {
                    "action": "set_viewport",
                    "strategy": "preserve_current",
                },
            ],
        }
    )

    assert plan.actions[0].action == "set_layer_opacity"
    assert plan.actions[1].action == "set_viewport"


###############################################################################
@pytest.mark.parametrize(
    "payload",
    [
        {
            "expected_collection_revision": 0,
            "actions": [
                {
                    "action": "set_layer_opacity",
                    "instance_id": "traffic",
                    "opacity": 1.1,
                }
            ],
        },
        {
            "expected_collection_revision": 0,
            "actions": [{"action": "unknown_action"}],
        },
        {
            "expected_collection_revision": 0,
            "actions": [
                {
                    "action": "set_basemap",
                    "capability_id": "osm",
                    "unexpected": True,
                }
            ],
        },
    ],
)
def test_map_plan_rejects_invalid_actions(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MapPlan.model_validate(payload)
