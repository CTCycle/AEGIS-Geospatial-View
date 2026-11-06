from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from pydantic import ValidationError

from server.contracts.geospatial import MapSession, OverlayCollectionState, OverlayInstance, ViewportPolicy
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.map_plan import PLACE_MARKERS_INSTANCE_ID
from server.domain.realtime import RealtimeRenderAckPayload
from server.domain.agent.capability_route import (
    AgentPhase,
    AgentRunState,
    AgentTemporalScope,
    CapabilityRoute,
    TargetRequirement,
    CompletionContract,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.llm.types import LLMResult, LLMToolCall
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.geospatial.providers import ProviderResponse
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.domain.agent.presentation_contract import ContractTarget, PresentationContract
from server.services.agent.completion import CompletionEvaluator, build_completion_summary, presentation_contract
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent_runs.render_completion import RenderCompletionService
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


###############################################################################
def _map(*instances: OverlayInstance) -> MapSession:
    location = ResolvedLocation(label="Rome, Italy", latitude=41.9, longitude=12.5)
    return MapSession(
        session_id="map-1", resolved_location=location, basemap_id="osm_standard",
        viewport=ViewportPolicy(center_latitude=41.9, center_longitude=12.5),
        overlay_collection=OverlayCollectionState(revision=1, instances=list(instances)),
    )


###############################################################################
def _markers(*annotations: str | None) -> OverlayInstance:
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
         "properties": {"name": place, "location_ref": place, **({"annotation": text} if text else {})}}
        for place, text in zip(("Rome", "Milan"), annotations)
    ]
    return OverlayInstance(
        instance_id=PLACE_MARKERS_INSTANCE_ID, capability_id=PLACE_MARKERS_INSTANCE_ID, label="Marked places",
        provider="aegis", overlay_type="geojson", rendering_mode="place-markers",
        descriptor={"data": {"features": features}},
    )


###############################################################################
def test_a_comparison_map_must_show_every_requested_place() -> None:
    state = _state(_compound_route(presentation="map"))
    labelled = _map(_markers("18.3 °C", "19.4 °C"))
    contract = presentation_contract(state, labelled)
    assert contract is not None and [target.ref for target in contract.targets] == ["rome", "milan"]

    only_rome = contract.violations([12.0, 41.5, 13.0, 42.3])
    assert any("Milan" in item for item in only_rome)
    assert not contract.violations([8.5, 41.0, 13.0, 46.0])


###############################################################################
def test_a_landmark_must_be_framed_at_landmark_scale_not_as_its_city() -> None:
    route = _compound_route(
        presentation="map", target_refs=["Brandenburg Gate"], target_requirements=[],
        temporal_scope=AgentTemporalScope(), capability_queries=[],
    )
    state = _state(route)
    state.location_refs = {"brandenburg gate": ResolvedLocation(
        label="Brandenburg Gate, Berlin", latitude=52.5163, longitude=13.3777, location_type="landmark",
    )}
    contract = presentation_contract(state, _map())
    assert contract is not None

    berlin_view = [13.08, 52.33, 13.76, 52.68]
    assert any("too wide" in item for item in contract.violations(berlin_view))
    assert not contract.violations([13.37, 52.51, 13.39, 52.52])


###############################################################################
def test_requested_values_must_be_labelled_not_shown_as_bare_markers() -> None:
    state = _state(_compound_route(presentation="map", temporal_scope=AgentTemporalScope(), target_requirements=[]))
    bare = presentation_contract(state, _map(_markers(None, None)))
    labelled = presentation_contract(state, _map(_markers("18.3 °C", "19.4 °C")))

    assert bare is not None and any("without the weather values" in item for item in bare.findings)
    assert labelled is not None and not labelled.findings


###############################################################################
def test_a_render_acknowledgment_satisfies_only_the_presentation_obligation() -> None:
    state = _state(_compound_route(presentation="map", temporal_scope=AgentTemporalScope(), target_requirements=[]))
    state.render_verified = True

    summary = build_completion_summary(state, AgentLoop._completion_checks(state))  # pyright: ignore[reportPrivateUsage]
    status = {item.kind: item.status for item in summary.obligations}

    assert summary.map_state == "rendered"
    assert status["presentation"] == "met"
    assert status["data"] == "unmet"


###############################################################################
def test_contract_rejects_a_ready_acknowledgment_that_misses_a_place() -> None:
    state = _state(_compound_route(presentation="map"))
    contract = presentation_contract(state, _map(_markers("18.3 °C", "19.4 °C")))
    assert contract is not None
    presentation = {
        "presentation_contract": contract.model_dump(mode="json"),
        "map_session_id": "map-1", "collection_revision": 1,
    }

    def ack(viewport: list[float]) -> RealtimeRenderAckPayload:
        return RealtimeRenderAckPayload(
            run_id="run-1", run_version=1, map_session_id="map-1", collection_revision=1,
            status="ready", viewport_bounds=viewport,
        )

    enforce = RenderCompletionService._enforce_presentation_contract  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="Presentation contract failed"):
        enforce(presentation, ack([12.0, 41.5, 13.0, 42.3]))
    enforce(presentation, ack([8.5, 41.0, 13.0, 46.0]))


