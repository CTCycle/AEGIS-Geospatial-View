from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from pydantic import ValidationError

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentPhase,
    AgentRunState,
    AgentTemporalScope,
    CapabilityRoute,
    TargetRequirement,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.llm.types import LLMResult, LLMToolCall
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.geospatial.providers import ProviderResponse
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.completion import CompletionEvaluator
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


TODAY = AgentTemporalScope(
    mode="current",
    start_time_iso="2026-11-03T00:00:00+00:00",
    end_time_iso="2026-11-03T23:59:59+00:00",
    granularity="day",
)
TOMORROW = AgentTemporalScope(
    mode="forecast",
    start_time_iso="2026-11-04T00:00:00+00:00",
    end_time_iso="2026-11-04T23:59:59+00:00",
    granularity="day",
)


###############################################################################
class _ScriptedProvider:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult]) -> None:
        self._results = deque(results)

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> "_ScriptedProvider":
        del provider
        return self

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        del request, kwargs
        return self._results.popleft()


###############################################################################
def _call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMResult:
    return LLMResult(content="", tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)])


###############################################################################
class _Evidence:

    # -------------------------------------------------------------------------
    def create(self, **kwargs: Any) -> Any:
        from server.domain.agent.evidence import AgentEvidenceSummary

        return AgentEvidenceSummary(
            evidence_id="evidence-1", kind=kwargs["kind"], media_type=kwargs["media_type"],
            status=kwargs["status"], summary=kwargs["summary"], provenance=kwargs["provenance"],
            byte_size=1, map_eligibility="renderable",
        )


###############################################################################
def make_loop(model: _ScriptedProvider, providers: Any, resolver: Any) -> AgentLoop:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(registry, capability_registry=capabilities, runtime_registry=runtime,
                         provider_registry=providers, evidence_repository=_Evidence(),  # type: ignore[arg-type]
                         geospatial_api_service=object(), location_resolver=resolver)  # type: ignore[arg-type]
    return AgentLoop(provider_factory=model,  # type: ignore[arg-type]
                     capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
                     tool_registry=registry, tool_executor=ToolExecutor(tool_registry=registry,
                     policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime)))


###############################################################################
def _compound_route(**updates: Any) -> CapabilityRoute:
    fields: dict[str, Any] = {
        "primary_domain": CapabilityDomain.DATA_RETRIEVAL,
        "task_mode": "execute",
        "presentation": "text",
        "location_mode": "target",
        "capability_queries": ["weather"],
        "target_refs": ["Rome", "Milan"],
        "temporal_scope": TOMORROW,
        "target_requirements": [
            TargetRequirement(target_ref="Rome", temporal_scope=TODAY),
            TargetRequirement(target_ref="Milan", temporal_scope=TOMORROW),
        ],
    }
    return CapabilityRoute(**{**fields, **updates})


###############################################################################
def _state(route: CapabilityRoute) -> AgentRunState:
    state = AgentRunState(
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        request_id="per-target",
        conversation_id="per-target",
        user_message="Compare rainfall today in Rome with tomorrow in Milan",
        location_refs={
            "rome": ResolvedLocation(label="Rome, Italy", latitude=41.9, longitude=12.5),
            "milan": ResolvedLocation(label="Milan, Italy", latitude=45.46, longitude=9.19),
        },
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)
    return state


###############################################################################
def _evidence(location_ref: str, observed_at: str) -> ToolResult:
    return ToolResult(
        call_id=f"execute-{location_ref}",
        tool_name="execute_geospatial_capability",
        status="success",
        summary="ok",
        data={"kind": "weather_forecast", "query": {"location_ref": location_ref}},
        evidence_refs=[f"evidence-{location_ref}"],
        metadata=ToolExecutionMetadata(
            duration_ms=0,
            capability_id="openmeteo_weather_forecast",
            result_type="weather_forecast",
            observation_time=observed_at,
            coverage={"data_valid": True},
        ),
    )


###############################################################################
def test_route_rejects_requirement_for_unknown_target() -> None:
    with pytest.raises(ValidationError, match="not in target_refs"):
        _compound_route(
            target_requirements=[TargetRequirement(target_ref="Turin", temporal_scope=TODAY)]
        )


###############################################################################
def test_router_normalizes_per_target_scopes_and_prunes_removed_targets() -> None:
    capabilities = CapabilityRegistry()
    router = CapabilityRouter(
        capability_registry=capabilities,
        runtime_registry=RuntimeRegistry(
            catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None
        ),
    )
    recent = AgentTemporalScope(mode="historical", granularity="recent")
    route = _compound_route(
        target_requirements=[
            TargetRequirement(target_ref="Rome", temporal_scope=recent),
            TargetRequirement(target_ref="Milan", temporal_scope=TOMORROW),
        ]
    )
    decision = router.validate_route(
        route,
        user_message="Compare rainfall today in Rome with tomorrow in Milan",
        active_state=AgentRunState(
            phase=AgentPhase.ROUTE_REQUEST, request_id="r", conversation_id="r", user_message="x"
        ),
    )
    by_target = {item.target_ref: item for item in decision.route.target_requirements}
    assert by_target["Rome"].temporal_scope is not None
    assert by_target["Rome"].temporal_scope.mode == "current"
    assert by_target["Milan"].temporal_scope == TOMORROW


