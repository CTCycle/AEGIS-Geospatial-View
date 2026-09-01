from __future__ import annotations

from pathlib import Path

from tests.agent_benchmark.scenario_matrix import (
    load_scenario_matrix,
    validate_scenario_matrix,
)


###############################################################################
def test_checked_in_scenario_matrix_is_complete_and_unique() -> None:
    matrix = load_scenario_matrix()

    assert len(matrix["scenarios"]) >= 20
    assert len({item["id"] for item in matrix["scenarios"]}) == len(matrix["scenarios"])
    assert validate_scenario_matrix(matrix) == []


###############################################################################
def test_matrix_covers_required_geographic_agent_dimensions() -> None:
    matrix = load_scenario_matrix()
    dimensions = matrix["scenarios"]

    assert {item["dimensions"]["conversation"] for item in dimensions} >= {
        "fresh",
        "follow_up",
    }
    assert {item["dimensions"]["ambiguity"] for item in dimensions} >= {
        "none",
        "place_name",
        "missing_reference",
    }
    assert {item["dimensions"]["availability"] for item in dimensions} >= {
        "supported",
        "unsupported",
        "timeout",
        "malformed",
    }
    assert {item["dimensions"]["geographic_scale"] for item in dimensions} >= {
        "point",
        "city",
        "neighborhood",
        "region",
        "country",
        "bounding_box",
    }
    assert all(item["expected"]["fabrication_forbidden"] for item in dimensions)


###############################################################################
def test_held_out_matrix_validates_and_uses_generalized_invariants() -> None:
    path = Path(__file__).parents[2] / "agent_benchmark" / "scenario_matrix.holdout.v1.json"
    matrix = load_scenario_matrix(path)

    assert len(matrix["scenarios"]) >= 10
    assert all(item.get("invariants") for item in matrix["scenarios"])
    assert "location_target_consistency" in {
        invariant
        for item in matrix["scenarios"]
        for invariant in item["invariants"]
    }
