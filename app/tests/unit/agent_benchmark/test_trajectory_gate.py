from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agent_benchmark.trajectories import SCENARIOS, run_scenario

BASELINE_PATH = Path(__file__).parents[2] / "agent_benchmark" / "trajectory_baseline.v1.json"
TOKEN_TOLERANCE = 1.05

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.scenario_id)
async def test_trajectory_stays_within_baseline(scenario: object) -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["scenarios"]
    result = await run_scenario(scenario)  # type: ignore[arg-type]
    expected = baseline[result["scenario_id"]]

    assert result["termination_reason"] == expected["termination_reason"]
    assert result["model_calls"] <= expected["model_calls"]
    assert result["total_estimated_input_tokens"] <= (
        expected["total_estimated_input_tokens"] * TOKEN_TOLERANCE
    ), "Token overhead grew; lower it or refresh the baseline deliberately."
