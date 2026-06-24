from __future__ import annotations

import json

from server.domain.agent.pipeline import SpecialistGroup, ToolPlan, ToolPlanStep
from server.domain.extraction.models import TurnParseResult

###############################################################################
class DeterministicToolPlanner:

    # -------------------------------------------------------------------------
    def build_plan(
        self,
        turn: TurnParseResult,
        specialist: SpecialistGroup,
    ) -> ToolPlan:
        steps: list[ToolPlanStep] = []
        for index, capability_id in enumerate(turn.requested_layers, start=1):
            steps.append(
                ToolPlanStep(
                    step_id=f"step-{index}",
                    tool_name="execute_geospatial_capability",
                    capability_id=capability_id,
                    reason=f"Required layer for {turn.entity_target or turn.normalized_action.action_label}.",
                    arguments={"capability_id": capability_id, "arguments": {}},
                )
            )
        steps = self._dedupe_steps(steps)
        selected = sorted({step.tool_name for step in steps})
        return ToolPlan(
            tool_group=specialist,
            candidate_tools=selected,
            selected_tools=selected,
            steps=steps,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe_steps(steps: list[ToolPlanStep]) -> list[ToolPlanStep]:
        unique: list[ToolPlanStep] = []
        seen: set[str] = set()
        for step in steps:
            key = json.dumps(
                {
                    "tool": step.tool_name,
                    "capability": step.capability_id,
                    "arguments": step.arguments,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(step)
        return unique

