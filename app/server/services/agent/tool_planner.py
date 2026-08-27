from __future__ import annotations

import json
from typing import Any

from server.domain.agent.pipeline import SpecialistGroup, ToolPlan, ToolPlanStep
from server.contracts.extraction import TurnParseResult
from server.services.agent.tool_argument_builder import ToolArgumentBuilder

###############################################################################
class DeterministicToolPlanner:

    # -------------------------------------------------------------------------
    def __init__(self, argument_builder: ToolArgumentBuilder | None = None) -> None:
        self.argument_builder = argument_builder or ToolArgumentBuilder()

    # -------------------------------------------------------------------------
    def build_plan(
        self,
        turn: TurnParseResult,
        specialist: SpecialistGroup,
        memory_snapshot: dict[str, Any] | None = None,
    ) -> ToolPlan:
        steps: list[ToolPlanStep] = []
        visualization_update = self._build_visualization_update(turn)
        capability_ids = self._select_capabilities(turn)
        for index, capability_id in enumerate(capability_ids, start=1):
            steps.append(
                ToolPlanStep(
                    step_id=f"step-{index}",
                    tool_name="execute_geospatial_capability",
                    capability_id=capability_id,
                    reason=f"Required layer for {turn.entity_target or turn.normalized_action.action_label}.",
                    arguments={
                        "capability_id": capability_id,
                        "arguments": self.argument_builder.build_capability_arguments(
                            capability_id,
                            turn,
                            memory_snapshot,
                        ),
                    },
                )
            )
        for provider_id, layer_id in self._select_provider_layers(turn):
            steps.append(
                ToolPlanStep(
                    step_id=f"step-{len(steps) + 1}",
                    tool_name="render_geospatial_provider_layer",
                    reason="Provider-native layer was explicitly selected for rendering.",
                    arguments={
                        "provider_id": provider_id,
                        "layer_id": layer_id,
                    },
                )
            )
        if self._requires_provider_discovery(turn, specialist):
            provider_id = next(
                (item for item in turn.required_data_sources if item.strip()),
                "",
            )
            if provider_id:
                steps.append(
                    ToolPlanStep(
                        step_id=f"step-{len(steps) + 1}",
                        tool_name="fetch_geospatial_provider_layers",
                        reason="Provider-native layer discovery was explicitly requested.",
                        arguments={
                            "provider_id": provider_id,
                            "query": turn.entity_target or turn.user_text,
                            "limit": 50,
                            "refresh": False,
                        },
                    )
                )
        steps = self._dedupe_steps(steps)
        selected = sorted({step.tool_name for step in steps})
        return ToolPlan(
            tool_group=specialist,
            candidate_tools=selected,
            selected_tools=selected,
            steps=steps,
            visualization_update=visualization_update,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _select_capabilities(turn: TurnParseResult) -> list[str]:
        selected: list[str] = []
        text = turn.user_text.casefold()
        commands = getattr(turn, "overlay_commands", [])
        has_fetching_command = any(
            command.action in {"add", "show", "update"} for command in commands
        )
        if not commands or has_fetching_command:
            selected.extend(
                layer_id for layer_id in turn.requested_layers if ":" not in layer_id
            )
            for command in commands:
                if command.action not in {"add", "show", "update"}:
                    continue
                selected.extend(command.selector.capability_ids)
        if not turn.requested_layers:
            if "air quality" in text and "forecast" in text:
                selected.append("get_air_quality_forecast")
            elif "weather" in text or ("forecast" in text and "rain" in text):
                selected.append("get_weather_forecast")

            if any(marker in text for marker in ("nearby", "poi", "amenities")):
                selected.append("get_nearby_poi")

            if turn.task_class == "direct_query" and any(
                marker in text for marker in ("coordinate", "latitude", "longitude")
            ):
                selected.append("location_to_coordinates")
        return list(dict.fromkeys(selected))

    # -------------------------------------------------------------------------
    @staticmethod
    def _select_provider_layers(turn: TurnParseResult) -> list[tuple[str, str]]:
        selections: list[tuple[str, str]] = []
        for layer in turn.requested_layers:
            if ":" not in layer:
                continue
            provider_id, layer_id = [part.strip() for part in layer.split(":", 1)]
            if provider_id and layer_id:
                selections.append((provider_id, layer_id))
        return list(dict.fromkeys(selections))

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_visualization_update(turn: TurnParseResult) -> dict[str, object]:
        basemap = turn.requested_basemap
        if (
            not basemap
            and turn.task_class == "map_search"
            and not turn.requested_layers
            and not turn.overlay_commands
        ):
            basemap = "osm_default"
        update: dict[str, object] = {}
        if basemap:
            update["basemap_replacement"] = basemap
        has_fetching_command = any(
            command.action in {"add", "show", "update"}
            for command in turn.overlay_commands
        )
        if turn.requested_layers and (not turn.overlay_commands or has_fetching_command):
            update["add_layer_ids"] = list(dict.fromkeys(turn.requested_layers))
        if turn.overlay_commands:
            update["overlay_commands"] = [
                command.model_dump(mode="json") for command in turn.overlay_commands
            ]
        return update

    # -------------------------------------------------------------------------
    @staticmethod
    def _requires_provider_discovery(
        turn: TurnParseResult,
        specialist: SpecialistGroup,
    ) -> bool:
        return (
            specialist in {"map_layers", "environmental_data"}
            and turn.required_tool_category == "provider_native_discovery"
            and bool(turn.required_data_sources)
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
