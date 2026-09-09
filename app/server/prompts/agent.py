"""Prompt declarations and builders for the native geospatial tool loop."""

from __future__ import annotations

import json
from typing import Any, cast

from server.domain.agent.evidence import AgentEvidenceSummary, AgentWorkingState

from server.prompts.common import (
    GROUNDING_REQUIREMENTS,
    INTERNAL_INFORMATION_RESTRICTIONS,
    SUPPORTED_AEGIS_SCOPE,
    UNCERTAINTY_RULES,
)

NATIVE_AGENT_SYSTEM_PROMPT = (
    "You are the AEGIS native geospatial agent. Use the provided native tools "
    "when supported catalog discovery, capability description, or execution is "
    "actually needed. Call tools only by their exact supplied names.\n\n"
    "Tool-loop rules:\n"
    "1. Inspect existing verified observations and current map state before "
    "calling another tool.\n"
    "2. Call a tool only when required evidence or an execution result is "
    "missing.\n"
    "3. Do not repeat a successful equivalent call.\n"
    "4. Refine a search only when the new query materially addresses an "
    "ambiguity or missing result.\n"
    "5. Retry a failed call only when a materially different valid invocation "
    "can reasonably succeed.\n"
    "6. Never treat failed or rejected tool output as evidence.\n"
    "7. When sources conflict, preserve the conflict instead of silently "
    "selecting one source.\n"
    "8. Stop gathering evidence when the task is satisfied.\n"
    "9. Stop when no useful supported tool remains.\n"
    "10. State that evidence is insufficient when that is the actual result.\n\n"
    "After the useful tool work is complete, provide one concise user-facing "
    "answer and stop."
)

NATIVE_AGENT_CONTEXT_TEMPLATE = (
    "Parsed request:\n{parsed_request}\n\n"
    "Map memory:\n{memory_snapshot}\n\n"
    "Active conversation instructions:\n{active_instructions}\n\n"
    "Current task state:\n{task_snapshot}\n\n"
    "Policy constraints:\n{policy_constraints}"
)

WORKING_STATE_TEMPLATE = "WORKING_STATE (replaceable): {state_json}"

###############################################################################
def build_native_agent_system_prompt() -> str:
    return "\n\n".join(
        [
            NATIVE_AGENT_SYSTEM_PROMPT,
            SUPPORTED_AEGIS_SCOPE,
            GROUNDING_REQUIREMENTS,
            UNCERTAINTY_RULES,
            INTERNAL_INFORMATION_RESTRICTIONS,
        ]
    )

