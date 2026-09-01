from __future__ import annotations

import json
from typing import Any

from server.domain.agent.pipeline import (
    SpecialistGroup,
    ToolInputBinding,
    ToolPlan,
    ToolPlanStep,
)
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
                    parallel_group="capability-fetch",
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
                    parallel_group="provider-layer-fetch",
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
                        parallel_group="provider-discovery",
                        arguments={
                            "provider_id": provider_id,
                            "query": turn.entity_target or turn.map_target or "",
                            "limit": 50,
                            "refresh": False,
                        },
                    )
                )
        steps = self._dedupe_steps(steps)
        steps = self._apply_atomic_relationships(steps, turn)
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
        update: dict[str, object] = {}
        if basemap:
            update["basemap_replacement"] = basemap
        has_fetching_command = any(
            command.action in {"add", "show", "update"}
            for command in turn.overlay_commands
        )
        if turn.requested_layers and (
            not turn.overlay_commands or has_fetching_command
        ):
            update["add_layer_ids"] = list(dict.fromkeys(turn.requested_layers))
        if turn.viewport_intent is not None:
            # A viewport-only follow-up still belongs to the deterministic map
            # pipeline.  The execution layer reads the typed intent from the
            # turn contract when rebuilding the session.
            update["viewport_change"] = True
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

    # -------------------------------------------------------------------------
    @classmethod
    def _apply_atomic_relationships(
        cls,
        steps: list[ToolPlanStep],
        turn: TurnParseResult,
    ) -> list[ToolPlanStep]:
        """Project typed atomic-task relationships onto executable steps.

        The planner does not infer dependencies from prose. It only connects
        model-declared task references to the exact capabilities already
        selected from the catalog. Unmatched references remain visible in the
        task state and cannot silently change tool ordering.
        """

        if not turn.atomic_tasks:
            return steps
        task_steps: dict[str, list[str]] = {}
        task_payloads: dict[str, dict[str, Any]] = {}
        for index, raw_task in enumerate(turn.atomic_tasks):
            if not isinstance(raw_task, dict):
                continue
            task_id = cls._task_id(raw_task, index)
            task_payloads[task_id] = raw_task
            references = raw_task.get("required_layers")
            layer_refs = (
                [str(item).strip() for item in references if str(item).strip()]
                if isinstance(references, list)
                else []
            )
            if layer_refs:
                matched = [
                    step.step_id
                    for step in steps
                    if any(
                        cls._step_matches_reference(step, ref) for ref in layer_refs
                    )
                ]
            else:
                # Without an explicit capability reference there is no safe
                # ownership mapping.  Positional matching would project a
                # geocode/map task graph onto unrelated capabilities and can
                # create artificial dependency cycles or suppress parallel
                # provider fetches after one optional provider fails.
                matched = []
            task_steps[task_id] = list(dict.fromkeys(matched))

        updated: list[ToolPlanStep] = []
        for step in steps:
            owning_tasks = [
                task_id
                for task_id, step_ids in task_steps.items()
                if step.step_id in step_ids
            ]
            dependencies = list(step.depends_on)
            input_bindings = list(step.input_bindings)
            output_refs = list(step.output_refs)
            for task_id in owning_tasks:
                task = task_payloads[task_id]
                for dependency_ref in cls._string_list(task.get("depends_on")):
                    dependency_steps = cls._resolve_task_reference(
                        dependency_ref, task_steps
                    )
                    dependencies.extend(
                        dependency_step
                        for dependency_step in dependency_steps
                        if dependency_step != step.step_id
                    )
                output_refs.extend(cls._string_list(task.get("output_refs")))
                input_bindings.extend(
                    cls._parse_input_bindings(task.get("input_refs"), task_steps)
                )
            unique_dependencies = list(dict.fromkeys(dependencies))
            unique_bindings = list(
                {
                    (
                        binding.target,
                        binding.source_step_id,
                        binding.source_path,
                        binding.required,
                    ): binding
                    for binding in input_bindings
                }.values()
            )
            updated.append(
                step.model_copy(
                    update={
                        "depends_on": unique_dependencies,
                        "input_bindings": unique_bindings,
                        "output_refs": list(dict.fromkeys(output_refs)),
                    }
                )
            )
        return updated

    # -------------------------------------------------------------------------
    @staticmethod
    def _task_id(task: dict[str, Any], index: int) -> str:
        value = str(task.get("id") or "").strip()
        return value or f"task-{index + 1}"

    # -------------------------------------------------------------------------
    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    # -------------------------------------------------------------------------
    @staticmethod
    def _step_matches_reference(step: ToolPlanStep, reference: str) -> bool:
        candidates = {
            step.step_id,
            str(step.capability_id or ""),
            str(step.arguments.get("capability_id") or ""),
        }
        provider_id = str(step.arguments.get("provider_id") or "").strip()
        layer_id = str(step.arguments.get("layer_id") or "").strip()
        if provider_id and layer_id:
            candidates.add(f"{provider_id}:{layer_id}")
        return reference.strip() in candidates

    # -------------------------------------------------------------------------
    @classmethod
    def _resolve_task_reference(
        cls,
        reference: str,
        task_steps: dict[str, list[str]],
    ) -> list[str]:
        normalized = reference.strip()
        if normalized.isdigit():
            normalized = f"task-{normalized}"
        if normalized in task_steps:
            return task_steps[normalized]
        if normalized.startswith("task-") and normalized in task_steps:
            return task_steps[normalized]
        return [normalized] if normalized.startswith("step-") else []

    # -------------------------------------------------------------------------
    @classmethod
    def _parse_input_bindings(
        cls,
        value: object,
        task_steps: dict[str, list[str]],
    ) -> list[ToolInputBinding]:
        bindings: list[ToolInputBinding] = []
        for raw_ref in cls._string_list(value):
            if "->" not in raw_ref:
                continue
            source_ref, target = (part.strip() for part in raw_ref.split("->", 1))
            if not source_ref or not target:
                continue
            source_id, separator, source_path = source_ref.partition(":")
            source_steps = cls._resolve_task_reference(source_id, task_steps)
            if not separator or not source_path or len(source_steps) != 1:
                continue
            bindings.append(
                ToolInputBinding(
                    target=target,
                    source_step_id=source_steps[0],
                    source_path=source_path,
                )
            )
        return bindings