###############################################################################
def test_goal_carries_per_target_windows_with_route_fallback() -> None:
    route = _compound_route(
        target_requirements=[TargetRequirement(target_ref="Rome", temporal_scope=TODAY)]
    )
    state = _state(route)

    assert state.goal is not None and state.completion_contract is not None
    assert state.goal.temporal_scope["start_time_iso"] == TOMORROW.start_time_iso
    assert [item.target_ref for item in state.goal.target_requirements] == ["Rome"]
    assert state.goal.target_requirements[0].temporal_scope == TODAY
    assert state.completion_contract.temporal_scope_required


###############################################################################
def test_each_target_is_judged_against_its_own_window() -> None:
    state = _state(_compound_route())
    rome_today = _evidence("rome", "2026-11-03T12:00:00+00:00")
    milan_tomorrow = _evidence("milan", "2026-11-04T12:00:00+00:00")
    milan_today = _evidence("milan", "2026-11-03T12:00:00+00:00")

    state.tool_results = [rome_today, milan_tomorrow]
    assert CompletionEvaluator.data_checks(state)["temporal_scope_applied"] is True

    state.tool_results = [rome_today, milan_today]
    assert CompletionEvaluator.assess_evidence(state, rome_today).temporal_scope_satisfied is True
    assert CompletionEvaluator.assess_evidence(state, milan_today).temporal_scope_satisfied is False
    assert CompletionEvaluator.data_checks(state)["temporal_scope_applied"] is False


###############################################################################
class _WeatherProvider:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    async def fetch(self, provider: str, request: Any) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider,
            payload={"features": [{"latitude": request.params["latitude"], "longitude": request.params["longitude"], "precipitation_sum_mm": 3.0}]},
            result_type="features",
            units={"precipitation_sum_mm": "mm"},
            coverage={"bbox": [0, 0, 0, 0], "spatial_scope_satisfied": True},
        )


###############################################################################
@pytest.mark.asyncio
async def test_compound_request_queries_each_target_with_its_own_window() -> None:
    cities = {
        "Rome": ResolvedLocation(label="Rome, Italy", latitude=41.9, longitude=12.5),
        "Milan": ResolvedLocation(label="Milan, Italy", latitude=45.46, longitude=9.19),
    }

    ###############################################################################
    class Resolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals: Any, memory_snapshot: Any) -> ResolvedLocation:
            del memory_snapshot
            text = " ".join(str(getattr(signal, "text", signal)) for signal in signals)
            return next(location for name, location in cities.items() if name in text)

    route = {
        "primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "text",
        "location_mode": "target", "operation": "inspect", "capability_queries": ["weather"],
        "explicit_capability_ids": ["openmeteo_weather_forecast"], "target_refs": ["Rome", "Milan"],
        "temporal_scope": TOMORROW.model_dump(mode="json"),
        "target_requirements": [
            {"target_ref": "Rome", "temporal_scope": TODAY.model_dump(mode="json")},
            {"target_ref": "Milan", "temporal_scope": TOMORROW.model_dump(mode="json")},
        ],
    }
    model = _ScriptedProvider([
        _call("route", "route_request", route),
        _call("rome", "resolve_geospatial_location", {"query": "Rome", "target_id": "Rome"}),
        _call("milan", "resolve_geospatial_location", {"query": "Milan", "target_id": "Milan"}),
        _call("x-rome", "execute_geospatial_capability", {"capability_id": "openmeteo_weather_forecast", "location_ref": "Rome"}),
        _call("x-milan", "execute_geospatial_capability", {"capability_id": "openmeteo_weather_forecast", "location_ref": "Milan"}),
    ])
    providers = _WeatherProvider()
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="compound", conversation_id="compound",
        user_message="Compare rainfall today in Rome with tomorrow in Milan",
    )
    await make_loop(model, providers, Resolver()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state,
        budget=AgentExecutionBudget(total_seconds=10), max_no_progress_corrections=0,
    ))

    assert state.route is not None and len(state.route.target_requirements) == 2
    windows = {
        round(request.params["latitude"]): (request.time.date().isoformat(), request.params.get("end_time_iso"))
        for request in providers.requests
    }
    assert windows == {
        42: ("2026-11-03", TODAY.end_time_iso),
        45: ("2026-11-04", TOMORROW.end_time_iso),
    }