###############################################################################
def build_native_agent_messages(
    *,
    turn_contract: Any,
    memory_snapshot: dict[str, Any],
    constraints: Any,
    active_instructions: list[dict[str, Any]] | None = None,
    task_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    parsed_request = (
        turn_contract.model_dump_json()
        if hasattr(turn_contract, "model_dump_json")
        else json.dumps(turn_contract, default=str)
    )
    context = NATIVE_AGENT_CONTEXT_TEMPLATE.format(
        parsed_request=parsed_request,
        memory_snapshot=memory_snapshot,
        active_instructions=active_instructions or [],
        task_snapshot=task_snapshot or {},
        policy_constraints=constraints,
    )
    return [
        {"role": "system", "content": build_native_agent_system_prompt()},
        {"role": "user", "content": context},
    ]

###############################################################################
def build_working_state_message(
    *,
    parsed_request: Any,
    map_state: dict[str, Any],
    policy_constraints: dict[str, Any],
    completed_tool_results: list[dict[str, Any]],
    evidence_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = (
        cast(dict[str, Any], parsed_request)
        if isinstance(parsed_request, dict)
        else {}
    )
    canonical = policy_constraints.get("canonical_request")
    canonical_payload: dict[str, Any] = (
        cast(dict[str, Any], canonical) if isinstance(canonical, dict) else parsed
    )
    evidence_items: list[AgentEvidenceSummary] = []
    for raw_value in evidence_summaries or []:
        evidence_ref = str(
            raw_value.get("evidence_ref") or raw_value.get("evidence_id") or ""
        )
        if not evidence_ref:
            continue
        status = str(raw_value.get("status") or "available")
        if status not in {"available", "partial", "valid_empty", "failed", "superseded"}:
            status = "available"
        kind = str(raw_value.get("kind") or "diagnostic")
        if kind not in {
            "location",
            "capability_result",
            "provider_layer_descriptor",
            "vector",
            "tabular",
            "raster_descriptor",
            "derived",
            "diagnostic",
        }:
            kind = "diagnostic"
        map_eligibility = str(raw_value.get("map_eligibility") or "unknown")
        if map_eligibility not in {"renderable", "not_renderable", "unknown"}:
            map_eligibility = "unknown"
        evidence_items.append(
            AgentEvidenceSummary(
                evidence_id=evidence_ref,
                kind=kind,  # type: ignore[arg-type]
                media_type=str(raw_value.get("media_type") or "application/json"),
                status=status,  # type: ignore[arg-type]
                summary=(
                    cast(dict[str, Any], raw_value.get("summary"))
                    if isinstance(raw_value.get("summary"), dict)
                    else {}
                ),
                provenance=(
                    cast(dict[str, Any], raw_value.get("provenance"))
                    if isinstance(raw_value.get("provenance"), dict)
                    else {}
                ),
                parent_evidence_ids=[
                    str(item) for item in raw_value.get("parent_evidence_ids", [])
                ]
                if isinstance(raw_value.get("parent_evidence_ids"), list)
                else [],
                byte_size=int(raw_value.get("byte_size") or 0),
                sha256=(
                    str(raw_value["sha256"])
                    if raw_value.get("sha256")
                    else None
                ),
                map_eligibility=map_eligibility,  # type: ignore[arg-type]
            )
        )
    targets: Any = canonical_payload.get("targets", [])
    target_items = cast(list[Any], targets) if isinstance(targets, list) else []
    resolved_locations: list[dict[str, Any]] = []
    for item in target_items:
        if not isinstance(item, dict):
            continue
        item_dict: dict[str, Any] = cast(dict[str, Any], item)
        resolved = item_dict.get("resolved_location")
        if isinstance(resolved, dict):
            resolved_locations.append(cast(dict[str, Any], resolved))
    available_tools: Any = policy_constraints.get("available_tools")
    if not isinstance(available_tools, list):
        available_tools = policy_constraints.get("allowed_tool_names", [])
    raw_task_ledger = policy_constraints.get("task_ledger")
    task_ledger = (
        cast(dict[str, Any], raw_task_ledger)
        if isinstance(raw_task_ledger, dict)
        else {"completed": completed_tool_results}
    )
    typed_state = AgentWorkingState(
        goal=str(parsed.get("user_text") or parsed.get("entity_target") or ""),
        explicit_constraints={
            "map_state": map_state,
            "policy_constraints": policy_constraints,
        },
        canonical_request=canonical_payload,
        resolved_locations=resolved_locations,
        task_ledger=task_ledger,
        completion_requirements=[
            str(item) for item in policy_constraints.get("completion_requirements", [])
        ],
        render_status=(
            "required"
            if policy_constraints.get("presentation_required")
            else "not_required"
        ),
        capability_domains=[
            str(item) for item in policy_constraints.get("capability_domains", [])
        ],
        routing_reasons=[
            str(item) for item in policy_constraints.get("routing_reasons", [])
        ],
        evidence=evidence_items,
        relevant_errors=[item for item in completed_tool_results if item.get("error")],
        active_map_revision=str(map_state.get("revision"))
        if map_state.get("revision") is not None
        else None,
        presentation_state={"map_state": map_state},
        available_tools=[str(item) for item in cast(list[Any], available_tools)],
        tool_exposure_reasons={
            str(key): str(value)
            for key, value in cast(
                dict[str, Any], policy_constraints.get("tool_exposure_reasons") or {}
            ).items()
        }
        if isinstance(policy_constraints.get("tool_exposure_reasons"), dict)
        else {},
        context_budget=(
            policy_constraints.get("context_allocation")
            if isinstance(policy_constraints.get("context_allocation"), dict)
            else None
        ),
    )
    state = {
        "working_state": typed_state.model_dump(mode="json"),
        "evidence_summaries": evidence_summaries or [],
    }
    return {
        "role": "system",
        "content": WORKING_STATE_TEMPLATE.format(
            state_json=json.dumps(state, default=str),
        ),
    }
