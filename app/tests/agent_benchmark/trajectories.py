"""Deterministic agent-loop trajectory replay for the performance gate.

Each scenario drives the real route, registry, executor and map boundaries
with a scripted model and fake providers. The script is split into a route
reply, served only when ``route_request`` is offered, and the ordered
iteration replies, so a run that skips model routing replays unchanged.

Measured per scenario: model calls, tool calls (and failed ones), iterations,
estimated input tokens per model call, recovery counters, unmet completion
obligations, termination reason and wall time. Everything except wall time is
deterministic; wall time is local overhead only.

Scenarios ending in ``_regression`` replay a trajectory observed in the
2026-11-01 browser evaluation that ended wrongly before the reliability work.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.geospatial.providers import ProviderResponse
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

ROUTE_TOOL = "route_request"
DEFAULT_SYNTHESIS = "Here is the requested result."

###############################################################################
def call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)],
    )

###############################################################################
def calls(*items: tuple[str, str, dict[str, Any]]) -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[
            LLMToolCall(id=call_id, name=name, arguments=arguments)
            for call_id, name, arguments in items
        ],
    )

###############################################################################
class ScriptedModel:
    """Serve the route reply on routing calls and iteration replies otherwise."""

    # -------------------------------------------------------------------------
    def __init__(self, route: LLMResult | None, steps: list[LLMResult]) -> None:
        self.route = route
        self.steps = deque(steps)

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        tools = cast(list[LLMToolDefinition], kwargs.get("tools") or [])
        offered = {tool.name for tool in tools}
        if ROUTE_TOOL in offered:
            if self.route is None:
                raise AssertionError("Scenario routed by the model has no route reply.")
            return self.route
        if self.steps:
            return self.steps.popleft()
        # Tools-disabled response synthesis after the scripted work.
        return LLMResult(content=DEFAULT_SYNTHESIS)

###############################################################################
class _ModelFactory:

    # -------------------------------------------------------------------------
    def __init__(self, model: ScriptedModel) -> None:
        self.model = model

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> ScriptedModel:
        del provider
        return self.model

###############################################################################
class _Resolver:

    # -------------------------------------------------------------------------
    def __init__(
        self, places: dict[str, ResolvedLocation | ClarificationRequest]
    ) -> None:
        self.places = {key.casefold(): value for key, value in places.items()}

    # -------------------------------------------------------------------------
    async def resolve_location_signals(
        self, signals: Any, memory_snapshot: Any
    ) -> ResolvedLocation | ClarificationRequest:
        del memory_snapshot
        signal = signals[0]
        if signal.latitude is not None and signal.longitude is not None:
            return ResolvedLocation(
                label=f"{signal.latitude}, {signal.longitude}",
                latitude=signal.latitude,
                longitude=signal.longitude,
                source="scripted-benchmark",
                confidence=1.0,
                location_type="coordinates",
            )
        key = str(signal.raw_value).casefold()
        if key in self.places:
            return self.places[key]
        raise AssertionError(f"Unscripted location: {signal.raw_value!r}")

###############################################################################
class _Providers:
    """Return a two-point feature payload for any provider request."""

    # -------------------------------------------------------------------------
    async def fetch(self, provider: str, request: Any) -> ProviderResponse:
        latitude = float(request.params.get("latitude", 48.0))
        longitude = float(request.params.get("longitude", 8.0))
        metric = "precipitation_sum_mm"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider,
            payload={
                "features": [
                    {"latitude": latitude, "longitude": longitude, metric: 9.0},
                    {"latitude": latitude + 1, "longitude": longitude + 1, metric: 100.0},
                ],
                "value_kind": "model_estimate",
            },
            result_type="features",
            result_status="ok",
            units={metric: "mm"},
            coverage={
                "bbox": list(request.bbox) if request.bbox else [longitude, latitude, longitude + 1, latitude + 1],
                "type": "grid_sample",
                "point_count": 2,
                "spatial_scope_satisfied": True,
                "temporal_scope_satisfied": True,
            },
        )

###############################################################################
class _Evidence:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.records: dict[str, tuple[AgentEvidenceSummary, bytes]] = {}

    # -------------------------------------------------------------------------
    def create(self, **kwargs: Any) -> AgentEvidenceSummary:
        ref = f"evidence-{len(self.records) + 1}"
        raw = json.dumps(kwargs["payload"]).encode()
        summary = AgentEvidenceSummary(
            evidence_id=ref,
            kind=kwargs["kind"],
            media_type=kwargs["media_type"],
            status=kwargs["status"],
            summary=kwargs["summary"],
            provenance=kwargs["provenance"],
            byte_size=len(raw),
            map_eligibility=kwargs["summary"].get("map_eligibility", "renderable"),
        )
        self.records[ref] = summary, raw
        return summary

    # -------------------------------------------------------------------------
    def get_payload(self, ref: str, **kwargs: Any) -> tuple[AgentEvidenceSummary, bytes] | None:
        del kwargs
        return self.records.get(ref)

    # -------------------------------------------------------------------------
    def get_summary(self, ref: str, **kwargs: Any) -> AgentEvidenceSummary | None:
        del kwargs
        record = self.records.get(ref)
        return record[0] if record else None

###############################################################################
@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_message: str
    route: dict[str, Any]
    steps: Callable[[], list[LLMResult]]
    places: dict[str, ResolvedLocation | ClarificationRequest] = field(
        default_factory=lambda: dict[str, ResolvedLocation | ClarificationRequest]()
    )
    recent_messages: list[dict[str, object]] = field(
        default_factory=lambda: list[dict[str, object]]()
    )
    # Evidence an earlier turn of the conversation already stored.
    prior_evidence: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )

###############################################################################
def _location(label: str, latitude: float, longitude: float, kind: str = "city") -> ResolvedLocation:
    return ResolvedLocation(
        label=label,
        latitude=latitude,
        longitude=longitude,
        bbox=[longitude - 0.1, latitude - 0.1, longitude + 0.1, latitude + 0.1],
        source="scripted-benchmark",
        confidence=1.0,
        location_type=kind,
    )

###############################################################################
def _show_place_map(evidence_ref: str | None = None) -> dict[str, Any]:
    actions: list[dict[str, Any]] = [{"action": "set_basemap", "capability_id": "osm_default"}]
    if evidence_ref is not None:
        actions.append(
            {
                "action": "add_evidence_layer",
                "capability_id": "openmeteo_weather_forecast",
                "evidence_ref": evidence_ref,
            }
        )
    return {"expected_collection_revision": 0, "actions": actions}

_PLACE_ROUTE = {
    "primary_domain": "place_search",
    "secondary_domains": ["map_rendering"],
    "task_mode": "execute",
    "presentation": "map",
    "location_mode": "target",
    "capability_queries": ["place search", "map viewport"],
    "operation": "show_location_on_map",
}
_WEATHER = "openmeteo_weather_forecast"
_RAIN_RANK_ROUTE = {
    "primary_domain": "data_retrieval",
    "secondary_domains": ["map_rendering"],
    "task_mode": "execute",
    "presentation": "map",
    "location_mode": "target",
    "target_refs": ["Europe"],
    "capability_queries": ["weather"],
    "explicit_capability_ids": [_WEATHER],
    "operation": "show",
    "analysis": {"kind": "rank", "metric": "precipitation_sum_mm", "top_k": 1},
    "temporal_scope": {"mode": "current", "granularity": "day"},
}


def _inspect(call_id: str, view: str, limit: int = 20) -> LLMResult:
    return call(call_id, "inspect_evidence", {"evidence_ref": "evidence-1", "view": view, "limit": limit})


def _nested_weather(call_id: str, place: str) -> tuple[str, str, dict[str, Any]]:
    # The weaker-model shape: location_ref nested inside provider arguments.
    return (call_id, "execute_geospatial_capability", {"capability_id": _WEATHER, "arguments": {"location_ref": place}})

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="show_colosseum",
        user_message="Show the Colosseum",
        route=_PLACE_ROUTE,
        places={"Colosseum": _location("Colosseum, Rome, Italy", 41.8902, 12.4922, "landmark")},
        steps=lambda: [
            call("resolve-1", "resolve_geospatial_location", {"query": "Colosseum", "target_id": "Colosseum"}),
            call("map-1", "apply_map_plan", _show_place_map()),
        ],
    ),
    Scenario(
        scenario_id="show_coordinates",
        user_message="Show 41.89, 12.49 on the map",
        route=_PLACE_ROUTE,
        steps=lambda: [
            call("resolve-1", "resolve_geospatial_location", {"query": "41.89, 12.49", "target_id": "point", "expected_location_type": "coordinates"}),
            call("map-1", "apply_map_plan", _show_place_map()),
        ],
    ),
    Scenario(
        scenario_id="springfield_clarification",
        user_message="Show Springfield",
        route=_PLACE_ROUTE,
        places={
            "Springfield": ClarificationRequest(
                question="Which Springfield?", reason="Ambiguous place", missing_fields=["location"]
            )
        },
        steps=lambda: [
            call("resolve-1", "resolve_geospatial_location", {"query": "Springfield", "target_id": "Springfield"}),
        ],
    ),
    Scenario(
        scenario_id="paris_berlin_weather",
        user_message="Compare today's weather in Paris and Berlin",
        route={
            "primary_domain": "data_retrieval",
            "task_mode": "execute",
            "presentation": "text",
            "location_mode": "target",
            "target_refs": ["Paris", "Berlin"],
            "capability_queries": ["weather"],
            "explicit_capability_ids": [_WEATHER],
            "operation": "compare",
        },
        places={"Paris": _location("Paris, France", 48.8566, 2.3522), "Berlin": _location("Berlin, Germany", 52.52, 13.405)},
        steps=lambda: [
            calls(
                ("resolve-paris", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
                ("resolve-berlin", "resolve_geospatial_location", {"query": "Berlin", "target_id": "Berlin"}),
            ),
            calls(
                ("weather-paris", "execute_geospatial_capability", {"capability_id": _WEATHER, "location_ref": "Paris"}),
                ("weather-berlin", "execute_geospatial_capability", {"capability_id": _WEATHER, "location_ref": "Berlin"}),
            ),
            LLMResult(content="Berlin is wetter than Paris today."),
        ],
    ),
    Scenario(
        scenario_id="europe_rainfall_rank",
        user_message="Show where in Europe it rained most today",
        route={
            "primary_domain": "data_retrieval",
            "secondary_domains": ["map_rendering"],
            "task_mode": "execute",
            "presentation": "map",
            "location_mode": "target",
            "target_refs": ["Europe"],
            "capability_queries": ["weather"],
            "explicit_capability_ids": [_WEATHER],
            "operation": "show",
            "analysis": {"kind": "rank", "metric": "precipitation_sum_mm", "top_k": 1},
            "temporal_scope": {"mode": "current", "granularity": "day"},
        },
        steps=lambda: [
            call("execute-1", "execute_geospatial_capability", {"capability_id": _WEATHER}),
            call(
                "transform-1",
                "transform_evidence",
                {
                    "evidence_refs": ["evidence-1"],
                    "operations": [
                        {"op": "sort", "field": "precipitation_sum_mm", "descending": True},
                        {"op": "limit", "value": 1},
                    ],
                },
            ),
            call(
                "map-1",
                "apply_map_plan",
                {
                    "expected_collection_revision": 0,
                    "actions": [
                        {"action": "set_basemap", "capability_id": "osm_default"},
                        {
                            "action": "add_evidence_layer",
                            "capability_id": _WEATHER,
                            "evidence_ref": "evidence-2",
                            "value_encoding": {"mode": "graduated", "field": "precipitation_sum_mm"},
                        },
                        {"action": "set_viewport", "strategy": "fit_evidence", "evidence_refs": ["evidence-2"]},
                    ],
                },
            ),
        ],
    ),
    Scenario(
        scenario_id="follow_up_weather",
        user_message="And what is the weather there now?",
        route={
            "primary_domain": "data_retrieval",
            "task_mode": "execute",
            "presentation": "text",
            "location_mode": "target",
            "target_refs": ["Rome"],
            "capability_queries": ["weather"],
            "explicit_capability_ids": [_WEATHER],
            "operation": "show",
        },
        places={"Rome": _location("Rome, Italy", 41.9028, 12.4964)},
        recent_messages=[
            {"role": "user", "content": "Show Rome"},
            {"role": "assistant", "content": "Rome, Italy is now shown on the map."},
        ],
        steps=lambda: [
            call("resolve-1", "resolve_geospatial_location", {"query": "Rome", "target_id": "Rome"}),
            call("weather-1", "execute_geospatial_capability", {"capability_id": _WEATHER}),
            LLMResult(content="It is currently mild in Rome."),
        ],
    ),
    # A3: "airports" was rewritten to a location-only map and a viewport fit
    # was reported as done. Now the data obligation stays open and the run
    # ends without claiming airports it never retrieved.
    Scenario(
        scenario_id="entity_request_regression",
        user_message="Locate the major airports in Switzerland and display them on the map.",
        route={**_PLACE_ROUTE, "presentation": "both", "target_refs": ["Switzerland"]},
        places={"Switzerland": _location("Switzerland", 46.8, 8.2, "country")},
        steps=lambda: [
            call("resolve-1", "resolve_geospatial_location", {"query": "Switzerland", "target_id": "Switzerland"}),
            LLMResult(content="The major Swiss airports are shown on the map."),
        ],
    ),
    # BF-C4/BF-B4: inspection after inspection of one ref with nothing new.
    Scenario(
        scenario_id="inspect_loop_regression",
        user_message="Show where in Europe it rained most today",
        route=_RAIN_RANK_ROUTE,
        steps=lambda: [
            call("execute-1", "execute_geospatial_capability", {"capability_id": _WEATHER}),
            _inspect("inspect-1", "metadata"),
            _inspect("inspect-2", "schema"),
            _inspect("inspect-3", "sample"),
            _inspect("inspect-4", "statistics"),
            _inspect("inspect-5", "page"),
            _inspect("inspect-6", "sample", 5),
            _inspect("inspect-7", "page", 5),
            _inspect("inspect-8", "statistics", 5),
        ],
    ),
    # BF-B2: three parallel executions with location_ref nested in arguments
    # spent the whole correction budget in one batch.
    Scenario(
        scenario_id="nested_arguments_regression",
        user_message="Compare the weather in Lugano, Como and Milan",
        route={
            "primary_domain": "data_retrieval",
            "task_mode": "execute",
            "presentation": "text",
            "location_mode": "target",
            "target_refs": ["Lugano", "Como", "Milan"],
            "capability_queries": ["weather"],
            "explicit_capability_ids": [_WEATHER],
            "operation": "compare",
        },
        places={
            "Lugano": _location("Lugano, Switzerland", 46.0037, 8.9511),
            "Como": _location("Como, Italy", 45.8081, 9.0852),
            "Milan": _location("Milan, Italy", 45.4642, 9.19),
        },
        steps=lambda: [
            calls(
                ("resolve-lugano", "resolve_geospatial_location", {"query": "Lugano", "target_id": "Lugano"}),
                ("resolve-como", "resolve_geospatial_location", {"query": "Como", "target_id": "Como"}),
                ("resolve-milan", "resolve_geospatial_location", {"query": "Milan", "target_id": "Milan"}),
            ),
            calls(
                _nested_weather("weather-lugano", "Lugano"),
                _nested_weather("weather-como", "Como"),
                _nested_weather("weather-milan", "Milan"),
            ),
            LLMResult(content="Milan is the wettest of the three."),
        ],
    ),
    # E3/F2: a follow-up re-ranks evidence an earlier turn retrieved; it used
    # to fail with data, time and area obligations pending.
    Scenario(
        scenario_id="follow_up_prior_evidence_regression",
        user_message="Which of those places had the most rain?",
        route={**_RAIN_RANK_ROUTE, "presentation": "text", "secondary_domains": []},
        recent_messages=[
            {"role": "user", "content": "Show where in Europe it rained most today"},
            {"role": "assistant", "content": "The map shows today's sampled rainfall across Europe."},
        ],
        prior_evidence=[
            {
                "features": [
                    {"latitude": 45.0, "longitude": 22.0, "name": "Isverna", "precipitation_sum_mm": 39.2},
                    {"latitude": 47.0, "longitude": 11.0, "name": "Innsbruck", "precipitation_sum_mm": 12.0},
                ],
                "coverage": {"spatial_scope_satisfied": True, "temporal_scope_satisfied": True},
                "query": {"location_ref": "Europe"},
            }
        ],
        steps=lambda: [
            call(
                "transform-1",
                "transform_evidence",
                {
                    "evidence_refs": ["evidence-1"],
                    "operations": [
                        {"op": "sort", "field": "precipitation_sum_mm", "descending": True},
                        {"op": "limit", "value": 1},
                    ],
                },
            ),
            LLMResult(content="Isverna had the most rain, about 39 mm."),
        ],
    ),
)

###############################################################################
def build_loop(
    model: ScriptedModel, scenario: Scenario, evidence: _Evidence | None = None
) -> AgentLoop:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(
        registry,
        capability_registry=capabilities,
        runtime_registry=runtime,
        provider_registry=_Providers(),  # type: ignore[arg-type]
        evidence_repository=evidence or _Evidence(),  # type: ignore[arg-type]
        geospatial_api_service=object(),
        location_resolver=_Resolver(scenario.places),  # type: ignore[arg-type]
    )
    return AgentLoop(
        provider_factory=_ModelFactory(model),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
        tool_registry=registry,
        tool_executor=ToolExecutor(
            tool_registry=registry,
            policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime),
        ),
    )

###############################################################################
async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    model = ScriptedModel(call("route-1", ROUTE_TOOL, scenario.route), scenario.steps())
    evidence = _Evidence()
    prior_refs = [
        evidence.create(
            kind="vector",
            media_type="application/json",
            status="available",
            payload={"features": item["features"]},
            summary={"coverage": item["coverage"], "query": item["query"], "record_count": len(item["features"])},
            provenance={"capability_id": _WEATHER, "provider_id": "openmeteo"},
        ).evidence_id
        for item in scenario.prior_evidence
    ]
    loop = build_loop(model, scenario, evidence)
    state = AgentRunState(
        request_id=scenario.scenario_id,
        conversation_id=scenario.scenario_id,
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message=scenario.user_message,
        context_hydrated=True,
        recent_messages=list(scenario.recent_messages),
        evidence_refs=list(prior_refs),
    )
    started = time.perf_counter()
    outcome = await loop.run(
        AgentLoopRequest(
            provider="scripted",
            model="scripted",
            state=state,
            budget=AgentExecutionBudget(total_seconds=30, hard_max_seconds=30),
        )
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    per_call = [
        int(cast(int | None, item.get("estimated_input_tokens")) or 0)
        for item in state.model_trace
        if item.get("status") == "observed"
    ]
    return {
        "scenario_id": scenario.scenario_id,
        "termination_reason": outcome.stopped_reason,
        "model_calls": state.model_calls,
        "tool_calls": len(outcome.tool_results),
        "failed_tool_calls": sum(1 for item in outcome.tool_results if item.status == "failed"),
        "iterations": state.current_iteration,
        "no_progress_corrections": state.no_progress_corrections,
        "stuck_notices": state.stuck_notices,
        "unmet_requirements": AgentLoop._pending_native_requirements(state),  # pyright: ignore[reportPrivateUsage]
        "estimated_input_tokens": per_call,
        "total_estimated_input_tokens": sum(per_call),
        "wall_ms": round(elapsed_ms, 2),
    }

###############################################################################
async def run_all() -> list[dict[str, Any]]:
    return [await run_scenario(scenario) for scenario in SCENARIOS]


__all__ = ["SCENARIOS", "Scenario", "ScriptedModel", "run_all", "run_scenario"]
