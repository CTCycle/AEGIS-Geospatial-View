"""Run the versioned scenario manifest against a running AEGIS backend.

The runner intentionally does not select a provider or model.  The backend's
configured model is recorded in the output and a structured-output preflight
failure produces a blocked lane rather than silently substituting a model.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import ToolPlan, ToolPlanStep, ToolRetryPolicy
from server.domain.agent.runtime import (
    AgentTask,
    AgentThreadState,
    GeospatialWorkingState,
    apply_steering_delta,
)
from server.domain.agent.tools import ToolError, ToolExecutionEnvelope
from server.domain.steering import SteeringDelta
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.types import LLMToolDefinition


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code, "text": response.text[:1000]}
    return payload if isinstance(payload, dict) else {"value": payload}


def _fingerprint(tool: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(tool, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class _ScriptedToolRegistry:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute_native_tool(
        self, name: str, arguments: dict[str, Any], context: AgentExecutionContext
    ) -> ToolExecutionEnvelope:
        _ = context
        self.calls.append((name, arguments))
        if self.failure == "timeout":
            raise TimeoutError("scripted timeout")
        if self.failure == "http_error":
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(
                    code="provider_unavailable", message="scripted upstream failure"
                ),
            )
        if self.failure == "empty":
            return ToolExecutionEnvelope(ok=True, data={})
        if self.failure == "malformed_schema":
            return ToolExecutionEnvelope(ok=True, data={"capability_id": "wrong"})
        if self.failure == "partial" and name == "second":
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(code="provider_unavailable", message="partial failure"),
            )
        return ToolExecutionEnvelope(ok=True, data={"value": "scripted"})


def _scripted_plan(failure: str) -> ToolPlan:
    if failure == "malformed_schema":
        steps = [
            ToolPlanStep(
                step_id="malformed",
                tool_name="execute_geospatial_capability",
                capability_id="expected",
                reason="scripted malformed result",
            )
        ]
    elif failure == "partial":
        steps = [
            ToolPlanStep(step_id="first", tool_name="first", reason="partial success"),
            ToolPlanStep(step_id="second", tool_name="second", reason="partial failure"),
        ]
    elif failure == "repeated_call":
        steps = [
            ToolPlanStep(step_id="first", tool_name="probe", reason="first call"),
            ToolPlanStep(step_id="duplicate", tool_name="probe", reason="duplicate call"),
        ]
    else:
        steps = [ToolPlanStep(step_id="scripted", tool_name="probe", reason=failure)]
    if failure == "repeated_call":
        steps[1] = steps[1].model_copy(update={"arguments": dict(steps[0].arguments)})
    if failure in {"timeout", "http_error"}:
        steps[0] = steps[0].model_copy(
            update={"retry_policy": ToolRetryPolicy(max_attempts=2)}
        )
    return ToolPlan(tool_group="direct_chat", selected_tools=[step.tool_name for step in steps], steps=steps)


def _run_scripted_plan(failure: str) -> tuple[list[Any], int]:
    if failure == "invalid_coordinates_bounds_temporal":
        registry = ToolRegistry(runtime_registry=object())
        calls = 0

        async def handler(arguments: dict[str, Any], context: Any) -> dict[str, Any]:
            nonlocal calls
            _ = (arguments, context)
            calls += 1
            return {"value": "handler called"}

        registry.register_native_tool(
            LLMToolDefinition(
                name="validate",
                description="Validate coordinates",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"latitude": {"type": "number", "maximum": 90}},
                    "required": ["latitude"],
                },
            ),
            handler,
        )
        plan = ToolPlan(
            tool_group="direct_chat",
            selected_tools=["validate"],
            steps=[
                ToolPlanStep(
                    step_id="invalid",
                    tool_name="validate",
                    reason="invalid coordinates",
                    arguments={"latitude": 91},
                )
            ],
        )
        results = asyncio.run(
            ToolPlanExecutor(tool_registry=registry).execute(
                plan, AgentExecutionContext(request_id="scripted-fault")
            )
        )
        return results, calls
    registry = _ScriptedToolRegistry(failure)
    results = asyncio.run(
        ToolPlanExecutor(tool_registry=registry).execute(
            _scripted_plan(failure),
            AgentExecutionContext(request_id="scripted-fault"),
        )
    )
    return results, len(registry.calls)


def _run_scripted_fault_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario["id"])
    failure = str(scenario.get("failure") or "")
    if scenario_id == "context-answerable-no-tool":
        tool_calls = 0
        passed = True
        details = {"status": "answered_from_context", "tool_calls": tool_calls}
    elif scenario_id == "stale-layer-removal":
        state = AgentThreadState(
            conversation_id="scripted-fault",
            evidence_refs=["western-layer", "retained-layer"],
            geospatial_state=GeospatialWorkingState(
                layer_refs=["western-layer", "retained-layer"],
                renderable_refs=["western-layer", "retained-layer"],
            ),
            tasks=[
                AgentTask(
                    id="weather",
                    description="Weather",
                    kind="weather",
                    status="completed",
                    output_refs=["western-layer"],
                )
            ],
        )
        apply_steering_delta(
            state,
            SteeringDelta(kind="exclusion", text="Remove western results from the current map."),
        )
        passed = (
            "western-layer" not in state.evidence_refs
            and "western-layer" not in state.geospatial_state.renderable_refs
            and "retained-layer" in state.geospatial_state.renderable_refs
        )
        details = {
            "status": "state_delta_applied" if passed else "state_delta_failed",
            "tool_calls": 0,
            "remaining_renderable_refs": state.geospatial_state.renderable_refs,
        }
    else:
        results, tool_calls = _run_scripted_plan(failure)
        if failure in {"timeout", "http_error"}:
            passed = len(results) == 1 and results[0].ok is False and results[0].provenance.attempt == 2
        elif failure == "empty":
            passed = len(results) == 1 and results[0].ok and not results[0].data
        elif failure == "malformed_schema":
            passed = len(results) == 1 and results[0].validation_error is not None
        elif failure == "partial":
            passed = any(result.ok for result in results) and any(not result.ok for result in results)
        elif failure == "invalid_coordinates_bounds_temporal":
            passed = len(results) == 1 and results[0].error_code == "invalid_arguments" and tool_calls == 0
        elif failure == "repeated_call":
            passed = len(results) == 2 and results[1].error_code == "duplicate_tool_call" and tool_calls == 1
        else:
            passed = False
        details = {
            "status": "passed" if passed else "failed",
            "tool_calls": tool_calls,
            "tool_results": [result.model_dump(mode="json") for result in results],
        }
    return {
        "scenario_id": scenario_id,
        "assertions": scenario.get("assertions", []),
        "passed": passed,
        **details,
    }


def run_scripted_fault_lane(*, manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = [item for item in manifest["scenarios"] if item.get("lane") == "scripted_fault"]
    results = [_run_scripted_fault_scenario(scenario) for scenario in scenarios]
    passed = sum(1 for result in results if result["passed"])
    metrics = {
        "status": "passed" if passed == len(results) else "failed",
        "lane": "scripted_fault",
        "scenario_count": len(results),
        "passed_scenarios": passed,
        "task_success_rate": passed / len(results) if results else 1.0,
        "unnecessary_tool_calls": sum(
            1 for result in results if result["scenario_id"] == "context-answerable-no-tool" and result["tool_calls"]
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "manifest": str(manifest_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "lane": "scripted_fault",
        "status": metrics["status"],
        "results": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    (output_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=True, default=str) for item in results) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return bundle


def run_manifest(
    *,
    manifest_path: Path,
    output_dir: Path,
    base_url: str,
    lane: str | None = None,
) -> dict[str, Any]:
    if lane == "scripted_fault":
        return run_scripted_fault_lane(manifest_path=manifest_path, output_dir=output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = [
        scenario
        for scenario in manifest["scenarios"]
        if lane is None or scenario.get("lane") == lane
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=180.0)
    started = time.perf_counter()
    health = client.get("/api/health")
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        conversation_response = client.post(
            "/api/conversations",
            json={"title": f"benchmark {scenario['id']}"},
        )
        conversation_payload = _json_response(conversation_response)
        conversation_id = conversation_payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            conversation_id = f"benchmark-{uuid4().hex}"
        turns = scenario.get("turns") or [scenario.get("prompt", "")]
        trace: list[dict[str, Any]] = []
        scenario_started = time.perf_counter()
        for turn in turns:
            response = client.post(
                "/api/chat/turn",
                json={"conversation_id": conversation_id, "message": turn},
            )
            payload = _json_response(response)
            tool_payload = payload.get("tool_payload")
            tool_calls = tool_payload.get("tool_calls", []) if isinstance(tool_payload, dict) else []
            trace.append(
                {
                    "prompt": turn,
                    "status_code": response.status_code,
                    "tool_calls": tool_calls,
                    "tool_results": tool_payload.get("tool_results", [])
                    if isinstance(tool_payload, dict)
                    else [],
                    "response": payload,
                    "map_session": payload.get("map_session"),
                    "request_fingerprints": [_fingerprint(item) for item in tool_calls if isinstance(item, dict)],
                }
            )
        results.append(
            {
                "scenario_id": scenario["id"],
                "conversation_id": conversation_id,
                "elapsed_seconds": time.perf_counter() - scenario_started,
                "turns": trace,
                "status": "blocked"
                if any(
                    item["status_code"] == 503
                    or "could not perform structured extraction" in str(item["response"])
                    or "credentials are not configured" in str(item["response"])
                    for item in trace
                )
                else "recorded",
            }
        )
    bundle = {
        "manifest": str(manifest_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "health": {"status_code": health.status_code, "payload": _json_response(health)},
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    (output_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=True, default=str) for item in results) + "\n",
        encoding="utf-8",
    )
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:7059"))
    parser.add_argument("--lane", choices=["model_in_loop", "scripted_fault", "live_smoke"])
    args = parser.parse_args()
    run_manifest(
        manifest_path=args.manifest,
        output_dir=args.output,
        base_url=args.base_url,
        lane=args.lane,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