###############################################################################
def test_an_area_scope_is_judged_by_its_results_not_its_centre() -> None:
    contract = PresentationContract(targets=[ContractTarget(
        ref="world", label="World", latitude=0.0, longitude=0.0, location_type="macro_region",
    )])
    far_from_centre = [100.0, 10.0, 140.0, 40.0]
    assert not contract.violations(far_from_centre, 0.9)
    assert contract.violations(far_from_centre, 0.1)
    assert not contract.violations(far_from_centre)


###############################################################################
def test_a_global_target_is_always_in_view_and_a_small_extent_is_a_fine_place() -> None:
    world = ContractTarget(
        ref="world", label="World", latitude=0.0, longitude=0.0,
        location_type="macro_region", bbox=[-180.0, -85.0, 180.0, 85.0],
    )
    assert not PresentationContract(targets=[world]).violations([-180.0, -40.0, 180.0, 40.0], 0.4)

    gate = ContractTarget(
        ref="gate", label="Brandenburg Gate", latitude=52.5163, longitude=13.3777,
        location_type="attraction", bbox=[13.3770, 52.5160, 13.3785, 52.5166],
    )
    city_view = [13.2, 52.45, 13.55, 52.6]
    assert PresentationContract(targets=[gate]).violations(city_view)
    assert not PresentationContract(targets=[gate]).violations([13.37, 52.51, 13.385, 52.522])
    # S03: the ~10 km wide view that used to pass is still city scale.
    s03_view = [13.3127, 52.4886, 13.4427, 52.5471]
    assert PresentationContract(targets=[gate]).violations(s03_view)


###############################################################################
def _comparison_state(*, with_transform: bool) -> AgentRunState:
    state = _state(_compound_route(
        analysis={"kind": "rank", "metric": "temperature"}, temporal_scope=AgentTemporalScope(),
        target_requirements=[],
    ))
    state.completion_contract = CompletionContract(
        operation="compare", requirements=["required_data_retrieved", "result_locations_derived"]
    )
    for ref, value in (("Rome", 14.2), ("Milan", 10.9)):
        result = _evidence(ref, "2026-11-03T10:00:00+00:00")
        result.data = {"kind": "weather_forecast", "query": {"location_ref": ref},
                       "precipitation": 0.0, "temperature_2m": value}
        state.tool_results.append(result)
    if with_transform:
        state.tool_results.append(ToolResult(
            call_id="transform-1", tool_name="transform_evidence", status="success", summary="ok",
            data={"preview": [{"place_label": "Rome", "temperature_2m": 14.2}]},
            metadata=ToolExecutionMetadata(duration_ms=0, capability_id="openmeteo_weather_forecast"),
        ))
    return state


###############################################################################
def test_comparison_requires_each_targets_figure_and_fallback_is_not_top_results() -> None:
    state = _comparison_state(with_transform=False)
    summary = build_completion_summary(state, {"required_data_retrieved": True, "result_locations_derived": True})
    analysis = next(item for item in summary.obligations if item.kind == "analysis")
    assert [14.2 in group for group in analysis.cite_groups] == [True, False]
    assert [10.9 in group for group in analysis.cite_groups] == [False, True]

    # An unfinished analysis never falls back to unrelated record previews.
    state = _comparison_state(with_transform=True)
    state.tool_results.append(ToolResult(
        call_id="transform-2", tool_name="transform_evidence", status="failed", summary="no field",
        metadata=ToolExecutionMetadata(duration_ms=0),
    ))
    state.context_hydrated = True
    findings = AgentLoop._evidence_findings(state)  # pyright: ignore[reportPrivateUsage]
    assert "Top results" not in findings
    assert "14.2" in findings and "10.9" in findings


###############################################################################
def test_statistics_inspection_supplies_the_ranked_record_to_the_summary() -> None:
    state = _comparison_state(with_transform=False)
    state.tool_results.append(ToolResult(
        call_id="inspect-1", tool_name="inspect_evidence", status="success", summary="ok",
        data={"result": {"statistics": {"mag": {
            "min": 1.0, "max": 6.1, "count": 40, "mean": 2.0,
            "argmax": {"place": "Offshore Chile", "mag": 6.1},
        }}}},
        metadata=ToolExecutionMetadata(duration_ms=0),
    ))
    from server.services.agent.completion import _leading_values  # pyright: ignore[reportPrivateUsage]

    values = _leading_values(state.tool_results[-1], variable="magnitude")
    assert values == ["mag max 6.1 (Offshore Chile), min 1.0"]
