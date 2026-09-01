"""Load and validate the reusable geographic-agent scenario matrix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_DIMENSIONS = frozenset(
    {
        "intent",
        "dataset",
        "geographic_scale",
        "temporal",
        "ambiguity",
        "tool_count",
        "availability",
        "conversation",
    }
)

ALLOWED_LANES = frozenset({"model_in_loop", "scripted_fault", "live_smoke"})
ALLOWED_CLARIFICATION = frozenset({"required", "not_required", "allowed"})
ALLOWED_TASK_CLASSES = frozenset(
    {"map_search", "direct_query", "general_question", "unclear"}
)
ALLOWED_RENDERING_TYPES = frozenset(
    {"map", "point", "line", "polygon", "raster", "chart", "text", "none"}
)


def _string_set(value: object) -> set[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    normalized = {item.strip() for item in value if item.strip()}
    return normalized


def validate_scenario_matrix(document: object) -> list[str]:
    """Return actionable validation errors without executing any scenario."""

    if not isinstance(document, dict):
        return ["matrix must be a JSON object"]
    if document.get("matrix_version") != "1.0":
        return ["matrix_version must be '1.0'"]
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return ["scenarios must be a non-empty list"]

    errors: list[str] = []
    scenario_ids: set[str] = set()
    for index, scenario in enumerate(scenarios):
        prefix = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{prefix} must be an object")
            continue
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            errors.append(f"{prefix}.id must be a non-empty string")
        elif scenario_id in scenario_ids:
            errors.append(f"duplicate scenario id: {scenario_id}")
        else:
            scenario_ids.add(scenario_id)

        lane = scenario.get("lane")
        if lane not in ALLOWED_LANES:
            errors.append(f"{prefix}.lane is not supported: {lane!r}")
        has_prompt = isinstance(scenario.get("prompt"), str) and bool(
            scenario["prompt"].strip()
        )
        turns = scenario.get("turns")
        has_turns = (
            isinstance(turns, list)
            and bool(turns)
            and all(isinstance(turn, str) and turn.strip() for turn in turns)
        )
        if not has_prompt and not has_turns and lane != "scripted_fault":
            errors.append(f"{prefix} requires a non-empty prompt or turns")
        if lane == "scripted_fault" and not isinstance(scenario.get("failure"), str):
            errors.append(f"{prefix}.failure must be a string for scripted_fault")

        dimensions = scenario.get("dimensions")
        if not isinstance(dimensions, dict):
            errors.append(f"{prefix}.dimensions must be an object")
        else:
            missing = REQUIRED_DIMENSIONS - dimensions.keys()
            errors.extend(
                f"{prefix}.dimensions missing {key}" for key in sorted(missing)
            )
            for key in REQUIRED_DIMENSIONS & dimensions.keys():
                value = dimensions[key]
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"{prefix}.dimensions.{key} must be a non-empty string"
                    )

        expected = scenario.get("expected")
        if not isinstance(expected, dict):
            errors.append(f"{prefix}.expected must be an object")
            continue
        task_classes = _string_set(expected.get("task_classes"))
        if task_classes is None or not task_classes:
            errors.append(
                f"{prefix}.expected.task_classes must be a non-empty string list"
            )
        elif not task_classes <= ALLOWED_TASK_CLASSES:
            errors.append(f"{prefix}.expected.task_classes contains an unknown class")
        capability_families = _string_set(expected.get("capability_families"))
        if capability_families is None:
            errors.append(
                f"{prefix}.expected.capability_families must be a string list"
            )
        clarification = expected.get("clarification")
        if clarification not in ALLOWED_CLARIFICATION:
            errors.append(
                f"{prefix}.expected.clarification is invalid: {clarification!r}"
            )
        rendering_types = _string_set(expected.get("rendering_types"))
        if rendering_types is None or not rendering_types:
            errors.append(
                f"{prefix}.expected.rendering_types must be a non-empty string list"
            )
        elif not rendering_types <= ALLOWED_RENDERING_TYPES:
            errors.append(f"{prefix}.expected.rendering_types contains an unknown type")
        for key in ("provenance_required", "fabrication_forbidden"):
            if not isinstance(expected.get(key), bool):
                errors.append(f"{prefix}.expected.{key} must be boolean")
        minimum_tool_count = expected.get("minimum_tool_count")
        if not isinstance(minimum_tool_count, int) or minimum_tool_count < 0:
            errors.append(
                f"{prefix}.expected.minimum_tool_count must be a non-negative integer"
            )

    return errors


def load_scenario_matrix(path: Path | None = None) -> dict[str, Any]:
    """Load the checked-in matrix and fail closed when its contract is invalid."""

    matrix_path = path or Path(__file__).with_name("scenario_matrix.v1.json")
    document = json.loads(matrix_path.read_text(encoding="utf-8"))
    errors = validate_scenario_matrix(document)
    if errors:
        raise ValueError(
            "Invalid geographic-agent scenario matrix:\n- " + "\n- ".join(errors)
        )
    return document
